"""AgentCore Platform v1.0"""

# S-2/S-3 defense-in-depth (InputNormaliseNode._extra_security_gate_input /
# ReportHandoffNode._extra_security_gate_output): this template processes
# resource discovery metadata only (proposal §3) — never learner/student
# records or assessment data. Risk #4 (proposal §11): "Accidental PII
# leakage if an institution's exchange profile embeds learner identifiers in
# resource records (e.g., creator/rights holder fields containing personal
# names)". Two independent checks, mirroring the same identifier-scan
# pattern used elsewhere in the fleet for this template's structured
# catalogue-export input shape:
#   1. forbidden key names anywhere in the raw payload text (structural —
#      catches a caller who embeds learner records in the export)
#   2. an email-address pattern anywhere in the raw payload text (catches an
#      identifier embedded in a value rather than a key)

from __future__ import annotations

import re

_FORBIDDEN_KEYS = frozenset(
    {
        "student_name",
        "student_id",
        "learner_id",
        "learner_name",
        "full_name",
        "email",
        "guardian_name",
        "date_of_birth",
    }
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+")

# Free-text cue phrases for scanning generated prose (remediation hints /
# final report), where the structural key-name check does not apply —
# defense-in-depth in case the LLM (full_remediation mode) echoes an
# apparent learner identifier from a record field into its hint text.
_TEXT_CUE_RE = re.compile(r"(?i:student\s*(name|id)|learner\s*(name|id)|date\s*of\s*birth|\bDOB\b)")


def contains_learner_identifier(raw_text: str) -> bool:
    """Return True if raw_text (catalogue payload) appears to carry learner-level data."""
    raw_text = raw_text or ""
    if _EMAIL_RE.search(raw_text):
        return True
    lowered = raw_text.lower()
    return any(key in lowered for key in _FORBIDDEN_KEYS)


def contains_learner_identifier_text(text: str) -> bool:
    """S-3 defense-in-depth: scan generated prose (remediation hints / report) for
    signs it leaked learner-level data despite upstream metadata-only scope."""
    text = text or ""
    return bool(_EMAIL_RE.search(text) or _TEXT_CUE_RE.search(text))
