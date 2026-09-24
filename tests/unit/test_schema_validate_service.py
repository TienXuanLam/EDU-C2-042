# EDU-C2-042 — Unit Tests: schema_validate_service (BL-16..BL-24)

from src.services.schema_validate_service import validate_schema

REQUIRED_FIELDS = ["resource_id", "title", "subject_code", "grade_code", "licence", "language", "format", "url"]
RESOURCE_ID_PATTERN = r"^[A-Za-z0-9._-]{3,64}$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def _valid_record(**overrides) -> dict:
    record = {
        "resource_id": "RES-001",
        "title": "Algebra Basics",
        "subject_code": "MATH",
        "grade_code": "G5",
        "licence": "CC-BY-4.0",
        "language": "ja",
        "format": "pdf",
        "url": "https://example.org/algebra",
        "date_published": "2026-01-01",
        "accessibility_descriptors": [],
    }
    record.update(overrides)
    return record


class TestValidateSchema:
    def test_clean_record_no_findings(self):
        """BL-16: a fully valid record produces no findings."""
        findings = validate_schema(_valid_record(), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert findings == []

    def test_missing_required_field(self):
        """BL-17: SCHEMA-001 fires for each missing/empty required field."""
        findings = validate_schema(_valid_record(title=""), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert any(f["rule_id"] == "SCHEMA-001" and f["field"] == "title" for f in findings)

    def test_invalid_resource_id_pattern(self):
        """BL-18: SCHEMA-002 fires when resource_id fails the exchange-profile pattern."""
        findings = validate_schema(_valid_record(resource_id="a"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert any(f["rule_id"] == "SCHEMA-002" for f in findings)

    def test_invalid_url(self):
        """BL-19: SCHEMA-003 fires for a non-http(s) or malformed URL."""
        findings = validate_schema(_valid_record(url="not-a-url"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert any(f["rule_id"] == "SCHEMA-003" for f in findings)

    def test_ftp_url_rejected(self):
        findings = validate_schema(
            _valid_record(url="ftp://example.org/x"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN
        )
        assert any(f["rule_id"] == "SCHEMA-003" for f in findings)

    def test_invalid_date_format(self):
        """BL-20: SCHEMA-004 fires for a malformed date_published."""
        findings = validate_schema(
            _valid_record(date_published="01/01/2026"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN
        )
        assert any(f["rule_id"] == "SCHEMA-004" for f in findings)

    def test_impossible_calendar_date_is_rejected(self):
        findings = validate_schema(
            _valid_record(date_published="2026-99-99"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN
        )
        assert any(f["rule_id"] == "SCHEMA-004" for f in findings)

    def test_url_credentials_are_rejected(self):
        credential_bearing_url = "https://" + "user" + ":" + "not-a-secret" + "@example.org/a"
        findings = validate_schema(
            _valid_record(url=credential_bearing_url),
            REQUIRED_FIELDS,
            RESOURCE_ID_PATTERN,
            DATE_PATTERN,
        )
        assert any(f["rule_id"] == "SCHEMA-003" for f in findings)

    def test_malformed_ipv6_url_is_rejected_without_crashing(self):
        findings = validate_schema(
            _valid_record(url="https://[invalid"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN
        )
        assert any(f["rule_id"] == "SCHEMA-003" for f in findings)

    def test_empty_date_not_flagged(self):
        """BL-21: an absent (optional) date_published is not flagged."""
        findings = validate_schema(_valid_record(date_published=""), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert not any(f["rule_id"] == "SCHEMA-004" for f in findings)

    def test_missing_resource_id_uses_placeholder(self):
        """BL-22: findings still resolve a resource_id label even when it's the missing field itself."""
        findings = validate_schema(_valid_record(resource_id=""), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN)
        assert all(f["resource_id"] == "(missing resource_id)" for f in findings)

    def test_multiple_findings_accumulate(self):
        """BL-23: multiple violations on one record all appear in the findings list."""
        findings = validate_schema(
            _valid_record(title="", url="bad"), REQUIRED_FIELDS, RESOURCE_ID_PATTERN, DATE_PATTERN
        )
        rule_ids = {f["rule_id"] for f in findings}
        assert {"SCHEMA-001", "SCHEMA-003"} <= rule_ids
