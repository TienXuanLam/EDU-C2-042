# EDU-C2-042 — Unit Tests: domain_rule_service (BL-25..BL-34)

from src.services.domain_rule_service import validate_domain_rules

SUBJECT_CODES = ["MATH", "SCI"]
GRADE_CODES = ["G5", "G6"]
CONTROLLED_VOCAB = {
    "licence": ["CC-BY-4.0"],
    "language": ["ja", "en"],
    "format": ["pdf", "video"],
}
REQUIRED_DESCRIPTORS = {"video": ["captions"], "image": ["alt_text"]}


def _valid_record(**overrides) -> dict:
    record = {
        "resource_id": "RES-001",
        "subject_code": "MATH",
        "grade_code": "G5",
        "licence": "CC-BY-4.0",
        "language": "ja",
        "format": "pdf",
        "accessibility_descriptors": [],
    }
    record.update(overrides)
    return record


class TestValidateDomainRules:
    def test_clean_record_no_findings(self):
        """BL-25: a record fully within the curriculum/vocabulary tables produces no findings."""
        findings = validate_domain_rules(
            _valid_record(), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert findings == []

    def test_invalid_subject_code(self):
        """BL-26: DOMAIN-001 fires for a subject_code not in the curriculum code list."""
        findings = validate_domain_rules(
            _valid_record(subject_code="ART"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert any(f["rule_id"] == "DOMAIN-001" for f in findings)

    def test_invalid_grade_code(self):
        """BL-27: DOMAIN-002 fires for a grade_code not in the curriculum code list."""
        findings = validate_domain_rules(
            _valid_record(grade_code="G12"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert any(f["rule_id"] == "DOMAIN-002" for f in findings)

    def test_invalid_licence(self):
        """BL-28: DOMAIN-003 fires for a licence not in the controlled vocabulary."""
        findings = validate_domain_rules(
            _valid_record(licence="UNKNOWN"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert any(f["rule_id"] == "DOMAIN-003" for f in findings)

    def test_invalid_language(self):
        """BL-29: DOMAIN-004 fires for a language not in the controlled vocabulary."""
        findings = validate_domain_rules(
            _valid_record(language="fr"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert any(f["rule_id"] == "DOMAIN-004" for f in findings)

    def test_invalid_format(self):
        """BL-30: DOMAIN-005 fires for a format not in the controlled vocabulary."""
        findings = validate_domain_rules(
            _valid_record(format="epub"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert any(f["rule_id"] == "DOMAIN-005" for f in findings)

    def test_missing_accessibility_descriptor(self):
        """BL-31: DOMAIN-006 fires when a required descriptor is missing for the record's format."""
        findings = validate_domain_rules(
            _valid_record(format="video", accessibility_descriptors=[]),
            SUBJECT_CODES,
            GRADE_CODES,
            CONTROLLED_VOCAB,
            REQUIRED_DESCRIPTORS,
        )
        assert any(f["rule_id"] == "DOMAIN-006" for f in findings)

    def test_accessibility_descriptor_present_no_finding(self):
        """BL-32: DOMAIN-006 does not fire when the required descriptor is present."""
        findings = validate_domain_rules(
            _valid_record(format="video", accessibility_descriptors=["captions"]),
            SUBJECT_CODES,
            GRADE_CODES,
            CONTROLLED_VOCAB,
            REQUIRED_DESCRIPTORS,
        )
        assert not any(f["rule_id"] == "DOMAIN-006" for f in findings)

    def test_format_not_in_vocab_skips_accessibility_check(self):
        """BL-33: an invalid format short-circuits the accessibility-descriptor check (DOMAIN-005 only)."""
        findings = validate_domain_rules(
            _valid_record(format="epub", accessibility_descriptors=[]),
            SUBJECT_CODES,
            GRADE_CODES,
            CONTROLLED_VOCAB,
            REQUIRED_DESCRIPTORS,
        )
        rule_ids = {f["rule_id"] for f in findings}
        assert rule_ids == {"DOMAIN-005"}

    def test_format_with_no_accessibility_requirement(self):
        """BL-34: a format with no entry in required_descriptors_by_format never triggers DOMAIN-006."""
        findings = validate_domain_rules(
            _valid_record(format="pdf"), SUBJECT_CODES, GRADE_CODES, CONTROLLED_VOCAB, REQUIRED_DESCRIPTORS
        )
        assert not any(f["rule_id"] == "DOMAIN-006" for f in findings)
