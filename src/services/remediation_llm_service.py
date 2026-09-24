"""AgentCore Platform v1.0"""

# Thin adapter over BaseLLM.complete() (shared.services.llm.base_llm) for the
# single LLM-calling node in this agent (RemediationGenerateNode). The real
# interface takes a message list and returns the canonical {"content": str,
# "tool_calls": list, "model": str, ...} dict — not the simplified
# complete(prompt: str) -> str shown in some sdk/ how-to examples.
#
# The LLM only turns already-computed rule findings into concise prose
# remediation hints (proposal §4 step 4: "advisory only") — it never
# re-derives or overrides a pass/fail/severity judgment (Design Decision
# Record, docs/02_design.md).
#
# Bounded-evidence boundary (review finding T1-01, MEDIUM): the prompt
# below intentionally carries ONLY resource_id (a caller value validated by
# SCHEMA-002's pattern check) and rule findings (deterministic Python
# output) — never the record's raw `title` or other unvalidated free-text
# fields. `title` is caller-supplied free text with no format/content
# validation (schema_validate_service only checks it is non-empty), so
# passing it into the prompt would expand the LLM's input beyond the
# claimed findings-only evidence boundary and open a prompt-injection
# surface. Do not add title (or any other unvalidated free-text field) back
# into _build_prompt() without first adding a purpose-built sanitization/
# isolation boundary and adversarial-input tests.

from __future__ import annotations

from typing import Any

DEFAULT_SYSTEM_PROMPT = (
    "You are drafting remediation guidance for an education learning-resource "
    "catalogue quality report. Use ONLY the rule findings and evidence "
    "provided for each record — never invent field values, curriculum codes, "
    "licence types, or accessibility requirements not present in the input. "
    "Do not restate or invent policy; do not include any learner/student "
    "names, IDs, or other personally identifiable information. For each "
    "record, respond with one concise, actionable remediation sentence per "
    "finding, addressed to the catalogue data owner."
)


def _build_prompt(resource_id: str, findings: list[dict[str, str]]) -> str:
    finding_lines = "\n".join(
        f"- [{f.get('severity')}] {f.get('rule_id')} ({f.get('field')}): {f.get('message')}" for f in findings
    )
    return (
        f"Resource ID: {resource_id}\n\n"
        "The following rule findings were already computed deterministically "
        "for this record (do not re-derive or dispute them):\n"
        f"{finding_lines}\n\n"
        "Draft a short remediation hint (1-3 sentences) telling the catalogue "
        "data owner exactly what to fix for this record."
    )


def generate_remediation_hint(
    llm: Any,
    resource_id: str,
    findings: list[dict[str, str]],
    system_prompt: str | None = None,
) -> str:
    """Send one record's findings to the LLM and return the remediation hint text.

    system_prompt defaults to DEFAULT_SYSTEM_PROMPT — pass "" explicitly to
    omit the system turn entirely.
    """
    system = DEFAULT_SYSTEM_PROMPT if system_prompt is None else system_prompt
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": _build_prompt(resource_id, findings)}
    ]
    response = llm.complete(messages)
    content = response.get("content", "") if isinstance(response, dict) else response
    hint = str(content).strip()
    if len(hint) > 1_000:
        raise ValueError("LLM remediation hint exceeds 1000 characters")
    if any(ord(character) < 32 and character not in "\n\t" for character in hint):
        raise ValueError("LLM remediation hint contains control characters")
    return hint
