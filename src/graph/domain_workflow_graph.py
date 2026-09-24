"""AgentCore Platform v1.0"""

# EDU-C2-042 — inner domain workflow graph (Cat 2, see docs/02_design.md).
# Instantiated by RecordValidationWorkflowGraphNode.get_subgraph() in graph.py.
# Inherits BaseGraph directly — fully custom topology, not the
# pre_process/main/post_process backbone (that belongs to the outer graph).
#
# Pipeline (branches once, on remediation_mode — proposal has no explicit
# LLM-free path, but the LLM remediation step needs a bypass so the agent
# can be exercised without a real LLM/API key, e.g. Stage 5 STG smoke test —
# see docs/02_design.md "rules_only mode"):
#     START -> schema_format_validate -> domain_rule_validate -> {route: remediation_mode}
#                full_remediation:  -> remediation_generate -> END
#                rules_only:        -> END (ReportHandoffNode renders findings only)

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.errors import ConfigError
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.domain_rule_validate_node import DomainRuleValidateNode
from src.nodes.remediation_generate_node import RemediationGenerateNode
from src.nodes.schema_format_validate_node import SchemaFormatValidateNode
from src.schemas.state import State
from src.services.config_validation_service import validate_profile_config


class RecordValidationWorkflowGraph(BaseGraph):
    """Inner graph for the schema/domain validation and remediation-generation workflow."""

    @property
    def name(self) -> str:
        return "record_validation_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        try:
            validate_profile_config(self.config)
        except ValueError as exc:
            raise ConfigError(f"[{self.__class__.__name__}] invalid metadata profile config: {exc}") from exc

    def register_nodes(self) -> None:
        exchange_profile = self.config.get("exchange_profile") or {}
        curriculum_code_list = self.config.get("curriculum_code_list") or {}
        controlled_vocabulary = self.config.get("controlled_vocabulary") or {}
        accessibility_profile = self.config.get("accessibility_profile") or {}
        system_prompt = self.config.get("system_prompt")

        self._nodes["schema_format_validate"] = SchemaFormatValidateNode(
            required_fields=exchange_profile.get("required_fields"),
            resource_id_pattern=exchange_profile.get("resource_id_pattern"),
            date_pattern=exchange_profile.get("date_pattern"),
        )
        self._nodes["domain_rule_validate"] = DomainRuleValidateNode(
            subject_codes=curriculum_code_list.get("subject_codes"),
            grade_codes=curriculum_code_list.get("grade_codes"),
            controlled_vocabulary=controlled_vocabulary,
            required_descriptors_by_format=accessibility_profile.get("required_descriptors_by_format"),
        )
        # LLM client is resolved per-invocation inside RemediationGenerateNode
        # via InvocationContext.from_state(state).secrets.require(...), not
        # built once here and threaded through config -- matches the
        # fleet-standard pattern used elsewhere in the fleet's server.py files.
        self._nodes["remediation_generate"] = RemediationGenerateNode(
            system_prompt=system_prompt,
            timeout_s=int(self.config.get("llm_timeout_s", 45)),
            max_retries=int(self.config.get("llm_max_retries", 1)),
            temperature=float(self.config.get("llm_temperature", 0.1)),
            max_tokens=int(self.config.get("llm_max_tokens", 1024)),
        )

    def add_edges(self) -> None:
        self._sg.add_edge(START, "schema_format_validate")
        self._sg.add_edge("schema_format_validate", "domain_rule_validate")
        # lambda wrapper, not a bare `self.route` reference: passing the bound
        # method directly to add_conditional_edges (langgraph==1.1.10) caused
        # BOTH conditional targets to fire regardless of the returned value
        # (reproduced with a minimal StateGraph outside this class) — the
        # lambda wrapper does not exhibit the bug.
        self._sg.add_conditional_edges(
            "domain_rule_validate",
            lambda state: self.route(state),
            {"remediation_generate": "remediation_generate", END: END},
        )
        self._sg.add_edge("remediation_generate", END)

    def route(self, state: AgentState) -> str:
        """Conditional routing after domain_rule_validate.

        rules_only mode skips the LLM remediation step entirely —
        ReportHandoffNode (outer post_process) renders schema_findings /
        domain_findings directly instead (docs/02_design.md).
        """
        if state.get("status") == AgentStatus.ERROR.value:
            return END
        return "remediation_generate" if state.get("remediation_mode") == "full_remediation" else END

    def get_output(self, state: AgentState) -> dict[str, object]:
        return {
            "output": {
                "resource_records": state.get("resource_records", []),
                "schema_findings": state.get("schema_findings", []),
                "domain_findings": state.get("domain_findings", []),
                "remediation_hints": state.get("remediation_hints", []),
                "remediation_mode": state.get("remediation_mode", ""),
            },
            "status": state.get("status", AgentStatus.ERROR.value),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
