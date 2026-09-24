"""AgentCore Platform v1.0"""

# EDU-C2-042 — Cat 2: AgentBaseGraph (outer, fixed 5-node backbone) + GraphNode
# in the `main` slot wrapping the inner domain workflow graph
# (src/graph/domain_workflow_graph.py). Proposal §4 lists 5 steps (Input
# Normalisation / Schema & Format Validation / Domain Rule Validation / LLM
# Remediation Generation / Report & Human Handoff) — more than
# AgentBaseGraph's 3 fixed slots, so the 3 middle steps are encapsulated in
# the inner graph, matching the current Cat 2 scaffold convention
# (src/examples/graph_cat2_sample.py; see docs/02_design.md Design Decision
# Record — supersedes the older step-helper pattern described in some
# historical playbook notes, per a precedent used elsewhere in the fleet).
#
# Do NOT override add_edges() on this outer graph — backbone wiring
# (initialize -> pre_process -> main -> {route} -> post_process -> finalize)
# belongs to AgentBaseGraph.

from typing import TYPE_CHECKING, Any, ClassVar

from framework.errors import ConfigError
from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from src.nodes.input_normalise_node import InputNormaliseNode
from src.nodes.report_handoff_node import ReportHandoffNode
from src.schemas.state import State
from src.services.config_validation_service import validate_profile_config

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import RecordValidationWorkflowGraph


class RecordValidationWorkflowGraphNode(GraphNode):
    """Wraps the inner domain workflow graph; assigned to the outer `main` slot."""

    # S-1: check_trust_level.py only scans direct FunctionNode subclasses, so
    # GraphNode subclasses default to ANONYMOUS silently unless declared here
    # explicitly. Matches config/agent.yaml's agent-level required_trust_level
    # and the other two outer nodes.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"  # fail fast — no silent partial validation report
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        exchange_profile: dict[str, Any] | None = None,
        curriculum_code_list: dict[str, Any] | None = None,
        controlled_vocabulary: dict[str, Any] | None = None,
        accessibility_profile: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        llm_timeout_s: int = 45,
        llm_max_retries: int = 1,
        llm_temperature: float = 0.1,
        llm_max_tokens: int = 1024,
    ) -> None:
        super().__init__()
        self._exchange_profile = exchange_profile
        self._curriculum_code_list = curriculum_code_list
        self._controlled_vocabulary = controlled_vocabulary
        self._accessibility_profile = accessibility_profile
        self._system_prompt = system_prompt
        self._llm_timeout_s = llm_timeout_s
        self._llm_max_retries = llm_max_retries
        self._llm_temperature = llm_temperature
        self._llm_max_tokens = llm_max_tokens

    def get_subgraph(self) -> "RecordValidationWorkflowGraph":
        from src.graph.domain_workflow_graph import RecordValidationWorkflowGraph

        return RecordValidationWorkflowGraph(
            config={
                "exchange_profile": self._exchange_profile,
                "curriculum_code_list": self._curriculum_code_list,
                "controlled_vocabulary": self._controlled_vocabulary,
                "accessibility_profile": self._accessibility_profile,
                "system_prompt": self._system_prompt,
                "llm_timeout_s": self._llm_timeout_s,
                "llm_max_retries": self._llm_max_retries,
                "llm_temperature": self._llm_temperature,
                "llm_max_tokens": self._llm_max_tokens,
            }
        )

    def extract_input(self, state: AgentState) -> str:
        # validated_input is the normalized JSON string built by
        # InputNormaliseNode — the single string the inner BaseGraph.invoke()
        # boundary requires (docs/02_design.md).
        return str(state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        output = sub_result.get("output", {}) or {}
        if not isinstance(output, dict):
            output = {}
        return {
            "schema_findings": output.get("schema_findings", []),
            "domain_findings": output.get("domain_findings", []),
            "remediation_hints": output.get("remediation_hints", []),
            "status": sub_result.get("status"),
        }


class EducationLearningResourceMetadataExchangeValidatorAgent(AgentBaseGraph):
    """EDU-C2-042 — education learning-resource metadata exchange validation."""

    @property
    def name(self) -> str:
        return "EducationLearningResourceMetadataExchangeValidatorAgent"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        super()._validate_config()
        try:
            validate_profile_config(self.config)
        except ValueError as exc:
            raise ConfigError(f"[{self.__class__.__name__}] invalid metadata profile config: {exc}") from exc

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        exchange_profile = self.config.get("exchange_profile") or {}

        self._nodes["pre_process"] = InputNormaliseNode(
            expected_profile_version=exchange_profile.get("version"),
        )
        self._nodes["main"] = RecordValidationWorkflowGraphNode(
            exchange_profile=self.config.get("exchange_profile"),
            curriculum_code_list=self.config.get("curriculum_code_list"),
            controlled_vocabulary=self.config.get("controlled_vocabulary"),
            accessibility_profile=self.config.get("accessibility_profile"),
            system_prompt=self.config.get("system_prompt"),
            llm_timeout_s=int(self.config.get("timeout_s", 45)),
            llm_max_retries=int(self.config.get("max_retry", 1)),
            llm_temperature=float(self.config.get("llm_temperature", 0.1)),
            llm_max_tokens=int(self.config.get("llm_max_tokens", 1024)),
        )
        self._nodes["post_process"] = ReportHandoffNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
