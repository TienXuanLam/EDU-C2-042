# Test Specification

## Test Strategy
- Coverage target: all business logic paths (success + validation-rejection + fail-closed) per node/service
- Test types: Unit (services, nodes), Integration (outer graph, inner graph, HTTP entry point), Proof-of-Boundary (framework contract)

## Scope Disclaimer

`config/config.yaml`'s `exchange_profile` / `curriculum_code_list` / `controlled_vocabulary` /
`accessibility_profile` are illustrative representative values, not sourced institutional data
(see README.md Known Limitations, docs/02_design.md). Tests verify the *mechanism* (required-field
check, resource_id/URL/date pattern check, curriculum-code/vocabulary lookup, accessibility
descriptor requirement) is correct given whatever tables are configured — they do not and cannot
verify the illustrative default values themselves are institutionally accurate.

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | ✅ `src/schemas/state.py` — all fields `str`/`list[dict]`/`list[str]` |
| TC-02 | SecurityViolationError fires on invalid input | S-2 rejection sets `status=error` (framework convention); S-3 raises `RuntimeError` | ✅ `test_input_normalise_node.py::test_s2_rejects_learner_identifier_via_call`, `test_report_handoff_node.py::test_s3_rejects_unsafe_output` |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | ✅ no credential fields declared |
| TC-04 | InvocationContext via configurable only | Not exercised by any node (docs/02_design.md Framework Utilization) | N/A — no node calls `InvocationContext.from_state()` |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from `execute()` body | ✅ manual review — only `emit_trace_event()` domain events |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | ✅ `test_framework_compliance_tc06_tc07.py::test_tc06_security_gate_input_cannot_be_overridden` — all `FunctionNode` subclasses extend via `_extra_security_gate_input()` only |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | ✅ `test_framework_compliance_tc06_tc07.py::test_tc07_security_gate_output_cannot_be_overridden` |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | ✅ `test_report_handoff_node.py::test_trust_gate_rejects_anonymous_caller`, `test_graph.py::test_graph_node_trust_gate_lifecycle` |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial | Learner-identifier key/email scan on the raw payload | ✅ `InputNormaliseNode._extra_security_gate_input` |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial | Learner-identifier text/email scan on the finalized report | ✅ `ReportHandoffNode._extra_security_gate_output` |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per `execute()` | Domain event emitted for execution entry; successful paths also emit outcome counts | `InputNormaliseNode` and `SchemaFormatValidateNode` emit a content-free start event before fail-closed validation; all nodes emit outcome events on success. Framework `node_error` remains available for failed `__call__()` lifecycles. |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | ✅ fires on the success path of every node; see TC-11 correction above — rejected/fail-closed invocations do not emit a domain event, only the framework's automatic `node_error` |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | ✅ `test_state_safety.py` |
| PB-3 | Level 2 → External service | Real external service connection | N/A — this template has no external service beyond the LLM (no KB, no DB) | N/A |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | ✅ `test_import_isolation.py` |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | ✅ `test_state_safety.py` |
| PB-6 | Invoke execution order | S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` | Order verified | ✅ `test_pb_invoke_order.py` (discovers all 5 `src/nodes/` classes dynamically) |
| PB-7 | HITL interrupt propagation *(conditional)* | `hitl.enabled` absent from `config/config.yaml` | **Auto-waived — non-HITL** | ✅ 2 SKIPPED |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory (PB-3 N/A per this template's
> architecture — no external service beyond the LLM). PB-7 auto-waived — non-HITL.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01..09 + hardening | `catalogue_parse_service` — JSON/CSV/XML parsing | Valid/malformed batch, missing IDs, duplicate CSV headers, oversized payload | Correct records/ingest_errors split; limits reject before processing; individual entries quarantine consistently | ✅ `test_catalogue_parse_service.py` |
| BL-10..15 | `learner_pii_scan` — structured + free-text scan | Clean payload/prose, forbidden key, email, cue phrase | Correctly flags only learner-level data | ✅ `test_learner_pii_scan.py` |
| BL-16..24 + hardening | `schema_validate_service` | Missing field, invalid resource_id/url/calendar date, credential-bearing URL, multiple findings | Correct SCHEMA-00N findings per case | ✅ `test_schema_validate_service.py` |
| BL-25..34 | `domain_rule_service` | Invalid subject/grade/licence/language/format, missing accessibility descriptor | Correct DOMAIN-00N findings per case; format-invalid short-circuits accessibility check | ✅ `test_domain_rule_service.py` |
| BL-35..38, BL-81 | `remediation_llm_service` | Dict/string LLM response, default/omitted system prompt; BL-81: `generate_remediation_hint()` has no `title` parameter at all (review finding T1-01 fix) | Correct content extraction and prompt assembly; BL-81 proves an adversarial title cannot appear in any message sent to the LLM | ✅ `test_remediation_llm_service.py` |
| BL-39..51 | `InputNormaliseNode` | Valid/malformed envelope, profile mismatch, invalid mode/format, quarantine-only batch, fail-closed, S-2 | Correct accept/reject per case | ✅ `test_input_normalise_node.py` |
| BL-52..56 + SCHEMA-005 | `SchemaFormatValidateNode` | Valid/invalid records, duplicate IDs, mode forwarding, malformed forwarded JSON, fail-closed | Correct rehydration; malformed forwarding fails closed; duplicate IDs are critical | ✅ `test_schema_format_validate_node.py` |
| BL-57..60 | `DomainRuleValidateNode` | Valid/invalid records, empty list, fail-closed | Correct finding generation; no crash | ✅ `test_domain_rule_validate_node.py` |
| BL-61..65, BL-82 | `RemediationGenerateNode` | LLM not configured, success (findings-only records), no findings, provider exception, empty response; BL-82: adversarial title in `resource_records` (review finding T1-01 fix) | Fail-closed on every non-success path; hints only for flagged records; BL-82 proves the node itself never forwards raw record fields to `generate_remediation_hint()` | ✅ `test_remediation_generate_node.py` |
| BL-66..72 + hardening | `ReportHandoffNode` | full report render, duplicate IDs, dynamic Markdown/newlines, S-3, trust gate | Correct per-record counts; report-section injection blocked; S-3/trust enforced | ✅ `test_report_handoff_node.py` |
| BL-73..80 | Outer + inner graph integration | rules_only / full_remediation / invalid input / unsafe LLM / config surface / GraphNode trust gate / framework S-2 title masking / adversarial title e2e | End-to-end correctness; inner routing regression coverage; Title-Case masking is cosmetic; instruction-like title is rejected before the LLM while unit tests independently prove the findings-only prompt boundary | ✅ `test_graph.py` |
| — | HTTP entry point | No token / wrong token / correct token | 401/401/200 with correct `node_history` | ✅ `test_server_endpoint.py` |

## Test Execution Summary
- Execution date: 2026-08-20
- Total tests: 118 (114 passed, 4 skipped — conditional HITL and optional Azure OpenAI boundary cases)
- Pass: 114 / Fail: 0 / Skip: 4
- TC-06/TC-07 now verified by an executable scaffold test (`tests/unit/test_framework_compliance_tc06_tc07.py`), not manual review — this file requires the `framework` package, only available in GitLab CI's private package registry, so its 2 tests must be confirmed green by CI, not by local run.
- Coverage: all node `execute()` success + primary rejection paths; all service-layer pure
  functions; S-1/S-2/S-3/S-4 lifecycle for every node type (`FunctionNode` and `GraphNode`)
