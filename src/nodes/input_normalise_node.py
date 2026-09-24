"""AgentCore Platform v1.0"""

# Outer pre_process node (docs/02_design.md — proposal §4 step 1: Input
# Normalisation). Parses the caller's catalogue export envelope, validates
# it, normalises every entry into the canonical record shape, and forwards
# validated_input (a JSON string) to the inner domain workflow graph
# (GraphNode.extract_input() can only forward a single string — see
# docs/02_design.md State Definition note).
#
# Caller envelope (user_input, JSON):
#   {
#     "source_format": "json" | "xml" | "csv",
#     "profile_version": "<must match config/config.yaml exchange_profile.version>",
#     "mode": "full_remediation" (default) | "rules_only",
#     "payload": "<raw catalogue export text in source_format>"
#   }

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.catalogue_parse_service import CatalogueSyntaxError, parse_catalogue
from src.services.learner_pii_scan import contains_learner_identifier

_VALID_SOURCE_FORMATS = {"json", "xml", "csv"}
_VALID_MODES = {"full_remediation", "rules_only"}


class InputNormaliseNode(FunctionNode):
    """Parse, validate, and normalise the caller's catalogue export."""

    # S-1: curriculum coordinator/LMS admin/publisher/board
    # officer caller only — not anonymous public (proposal §8 Users table).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, expected_profile_version: str | None = None) -> None:
        super().__init__()
        self._expected_profile_version = expected_profile_version

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        """S-2 domain check: reject payloads carrying learner-level data.

        Proposal §3/§11 Risk #4: this template accepts resource discovery
        metadata only — never learner/student records (defense-in-depth;
        the primary boundary is the institution's exchange profile scope).
        """
        raw = state.get("user_input", "") or ""
        if contains_learner_identifier(raw):
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = list(state.get("error_log", [])) + [
                "InputNormaliseNode: input rejected — apparent learner-level "
                "identifier detected (this template accepts resource discovery "
                "metadata only)"
            ]
        return state

    def execute(self, state: AgentState) -> dict[str, Any]:
        emit_trace_event("catalogue_ingest_started", {}, state)
        if state.get("status") == AgentStatus.ERROR.value:
            # Already rejected by the S-2 hook above.
            return {"status": AgentStatus.ERROR.value}

        # Fails closed (proposal §4 Notes): the agent must not run without a
        # configured approved exchange-profile version.
        if not self._expected_profile_version:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputNormaliseNode: no approved exchange_profile.version configured — failing closed"],
            }

        raw = state.get("user_input", "") or ""
        try:
            envelope = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputNormaliseNode: user_input is not valid JSON"],
            }

        if not isinstance(envelope, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputNormaliseNode: envelope must be a JSON object"],
            }

        source_format = envelope.get("source_format", "")
        if source_format not in _VALID_SOURCE_FORMATS:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"InputNormaliseNode: invalid or missing source_format {source_format!r}"],
            }

        profile_version = envelope.get("profile_version", "")
        if profile_version != self._expected_profile_version:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"InputNormaliseNode: profile_version {profile_version!r} does not match the "
                    f"institution-approved profile {self._expected_profile_version!r}"
                ],
            }

        mode = envelope.get("mode", "full_remediation")
        if mode not in _VALID_MODES:
            return {"status": AgentStatus.ERROR.value, "error_log": [f"InputNormaliseNode: invalid mode {mode!r}"]}

        payload = envelope.get("payload", "")
        # Callers that don't hand-escape JSON (server.py's object-input path,
        # or a Marketplace UI caller typing the envelope directly) can send
        # `payload` as a real JSON array/object instead of a string-within-
        # a-string. Only source_format="json" can meaningfully do this --
        # csv/xml payload must already be raw text. Re-stringify it here
        # (the one place both the HTTP and Marketplace entrypoints funnel
        # through user_input) so parse_catalogue's str-only interface is
        # unaffected either way.
        if source_format == "json" and isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        if not isinstance(payload, str) or not payload.strip():
            return {"status": AgentStatus.ERROR.value, "error_log": ["InputNormaliseNode: missing or empty 'payload'"]}

        try:
            records, ingest_errors = parse_catalogue(source_format, payload)
        except CatalogueSyntaxError as exc:
            return {"status": AgentStatus.ERROR.value, "error_log": [f"InputNormaliseNode: {exc}"]}

        if not records:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputNormaliseNode: no valid records found in payload after quarantine"],
            }

        validated_input = json.dumps({"remediation_mode": mode, "records": records})

        emit_trace_event(
            "catalogue_ingested",
            {
                "source_format": source_format,
                "record_count": len(records),
                "ingest_error_count": len(ingest_errors),
            },
            state,
        )

        return {
            "source_format": source_format,
            "profile_version": profile_version,
            "remediation_mode": mode,
            "resource_records": records,
            "ingest_errors": ingest_errors,
            "validated_input": validated_input,
            "status": AgentStatus.SUCCESS.value,
        }
