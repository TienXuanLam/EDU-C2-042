"""AgentCore Platform v1.0"""

# Pure domain logic for proposal §4 step 3 (Domain Rule Validation).
# No LLM, no agenticstar/framework imports — testable in isolation.
#
# Per the Design Decision Record (docs/02_design.md): whether a subject/
# grade code is valid against the curriculum code list, whether a licence/
# language/format value is in the controlled vocabulary, and whether the
# accessibility descriptors satisfy the profile's minimum requirement for a
# resource's format are all deterministic, config-driven judgments — never
# LLM-arbitrated (same principle applied to a compliance_gap_service.py used elsewhere in the fleet).

from __future__ import annotations

from typing import Any

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


def validate_domain_rules(
    record: dict[str, Any],
    subject_codes: list[str],
    grade_codes: list[str],
    controlled_vocabulary: dict[str, list[str]],
    required_descriptors_by_format: dict[str, list[str]],
) -> list[dict[str, str]]:
    """Deterministic curriculum-code / controlled-vocabulary / accessibility checks.

    Rule IDs:
      DOMAIN-001 subject_code not in the curriculum code list
      DOMAIN-002 grade_code not in the curriculum code list
      DOMAIN-003 licence not in the controlled vocabulary
      DOMAIN-004 language not in the controlled vocabulary
      DOMAIN-005 format not in the controlled vocabulary
      DOMAIN-006 accessibility_descriptors missing a descriptor required for this format
    """
    resource_id = record.get("resource_id", "") or "(missing resource_id)"
    findings: list[dict[str, str]] = []

    subject_code = record.get("subject_code", "")
    if subject_code and subject_code not in subject_codes:
        findings.append(
            _finding(
                resource_id,
                "DOMAIN-001",
                "subject_code",
                _SEVERITY_CRITICAL,
                f"subject_code '{subject_code}' is not in the curriculum code list",
            )
        )

    grade_code = record.get("grade_code", "")
    if grade_code and grade_code not in grade_codes:
        findings.append(
            _finding(
                resource_id,
                "DOMAIN-002",
                "grade_code",
                _SEVERITY_CRITICAL,
                f"grade_code '{grade_code}' is not in the curriculum code list",
            )
        )

    licence = record.get("licence", "")
    if licence and licence not in controlled_vocabulary.get("licence", []):
        findings.append(
            _finding(
                resource_id,
                "DOMAIN-003",
                "licence",
                _SEVERITY_WARNING,
                f"licence '{licence}' is not in the controlled vocabulary",
            )
        )

    language = record.get("language", "")
    if language and language not in controlled_vocabulary.get("language", []):
        findings.append(
            _finding(
                resource_id,
                "DOMAIN-004",
                "language",
                _SEVERITY_WARNING,
                f"language '{language}' is not in the controlled vocabulary",
            )
        )

    fmt = record.get("format", "")
    if fmt and fmt not in controlled_vocabulary.get("format", []):
        findings.append(
            _finding(
                resource_id,
                "DOMAIN-005",
                "format",
                _SEVERITY_CRITICAL,
                f"format '{fmt}' is not in the controlled vocabulary",
            )
        )
    elif fmt:
        required = set(required_descriptors_by_format.get(fmt, []))
        present = set(record.get("accessibility_descriptors", []))
        missing = sorted(required - present)
        if missing:
            findings.append(
                _finding(
                    resource_id,
                    "DOMAIN-006",
                    "accessibility_descriptors",
                    _SEVERITY_WARNING,
                    f"missing required accessibility descriptor(s) for format '{fmt}': {missing}",
                )
            )

    return findings
