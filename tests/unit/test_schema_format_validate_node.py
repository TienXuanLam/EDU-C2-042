# EDU-C2-042 — Unit Tests: SchemaFormatValidateNode (BL-52..BL-56)

import json

from src.nodes.schema_format_validate_node import SchemaFormatValidateNode

REQUIRED_FIELDS = ["resource_id", "title"]
RESOURCE_ID_PATTERN = r"^[A-Za-z0-9._-]{3,64}$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def _state(records: list[dict], remediation_mode: str = "full_remediation") -> dict:
    return {"user_input": json.dumps({"remediation_mode": remediation_mode, "records": records})}


class TestSchemaFormatValidateNode:
    def setup_method(self):
        self.node = SchemaFormatValidateNode(REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)

    def test_success_path_no_findings(self):
        """BL-52: valid records produce no schema findings."""
        result = self.node.execute(_state([{"resource_id": "RES-001", "title": "Algebra"}]))
        assert result["status"] == "success"
        assert result["schema_findings"] == []
        assert result["resource_records"][0]["resource_id"] == "RES-001"

    def test_finding_produced_for_invalid_record(self):
        """BL-53: a missing required field produces a SCHEMA-001 finding."""
        result = self.node.execute(_state([{"resource_id": "RES-001", "title": ""}]))
        assert any(f["rule_id"] == "SCHEMA-001" for f in result["schema_findings"])

    def test_remediation_mode_forwarded(self):
        """BL-54: remediation_mode is forwarded from the parsed envelope."""
        result = self.node.execute(
            _state([{"resource_id": "RES-001", "title": "Algebra"}], remediation_mode="rules_only")
        )
        assert result["remediation_mode"] == "rules_only"

    def test_malformed_forwarded_json_fails_closed(self):
        """BL-55: malformed forwarded JSON returns a controlled error."""
        result = self.node.execute({"user_input": "not json"})
        assert result["status"] == "error"
        assert "not valid JSON" in result["error_log"][0]

    def test_fails_closed_when_no_exchange_profile_configured(self):
        """BL-56: the agent fails closed if no exchange_profile pattern rules are configured."""
        node = SchemaFormatValidateNode(required_fields=[], resource_id_pattern=None, date_pattern=None)
        result = node.execute(_state([{"resource_id": "RES-001"}]))
        assert result["status"] == "error"

    def test_duplicate_resource_id_is_critical(self):
        result = self.node.execute(
            _state(
                [
                    {"resource_id": "RES-001", "title": "First"},
                    {"resource_id": "RES-001", "title": "Second"},
                ]
            )
        )
        finding = next(f for f in result["schema_findings"] if f["rule_id"] == "SCHEMA-005")
        assert finding["severity"] == "critical"
