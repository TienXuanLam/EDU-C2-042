"""AgentCore Platform v1.0"""

# Inner domain workflow node (docs/02_design.md — proposal §4 step 3: Domain
# Rule Validation). Deterministic curriculum-code / controlled-vocabulary /
# accessibility checks — NO LLM (see domain_rule_service.py module docstring
# for the Design Decision Record rationale).

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.domain_rule_service import validate_domain_rules


class DomainRuleValidateNode(FunctionNode):
    """Validate each record's curriculum codes, controlled-vocabulary values, and accessibility descriptors."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        subject_codes: list[str] | None = None,
        grade_codes: list[str] | None = None,
        controlled_vocabulary: dict[str, list[str]] | None = None,
        required_descriptors_by_format: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__()
        self._subject_codes = subject_codes or []
        self._grade_codes = grade_codes or []
        self._controlled_vocabulary = controlled_vocabulary or {}
        self._required_descriptors_by_format = required_descriptors_by_format or {}

    def execute(self, state: AgentState) -> dict[str, Any]:
        # Fails closed (proposal §4 Notes): no curriculum code list / controlled
        # vocabulary configured.
        if not self._subject_codes or not self._grade_codes or not self._controlled_vocabulary:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "DomainRuleValidateNode: no curriculum code list / controlled vocabulary configured — failing closed"
                ],
            }

        records = state.get("resource_records", [])

        domain_findings = [
            f
            for record in records
            for f in validate_domain_rules(
                record,
                self._subject_codes,
                self._grade_codes,
                self._controlled_vocabulary,
                self._required_descriptors_by_format,
            )
        ]
        critical_count = sum(1 for f in domain_findings if f["severity"] == "critical")

        emit_trace_event(
            "domain_rules_validated",
            {
                "record_count": len(records),
                "finding_count": len(domain_findings),
                "critical_finding_count": critical_count,
            },
            state,
        )

        return {
            "domain_findings": domain_findings,
            "status": AgentStatus.SUCCESS.value,
        }
