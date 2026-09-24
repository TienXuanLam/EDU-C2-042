"""AgentCore Platform v1.0"""

# Outer post_process node (docs/02_design.md — proposal §4 step 5: Report &
# Human Handoff). Assembles the structured per-record findings + remediation
# hints + summary stats into a Markdown report, attaches the mandatory
# advisory disclaimer (this template is strictly read-only/advisory — never
# publishes, licenses, or transmits any resource, proposal §3), and re-scans
# the generated text for accidental learner-identifier leakage (S-3) before
# it leaves the node boundary — the LLM output (full_remediation mode) is
# not proposal-guaranteed clean, even though the upstream data is resource
# metadata only.

from __future__ import annotations

import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.learner_pii_scan import contains_learner_identifier_text

DISCLAIMER = (
    "\n\n---\n**Advisory only — AI-assisted draft.** This report is read-only "
    "guidance; it does not publish, licence, modify, or transmit any resource "
    "or catalogue record. The curriculum coordinator / data officer must "
    "verify findings and remediation hints before acting on them."
)


def _safe_markdown(value: object) -> str:
    """Render untrusted/configured text without allowing Markdown structure injection."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value))
    text = " ".join(text.splitlines())
    return re.sub(r"([\\`*_{}\[\]()<>#+|~])", r"\\\1", text)


def _record_verdict(
    resource_id: str,
    schema_findings: list[dict[str, Any]],
    domain_findings: list[dict[str, Any]],
) -> str:
    findings = [f for f in schema_findings + domain_findings if f["resource_id"] == resource_id]
    if any(f["severity"] == "critical" for f in findings):
        return "fail"
    if findings:
        return "warn"
    return "pass"


def _render_report(state: AgentState) -> str:
    records = state.get("resource_records", [])
    schema_findings = state.get("schema_findings", [])
    domain_findings = state.get("domain_findings", [])
    remediation_hints = {str(h["resource_id"]): h["hint"] for h in state.get("remediation_hints", [])}
    ingest_errors = state.get("ingest_errors", [])
    remediation_mode = state.get("remediation_mode", "rules_only")

    verdicts = [
        _record_verdict(str(record.get("resource_id", "")), schema_findings, domain_findings) for record in records
    ]
    pass_count = verdicts.count("pass")
    warn_count = verdicts.count("warn")
    fail_count = verdicts.count("fail")

    lines = [
        "# Learning-Resource Metadata Exchange Validation Report",
        f"*Profile version: {_safe_markdown(state.get('profile_version', ''))} · "
        f"Source format: {_safe_markdown(state.get('source_format', ''))} · "
        f"Remediation mode: {_safe_markdown(remediation_mode)}*",
        "",
        "## Summary",
        "",
        f"- Records validated: {len(records)}",
        f"- Pass: {pass_count} · Warn: {warn_count} · Fail: {fail_count}",
        f"- Quarantined at ingest (malformed entries): {len(ingest_errors)}",
        "",
        "## Per-Record Findings",
        "",
    ]

    if not records:
        lines.append("(no records)")
    for record, verdict in zip(records, verdicts, strict=True):
        resource_id = str(record.get("resource_id", ""))
        lines.append(f"### {_safe_markdown(resource_id)} — {_safe_markdown(record.get('title', ''))} [{verdict}]")
        record_findings = [f for f in schema_findings + domain_findings if f["resource_id"] == resource_id]
        if record_findings:
            for f in record_findings:
                lines.append(
                    f"- [{_safe_markdown(f['severity'])}] {_safe_markdown(f['rule_id'])} "
                    f"({_safe_markdown(f['field'])}): {_safe_markdown(f['message'])}"
                )
        else:
            lines.append("- (no findings)")
        if resource_id in remediation_hints:
            lines.append(f"- **Remediation hint:** {_safe_markdown(remediation_hints[resource_id])}")
        lines.append("")

    if ingest_errors:
        lines += ["## Quarantined Entries (rejected at ingest, not scored)", ""]
        for err in ingest_errors:
            lines.append(
                f"- record_index {_safe_markdown(err.get('record_index'))}: {_safe_markdown(err.get('reason'))}"
            )

    return "\n".join(lines)


class ReportHandoffNode(FunctionNode):
    """Finalize the validation report and attach the mandatory advisory disclaimer."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        if contains_learner_identifier_text(str(result.get("final_report_markdown", ""))):
            raise RuntimeError(
                "ReportHandoffNode: S-3 rejected output — apparent learner-level "
                "identifier detected in generated report"
            )
        return result

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("status") == AgentStatus.ERROR.value:
            return {"status": AgentStatus.ERROR.value}

        markdown = _render_report(state) + DISCLAIMER

        emit_trace_event(
            "validation_report_finalized",
            {
                "record_count": len(state.get("resource_records", [])),
                "remediation_mode": state.get("remediation_mode", ""),
            },
            state,
        )

        return {
            "final_report_markdown": markdown,
            "formatted_output": markdown,
            "status": AgentStatus.SUCCESS.value,
        }
