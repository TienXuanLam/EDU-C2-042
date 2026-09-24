"""AgentCore Platform v1.0"""

# Inner domain workflow node (docs/02_design.md — proposal §4 step 2:
# Schema & Format Validation). First node of the inner graph: BaseGraph
# forwards a single string (InputNormaliseNode's validated_input, a JSON
# string) as state["user_input"] — this node re-parses it and rehydrates the
# individual fields into inner state for downstream nodes.

from __future__ import annotations

import json
from collections import Counter
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.schema_validate_service import validate_schema


class SchemaFormatValidateNode(FunctionNode):
    """Parse the forwarded request and run deterministic schema/format checks per record."""

    # S-1: matches config/agent.yaml's agent-level required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        required_fields: list[str] | None = None,
        resource_id_pattern: str | None = None,
        date_pattern: str | None = None,
    ) -> None:
        super().__init__()
        self._required_fields = required_fields or []
        self._resource_id_pattern = resource_id_pattern
        self._date_pattern = date_pattern

    def execute(self, state: AgentState) -> dict[str, Any]:
        emit_trace_event("schema_format_validation_started", {}, state)
        # Fails closed (proposal §4 Notes): no approved exchange profile pack configured.
        if not self._resource_id_pattern or not self._date_pattern:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "SchemaFormatValidateNode: no exchange_profile pattern rules configured — failing closed"
                ],
            }

        raw = state.get("user_input", "") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SchemaFormatValidateNode: forwarded input is not valid JSON"],
            }
        if not isinstance(payload, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SchemaFormatValidateNode: forwarded input must be a JSON object"],
            }

        remediation_mode = payload.get("remediation_mode", "full_remediation")
        records = payload.get("records", []) or []
        if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SchemaFormatValidateNode: forwarded records must be a list of objects"],
            }

        schema_findings: list[dict[str, str]] = [
            f
            for record in records
            for f in validate_schema(record, self._required_fields, self._resource_id_pattern, self._date_pattern)
        ]
        id_counts = Counter(str(record.get("resource_id", "")) for record in records)
        for duplicate_id, count in id_counts.items():
            if duplicate_id and count > 1:
                schema_findings.append(
                    {
                        "resource_id": duplicate_id,
                        "rule_id": "SCHEMA-005",
                        "field": "resource_id",
                        "severity": "critical",
                        "message": f"resource_id '{duplicate_id}' occurs {count} times in the catalogue batch",
                    }
                )
        critical_count = sum(1 for f in schema_findings if f["severity"] == "critical")

        emit_trace_event(
            "schema_format_validated",
            {
                "record_count": len(records),
                "finding_count": len(schema_findings),
                "critical_finding_count": critical_count,
            },
            state,
        )

        return {
            "remediation_mode": remediation_mode,
            "resource_records": records,
            "schema_findings": schema_findings,
            "status": AgentStatus.SUCCESS.value,
        }
