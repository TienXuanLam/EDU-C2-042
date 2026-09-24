# EDU-C2-042 — Unit Tests: ReportHandoffNode (BL-66..BL-72)

from framework.schemas.trust_level import TrustLevel
from src.nodes.report_handoff_node import ReportHandoffNode

RECORDS = [{"resource_id": "R1", "title": "Algebra"}]
SCHEMA_FINDINGS = [
    {"resource_id": "R1", "rule_id": "SCHEMA-001", "field": "title", "severity": "critical", "message": "missing title"}
]


def _state(**overrides) -> dict:
    state = {
        "status": "success",
        "resource_records": RECORDS,
        "schema_findings": SCHEMA_FINDINGS,
        "domain_findings": [],
        "remediation_hints": [],
        "ingest_errors": [],
        "remediation_mode": "rules_only",
        "profile_version": "2026.1-illustrative",
        "source_format": "json",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "correlation_id": "test-corr",
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


class TestReportHandoffNode:
    def setup_method(self):
        self.node = ReportHandoffNode()

    def test_success_path_renders_report_with_disclaimer(self):
        """BL-66: report is rendered with per-record findings and the mandatory disclaimer."""
        result = self.node.execute(_state())
        assert result["status"] == "success"
        assert "R1" in result["final_report_markdown"]
        assert "SCHEMA-001" in result["final_report_markdown"]
        assert "Advisory only" in result["final_report_markdown"]

    def test_upstream_error_short_circuits(self):
        """BL-67: an upstream error status is passed through without rendering."""
        result = self.node.execute(_state(status="error"))
        assert result == {"status": "error"}

    def test_record_with_no_findings_marked_pass(self):
        """BL-68: a record with zero findings is rendered as [pass]."""
        result = self.node.execute(_state(schema_findings=[], domain_findings=[]))
        assert "[pass]" in result["final_report_markdown"]

    def test_record_with_critical_finding_marked_fail(self):
        """BL-69: a record with a critical finding is rendered as [fail]."""
        result = self.node.execute(_state())
        assert "[fail]" in result["final_report_markdown"]

    def test_remediation_hint_included_when_present(self):
        """BL-70: a remediation hint for a record appears in its section."""
        result = self.node.execute(_state(remediation_hints=[{"resource_id": "R1", "hint": "Add a title."}]))
        assert "Add a title." in result["final_report_markdown"]

    def test_s3_rejects_unsafe_output(self):
        """BL-71: S-3 hook raises RuntimeError when the rendered report leaks a learner identifier."""
        node = ReportHandoffNode()
        import pytest

        with pytest.raises(RuntimeError):
            node._extra_security_gate_output({"final_report_markdown": "Contact the student ID owner."})

    def test_trust_gate_rejects_anonymous_caller(self):
        """BL-72 (TC-08): calling via __call__() enforces the trust gate for an insufficiently trusted caller."""
        result = self.node(_state(caller_trust_level=TrustLevel.ANONYMOUS.value))
        assert result["status"] == "error"

    def test_untrusted_newlines_cannot_inject_report_sections(self):
        records = [{"resource_id": "R1", "title": "Safe\n## Forged Summary"}]
        result = self.node.execute(_state(resource_records=records))
        assert "\n## Forged Summary" not in result["final_report_markdown"]

    def test_duplicate_ids_are_counted_per_record(self):
        records = [{"resource_id": "R1", "title": "One"}, {"resource_id": "R1", "title": "Two"}]
        result = self.node.execute(_state(resource_records=records))
        assert "Fail: 2" in result["final_report_markdown"]
