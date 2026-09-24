# EDU-C2-042 — Unit Tests: DomainRuleValidateNode (BL-57..BL-60)

from src.nodes.domain_rule_validate_node import DomainRuleValidateNode

SUBJECT_CODES = ["MATH"]
GRADE_CODES = ["G5"]
CONTROLLED_VOCAB = {"licence": ["CC-BY-4.0"], "language": ["ja"], "format": ["pdf"]}


def _state(records: list[dict]) -> dict:
    return {"resource_records": records}


class TestDomainRuleValidateNode:
    def setup_method(self):
        self.node = DomainRuleValidateNode(SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, {})

    def test_success_path_no_findings(self):
        """BL-57: a record fully within configured tables produces no findings."""
        record = {
            "resource_id": "R1",
            "subject_code": "MATH",
            "grade_code": "G5",
            "licence": "CC-BY-4.0",
            "language": "ja",
            "format": "pdf",
        }
        result = self.node.execute(_state([record]))
        assert result["status"] == "success"
        assert result["domain_findings"] == []

    def test_finding_produced_for_invalid_subject_code(self):
        """BL-58: an out-of-list subject_code produces a DOMAIN-001 finding."""
        record = {
            "resource_id": "R1",
            "subject_code": "ART",
            "grade_code": "G5",
            "licence": "CC-BY-4.0",
            "language": "ja",
            "format": "pdf",
        }
        result = self.node.execute(_state([record]))
        assert any(f["rule_id"] == "DOMAIN-001" for f in result["domain_findings"])

    def test_empty_records_no_crash(self):
        """BL-59: an empty record list produces an empty findings list, no crash."""
        result = self.node.execute(_state([]))
        assert result["status"] == "success"
        assert result["domain_findings"] == []

    def test_fails_closed_when_no_curriculum_tables_configured(self):
        """BL-60: the agent fails closed if no curriculum code list / controlled vocabulary is configured."""
        node = DomainRuleValidateNode(
            subject_codes=[], grade_codes=[], controlled_vocabulary={}, required_descriptors_by_format={}
        )
        result = node.execute(_state([{"resource_id": "R1"}]))
        assert result["status"] == "error"
