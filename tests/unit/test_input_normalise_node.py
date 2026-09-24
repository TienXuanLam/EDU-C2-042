# EDU-C2-042 — Unit Tests: InputNormaliseNode (BL-39..BL-51)

import json

from framework.schemas.trust_level import TrustLevel
from src.nodes.input_normalise_node import InputNormaliseNode

PROFILE_VERSION = "2026.1-illustrative"


def _state(user_input: str) -> dict:
    return {
        "user_input": user_input,
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "thread_id": "test-thread",
        "trace_id": "",
        "caller_id": "",
        "hitl_allowed": True,
        "node_history": [],
        "error_log": [],
    }


def _envelope(**overrides) -> str:
    payload = {
        "source_format": "json",
        "profile_version": PROFILE_VERSION,
        "payload": '[{"resource_id": "R1", "title": "T1", "subject_code": "MATH", "grade_code": "G5", '
        '"licence": "CC-BY-4.0", "language": "ja", "format": "pdf", "url": "https://example.org/r1"}]',
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestInputNormaliseNode:
    def setup_method(self):
        self.node = InputNormaliseNode(expected_profile_version=PROFILE_VERSION)

    def test_success_path(self):
        """BL-39: a valid envelope is parsed and normalized."""
        result = self.node.execute(_state(_envelope()))
        assert result["status"] == "success"
        assert result["source_format"] == "json"
        assert result["remediation_mode"] == "full_remediation"
        assert len(result["resource_records"]) == 1
        assert json.loads(result["validated_input"])["records"][0]["resource_id"] == "R1"

    def test_profile_version_mismatch_rejected(self):
        """BL-40: a caller-declared profile_version that does not match the configured one is rejected."""
        result = self.node.execute(_state(_envelope(profile_version="stale-version")))
        assert result["status"] == "error"

    def test_invalid_source_format_rejected(self):
        """BL-41: an unsupported source_format is rejected."""
        result = self.node.execute(_state(_envelope(source_format="yaml")))
        assert result["status"] == "error"

    def test_invalid_mode_rejected(self):
        """BL-42: an invalid mode value is rejected."""
        result = self.node.execute(_state(_envelope(mode="bogus_mode")))
        assert result["status"] == "error"

    def test_missing_payload_rejected(self):
        """BL-43: an empty payload is rejected."""
        result = self.node.execute(_state(_envelope(payload="")))
        assert result["status"] == "error"

    def test_malformed_envelope_json_rejected(self):
        """BL-44: non-JSON user_input is rejected."""
        result = self.node.execute(_state("not json at all"))
        assert result["status"] == "error"

    def test_non_object_envelope_rejected(self):
        """BL-45: a JSON array (not an object) envelope is rejected."""
        result = self.node.execute(_state("[1, 2, 3]"))
        assert result["status"] == "error"

    def test_catalogue_syntax_error_surfaces_as_error(self):
        """BL-46: a whole-batch parse failure inside the payload is surfaced as status=error."""
        result = self.node.execute(_state(_envelope(payload="not valid json for records")))
        assert result["status"] == "error"

    def test_no_valid_records_after_quarantine_rejected(self):
        """BL-47: if every entry is quarantined, the batch is rejected."""
        result = self.node.execute(_state(_envelope(payload='["not an object"]')))
        assert result["status"] == "error"

    def test_rules_only_mode_accepted(self):
        """BL-48: rules_only mode is a valid, accepted mode."""
        result = self.node.execute(_state(_envelope(mode="rules_only")))
        assert result["status"] == "success"
        assert result["remediation_mode"] == "rules_only"

    def test_fails_closed_when_no_profile_version_configured(self):
        """BL-49: the agent fails closed if no approved exchange_profile.version is configured."""
        node = InputNormaliseNode(expected_profile_version=None)
        result = node.execute(_state(_envelope()))
        assert result["status"] == "error"

    def test_s2_rejects_learner_identifier_via_call(self):
        """BL-50: __call__() runs the S-2 hook and rejects a payload embedding learner data."""
        result = self.node(_state(_envelope(payload='[{"student_name": "Taro Yamada"}]')))
        assert result["status"] == "error"

    def test_s2_allows_clean_payload_via_call(self):
        """BL-51: __call__() allows a clean resource-metadata-only payload."""
        result = self.node(_state(_envelope()))
        assert result["status"] == "success"

    def test_payload_as_real_json_array_is_accepted_when_source_format_is_json(self):
        """Regression: a caller that sends `payload` as a real JSON array
        (not a pre-escaped string-within-a-string) must succeed when
        source_format="json" -- this is what a Marketplace UI caller typing
        the envelope directly produces, and what src/api/server.py's
        object-input path forwards unchanged (only server.py's own
        source_format="json" re-stringify was previously covering this;
        the Marketplace entrypoint calls agent.invoke() directly, bypassing
        server.py entirely, so this must also work here)."""
        envelope = {
            "source_format": "json",
            "profile_version": PROFILE_VERSION,
            "mode": "full_remediation",
            "payload": [
                {
                    "resource_id": "R1",
                    "title": "T1",
                    "subject_code": "MATH",
                    "grade_code": "G5",
                    "licence": "CC-BY-4.0",
                    "language": "ja",
                    "format": "pdf",
                    "url": "https://example.org/r1",
                }
            ],
        }
        result = self.node.execute(_state(json.dumps(envelope)))
        assert result["status"] == "success"
        assert len(result["resource_records"]) == 1
        assert json.loads(result["validated_input"])["records"][0]["resource_id"] == "R1"

    def test_payload_as_real_json_object_is_rejected_for_non_json_source_format(self):
        """A real JSON array/dict payload only makes sense for
        source_format="json" -- csv/xml payload must remain raw text, so a
        dict/list payload there is rejected with the same clear error as
        today, not silently misparsed."""
        envelope = {
            "source_format": "csv",
            "profile_version": PROFILE_VERSION,
            "payload": [{"resource_id": "R1"}],
        }
        result = self.node.execute(_state(json.dumps(envelope)))
        assert result["status"] == "error"
