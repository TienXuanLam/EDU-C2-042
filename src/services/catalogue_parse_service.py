"""AgentCore Platform v1.0"""

# Pure parsing/normalisation logic for proposal §4 step 1 (Input
# Normalisation). No LLM, no agenticstar/framework imports — testable in
# isolation. Dispatches on source_format (json/xml/csv) and maps every
# resource entry to the canonical record shape used by every downstream
# step:
#   resource_id, title, subject_code, grade_code, licence, language,
#   format, url, date_published, accessibility_descriptors (list[str])
#
# A malformed *individual* entry (missing id, unparseable row/element) is
# quarantined into ingest_errors and skipped — it does NOT reject the whole
# batch (proposal §4 step 1: "reject/quarantine malformed payloads"). Only a
# payload that fails to parse as valid JSON/XML/CSV *at all* is a hard
# failure — the caller must resubmit.

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from typing import Any

MAX_PAYLOAD_BYTES = 2_000_000
MAX_RECORDS = 10_000
MAX_FIELD_CHARS = 4_096
MAX_DESCRIPTORS = 100

_CANONICAL_FIELDS = (
    "resource_id",
    "title",
    "subject_code",
    "grade_code",
    "licence",
    "language",
    "format",
    "url",
    "date_published",
)


class CatalogueSyntaxError(Exception):
    """Raised when the payload is not valid JSON/XML/CSV at all (whole-batch failure)."""


def _text(value: object) -> str:
    text = "" if value is None else str(value)
    if len(text) > MAX_FIELD_CHARS:
        raise ValueError(f"field exceeds {MAX_FIELD_CHARS} characters")
    return text


def _normalise_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a raw parsed entry into the canonical record shape (strings + list[str])."""
    record: dict[str, Any] = {}
    for field in _CANONICAL_FIELDS:
        value = raw.get(field, "")
        record[field] = _text(value)

    descriptors = raw.get("accessibility_descriptors", [])
    if isinstance(descriptors, str):
        descriptors = [_text(d).strip() for d in descriptors.split("|") if d.strip()]
    elif isinstance(descriptors, list):
        descriptors = [_text(d).strip() for d in descriptors if str(d).strip()]
    else:
        descriptors = []
    if len(descriptors) > MAX_DESCRIPTORS:
        raise ValueError(f"accessibility_descriptors exceeds {MAX_DESCRIPTORS} entries")
    record["accessibility_descriptors"] = descriptors
    return record


def _parse_json_records(payload: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        data = json.loads(payload) if payload.strip() else []
    except json.JSONDecodeError as exc:
        raise CatalogueSyntaxError(f"invalid JSON payload: {exc}") from exc

    raw_records = data.get("records") if isinstance(data, dict) else data
    if not isinstance(raw_records, list):
        raise CatalogueSyntaxError("JSON payload must be a list of records or {'records': [...]}")

    if len(raw_records) > MAX_RECORDS:
        raise CatalogueSyntaxError(f"JSON payload exceeds {MAX_RECORDS} records")
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_records):
        if not isinstance(entry, dict):
            errors.append({"record_index": idx, "reason": "entry is not a JSON object"})
            continue
        try:
            record = _normalise_entry(entry)
        except ValueError as exc:
            errors.append({"record_index": idx, "reason": str(exc)})
            continue
        if not record["resource_id"].strip():
            errors.append({"record_index": idx, "reason": "missing resource_id"})
            continue
        records.append(record)
    return records, errors


def _parse_csv_records(payload: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        reader = csv.DictReader(io.StringIO(payload))
        rows = list(reader)
    except csv.Error as exc:
        raise CatalogueSyntaxError(f"invalid CSV payload: {exc}") from exc

    if reader.fieldnames is None:
        raise CatalogueSyntaxError("CSV payload has no header row")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise CatalogueSyntaxError("CSV payload contains duplicate header names")
    if len(rows) > MAX_RECORDS:
        raise CatalogueSyntaxError(f"CSV payload exceeds {MAX_RECORDS} records")

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not (row.get("resource_id") or "").strip():
            errors.append({"record_index": idx, "reason": "missing resource_id column value"})
            continue
        try:
            records.append(_normalise_entry(row))
        except ValueError as exc:
            errors.append({"record_index": idx, "reason": str(exc)})
    return records, errors


def _parse_xml_records(payload: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        root = ET.fromstring(payload)  # noqa: S314 — stdlib ET does not resolve external entities
    except ET.ParseError as exc:
        raise CatalogueSyntaxError(f"invalid XML payload: {exc}") from exc

    elements = root.findall("resource")
    if len(elements) > MAX_RECORDS:
        raise CatalogueSyntaxError(f"XML payload exceeds {MAX_RECORDS} records")
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, elem in enumerate(elements):
        resource_id = elem.get("id", "")
        if not resource_id:
            errors.append({"record_index": idx, "reason": "<resource> missing required 'id' attribute"})
            continue

        entry: dict[str, Any] = {"resource_id": resource_id}
        for field in _CANONICAL_FIELDS:
            if field == "resource_id":
                continue
            child = elem.find(field)
            entry[field] = child.text if child is not None and child.text else ""

        descriptors_elem = elem.find("accessibility_descriptors")
        descriptors = []
        if descriptors_elem is not None:
            descriptors = [d.text for d in descriptors_elem.findall("descriptor") if d.text]
        entry["accessibility_descriptors"] = descriptors

        try:
            records.append(_normalise_entry(entry))
        except ValueError as exc:
            errors.append({"record_index": idx, "reason": str(exc)})
    return records, errors


def parse_catalogue(source_format: str, payload: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse payload per source_format ("json"|"xml"|"csv") into (records, ingest_errors).

    Raises CatalogueSyntaxError on whole-batch parse failure or an
    unsupported source_format.
    """
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise CatalogueSyntaxError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    if source_format == "json":
        return _parse_json_records(payload)
    if source_format == "csv":
        return _parse_csv_records(payload)
    if source_format == "xml":
        return _parse_xml_records(payload)
    raise CatalogueSyntaxError(f"unsupported source_format: {source_format!r}")
