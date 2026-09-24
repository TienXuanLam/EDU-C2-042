"""AgentCore Platform v1.0"""

# Pure domain logic for proposal §4 step 2 (Schema & Format Validation).
# No LLM, no agenticstar/framework imports — testable in isolation.
#
# Per the Design Decision Record (docs/02_design.md, same principle applied
# to a compliance_gap_service.py used elsewhere in the fleet): required-field
# presence, ID/URL/date syntax are structural, deterministic judgments —
# never LLM-arbitrated.

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

_SEVERITY_CRITICAL = "critical"
_SEVERITY_WARNING = "warning"


def _finding(resource_id: str, rule_id: str, field: str, severity: str, message: str) -> dict[str, str]:
    return {
        "resource_id": resource_id,
        "rule_id": rule_id,
        "field": field,
        "severity": severity,
        "message": message,
    }


def _is_valid_url(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return bool(
            parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
        )
    except (TypeError, ValueError):
        return False


def validate_schema(
    record: dict[str, Any],
    required_fields: list[str],
    resource_id_pattern: str,
    date_pattern: str,
) -> list[dict[str, str]]:
    """Deterministic schema/format checks for one canonical record.

    Rule IDs:
      SCHEMA-001 missing required field
      SCHEMA-002 resource_id does not match the exchange-profile pattern
      SCHEMA-003 url is not syntactically valid (http/https + host)
      SCHEMA-004 date_published present but not YYYY-MM-DD
    """
    resource_id = record.get("resource_id", "") or "(missing resource_id)"
    findings: list[dict[str, str]] = []

    for field in required_fields:
        value = record.get(field, "")
        if not str(value).strip():
            findings.append(
                _finding(
                    resource_id,
                    "SCHEMA-001",
                    field,
                    _SEVERITY_CRITICAL,
                    f"required field '{field}' is missing or empty",
                )
            )

    rid = record.get("resource_id", "")
    if rid and not re.fullmatch(resource_id_pattern, str(rid)):
        findings.append(
            _finding(
                resource_id,
                "SCHEMA-002",
                "resource_id",
                _SEVERITY_CRITICAL,
                f"resource_id '{rid}' does not match the exchange-profile pattern {resource_id_pattern!r}",
            )
        )

    url = record.get("url", "")
    if url and not _is_valid_url(url):
        findings.append(
            _finding(resource_id, "SCHEMA-003", "url", _SEVERITY_CRITICAL, f"url '{url}' is not a valid http(s) URL")
        )

    date_value = record.get("date_published", "")
    if date_value:
        valid_date = bool(re.fullmatch(date_pattern, str(date_value)))
        if valid_date:
            try:
                date.fromisoformat(str(date_value))
            except ValueError:
                valid_date = False
        if not valid_date:
            findings.append(
                _finding(
                    resource_id,
                    "SCHEMA-004",
                    "date_published",
                    _SEVERITY_WARNING,
                    f"date_published '{date_value}' is not a valid date matching {date_pattern!r}",
                )
            )

    return findings
