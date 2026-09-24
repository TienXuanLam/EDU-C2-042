"""AgentCore Platform v1.0"""

# State fields are flat primitives / containers of primitives only (see
# sdk/concepts/state-and-schemas.md) — msgpack-checkpoint-safe. This agent
# processes resource discovery metadata only (proposal §3) — no student/
# learner data of any kind is ever expected to land here; the *_pii_findings
# fields exist only to record a defense-in-depth scan result, not to store
# PII itself.

from framework.schemas.agent_state import AgentState
from typing import Any


class State(AgentState):
    """EDU-C2-042 — EducationLearningResourceMetadataExchangeValidatorAgent state.

    Only fields specific to this agent are declared below. Shared fields
    (user_input, status, session_id, node_history, error_log, hitl_*, etc.)
    are inherited from AgentState.
    """

    # --- pre_process (InputNormaliseNode) ---
    source_format: str  # "json" | "xml" | "csv"
    profile_version: str
    remediation_mode: str  # "full_remediation" (LLM hints) | "rules_only" (no LLM)
    resource_records: list[dict[str, Any]]  # canonical: resource_id, title, subject_code, grade_code,
    # licence, language, format, url, date_published, accessibility_descriptors (list[str])
    ingest_errors: list[dict[str, Any]]  # quarantined malformed entries: record_index, reason
    validated_input: str  # JSON string forwarded to the inner domain workflow graph

    # --- main (RecordValidationWorkflowGraphNode <- inner domain workflow graph) ---
    schema_findings: list[dict[str, Any]]  # + rule_id, resource_id, field, severity, message
    domain_findings: list[dict[str, Any]]  # + rule_id, resource_id, field, severity, message
    remediation_hints: list[dict[str, Any]]  # resource_id, hint (empty in rules_only mode)

    # --- post_process (ReportHandoffNode) ---
    final_report_markdown: str
