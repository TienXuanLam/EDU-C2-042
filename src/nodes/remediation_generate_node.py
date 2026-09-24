"""AgentCore Platform v1.0"""

# Inner domain workflow node (docs/02_design.md — proposal §4 step 4: LLM
# Remediation Generation). Only reached when remediation_mode ==
# "full_remediation" (inner graph routing, docs/02_design.md
# "rules_only mode"). For each record with at least one schema/domain
# finding, the LLM turns the already-computed findings into a concise
# advisory remediation hint — it never re-derives or overrides a
# pass/fail/severity judgment (Design Decision Record, docs/02_design.md).

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.services.llm.azure_openai_client import AzureOpenAIClient
from shared.services.llm.base_llm import BaseLLM
from shared.utils.audit_logger import emit_trace_event
from src.services.remediation_llm_service import generate_remediation_hint


class RemediationGenerateNode(FunctionNode):
    """LLM-draft a concise remediation hint per record that has findings."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        system_prompt: str | None = None,
        timeout_s: int = 45,
        max_retries: int = 1,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__()
        self._system_prompt = system_prompt
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _build_llm(self, state: AgentState) -> BaseLLM:
        # timeout/max_retries/temperature/max_tokens are AzureOpenAIClient
        # constructor config, not complete() kwargs -- passing them to
        # complete() raises TypeError (verified against the real wheel).
        # "model" is not passed: AzureOpenAIClient always routes on
        # azure_deployment, not a separate "model" config key.
        ctx = InvocationContext.from_state(state)
        return AzureOpenAIClient(
            {
                "api_key": ctx.secrets.require("AZURE_OPENAI_API_KEY"),
                "azure_endpoint": ctx.secrets.require("AZURE_OPENAI_ENDPOINT"),
                "azure_deployment": ctx.secrets.require("AZURE_OPENAI_DEPLOYMENT"),
                "timeout": self._timeout_s,
                "max_retries": self._max_retries,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            }
        )

    def execute(self, state: AgentState) -> dict[str, Any]:
        try:
            llm = self._build_llm(state)
        except Exception as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"RemediationGenerateNode: LLM not configured: {exc}"],
            }

        records = state.get("resource_records", [])
        schema_findings = state.get("schema_findings", [])
        domain_findings = state.get("domain_findings", [])
        all_findings = schema_findings + domain_findings

        findings_by_resource: dict[str, list[dict[str, str]]] = {}
        for f in all_findings:
            findings_by_resource.setdefault(f["resource_id"], []).append(f)

        # Bounded-evidence boundary (review finding T1-01): only resource_id + rule
        # findings reach the LLM — never raw record fields (e.g. title). See
        # remediation_llm_service.py module docstring.
        remediation_hints: list[dict[str, str]] = []
        try:
            for resource_id, findings in findings_by_resource.items():
                hint = generate_remediation_hint(llm, resource_id, findings, self._system_prompt)
                if not hint.strip():
                    return {
                        "status": AgentStatus.ERROR.value,
                        "error_log": [f"RemediationGenerateNode: LLM returned empty content for {resource_id}"],
                    }
                remediation_hints.append({"resource_id": resource_id, "hint": hint})
        except Exception as exc:  # provider/network error — fail closed, not a crash
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"RemediationGenerateNode: LLM request failed: {exc}"],
            }

        emit_trace_event(
            "remediation_generated",
            {"resource_count": len(records), "hint_count": len(remediation_hints)},
            state,
        )

        return {
            "remediation_hints": remediation_hints,
            "status": AgentStatus.SUCCESS.value,
        }
