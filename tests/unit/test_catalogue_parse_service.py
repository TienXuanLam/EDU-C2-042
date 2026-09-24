# EDU-C2-042 — Unit Tests: catalogue_parse_service (BL-01..BL-12)

import pytest

from src.services.catalogue_parse_service import CatalogueSyntaxError, parse_catalogue


class TestParseJsonRecords:
    def test_success_path(self):
        """BL-01: valid JSON list is parsed and normalized."""
        payload = '[{"resource_id": "R1", "title": "T1", "subject_code": "MATH", "grade_code": "G5", "licence": "CC-BY-4.0", "language": "ja", "format": "pdf", "url": "https://example.org/r1", "accessibility_descriptors": ["alt_text"]}]'
        records, errors = parse_catalogue("json", payload)
        assert len(records) == 1
        assert errors == []
        assert records[0]["resource_id"] == "R1"
        assert records[0]["accessibility_descriptors"] == ["alt_text"]

    def test_records_wrapper_object_accepted(self):
        """BL-02: {'records': [...]} wrapper is also accepted."""
        payload = '{"records": [{"resource_id": "R1"}]}'
        records, errors = parse_catalogue("json", payload)
        assert len(records) == 1

    def test_malformed_json_raises(self):
        """BL-03: whole-batch syntax failure raises CatalogueSyntaxError."""
        with pytest.raises(CatalogueSyntaxError):
            parse_catalogue("json", "not json at all")

    def test_non_object_entry_quarantined(self):
        """BL-04: a non-object entry is quarantined, not a whole-batch failure."""
        payload = '[{"resource_id": "R1"}, "not an object"]'
        records, errors = parse_catalogue("json", payload)
        assert len(records) == 1
        assert len(errors) == 1
        assert errors[0]["record_index"] == 1

    def test_accessibility_descriptors_pipe_string_split(self):
        payload = '[{"resource_id": "R1", "accessibility_descriptors": "captions|alt_text"}]'
        records, _ = parse_catalogue("json", payload)
        assert records[0]["accessibility_descriptors"] == ["captions", "alt_text"]

    def test_wrong_top_level_type_raises(self):
        with pytest.raises(CatalogueSyntaxError):
            parse_catalogue("json", '{"not_records": 1}')

    def test_missing_resource_id_is_quarantined(self):
        records, errors = parse_catalogue("json", '[{"title": "No identifier"}]')
        assert records == []
        assert errors[0]["reason"] == "missing resource_id"

    def test_oversized_payload_is_rejected(self, monkeypatch):
        monkeypatch.setattr("src.services.catalogue_parse_service.MAX_PAYLOAD_BYTES", 10)
        with pytest.raises(CatalogueSyntaxError, match="payload exceeds"):
            parse_catalogue("json", '[{"resource_id":"R1"}]')


class TestParseCsvRecords:
    def test_success_path(self):
        """BL-05: valid CSV with header row is parsed."""
        payload = "resource_id,title,subject_code,grade_code,licence,language,format,url,accessibility_descriptors\nR1,T1,MATH,G5,CC-BY-4.0,ja,pdf,https://example.org/r1,captions|alt_text\n"
        records, errors = parse_catalogue("csv", payload)
        assert len(records) == 1
        assert errors == []
        assert records[0]["resource_id"] == "R1"
        assert records[0]["accessibility_descriptors"] == ["captions", "alt_text"]

    def test_missing_resource_id_quarantined(self):
        """BL-06: a row without resource_id is quarantined, not a whole-batch failure."""
        payload = "resource_id,title\n,T1\n"
        records, errors = parse_catalogue("csv", payload)
        assert records == []
        assert len(errors) == 1

    def test_no_header_row_raises(self):
        with pytest.raises(CatalogueSyntaxError):
            parse_catalogue("csv", "")

    def test_duplicate_headers_raise(self):
        with pytest.raises(CatalogueSyntaxError, match="duplicate header"):
            parse_catalogue("csv", "resource_id,resource_id\nR1,R2\n")


class TestParseXmlRecords:
    def test_success_path(self):
        """BL-07: valid XML catalogue with resource elements is parsed."""
        payload = (
            '<catalogue><resource id="R1">'
            "<title>T1</title><subject_code>MATH</subject_code><grade_code>G5</grade_code>"
            "<licence>CC-BY-4.0</licence><language>ja</language><format>pdf</format>"
            "<url>https://example.org/r1</url>"
            "<accessibility_descriptors><descriptor>captions</descriptor></accessibility_descriptors>"
            "</resource></catalogue>"
        )
        records, errors = parse_catalogue("xml", payload)
        assert len(records) == 1
        assert errors == []
        assert records[0]["resource_id"] == "R1"
        assert records[0]["accessibility_descriptors"] == ["captions"]

    def test_missing_id_attribute_quarantined(self):
        """BL-08: a <resource> without id attribute is quarantined."""
        payload = "<catalogue><resource><title>T1</title></resource></catalogue>"
        records, errors = parse_catalogue("xml", payload)
        assert records == []
        assert len(errors) == 1

    def test_malformed_xml_raises(self):
        with pytest.raises(CatalogueSyntaxError):
            parse_catalogue("xml", "<catalogue><resource>")


class TestUnsupportedFormat:
    def test_unsupported_format_raises(self):
        """BL-09: an unsupported source_format raises CatalogueSyntaxError."""
        with pytest.raises(CatalogueSyntaxError):
            parse_catalogue("yaml", "irrelevant")
