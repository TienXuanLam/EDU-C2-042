# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `EducationLearningResourceMetadataExchangeValidatorAgent`
- **L1 Base**: `AgentBaseGraph`
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible), `src/schemas/state.py`
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

> Section citations below (e.g. "§4", "§12") refer to `docs/01_proposal.md`.

The proposal (§4) lists five steps — Input
Normalisation, Schema & Format Validation, Domain Rule Validation, LLM Remediation Generation,
Report & Human Handoff — more than `AgentBaseGraph`'s three fixed slots (`pre_process` / `main` /
`post_process`). Per the current scaffold convention (`src/examples/graph_cat2_sample.py`,
supersedes the older step-helper pattern described in some historical playbook notes — confirmed
against a sibling project elsewhere in the fleet, already implemented on this convention), the three
middle steps are encapsulated in an inner `BaseGraph` wrapped by a `GraphNode` in the outer
`main` slot:

```
Outer graph (src/graph/graph.py):
    AgentBaseGraph — fixed backbone, add_edges() NOT overridden.
    pre_process  = InputNormaliseNode                     (proposal step 1)
    main         = RecordValidationWorkflowGraphNode       (GraphNode wrapping the inner graph)
    post_process = ReportHandoffNode                       (proposal step 5)

Inner graph (src/graph/domain_workflow_graph.py):
    RecordValidationWorkflowGraph(BaseGraph) — fully custom topology.
    schema_format_validate (step 2) -> domain_rule_validate (step 3)
        -> {route: remediation_mode} -> remediation_generate (step 4, LLM) -> END
                                      -> END directly (rules_only mode — see below)
```

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | `InputNormaliseNode` — parse JSON/XML/CSV envelope, validate profile_version, normalise records, quarantine malformed entries (S-2 learner-PII defense-in-depth) | `user_input` | `source_format`, `profile_version`, `remediation_mode`, `resource_records`, `ingest_errors`, `validated_input` | FunctionNode |
| main | `RecordValidationWorkflowGraphNode` — wraps the inner 3-step graph | `validated_input` | `schema_findings`, `domain_findings`, `remediation_hints` | GraphNode |
| ↳ schema_format_validate | Required fields, resource_id pattern, URL syntax, date format (`config/config.yaml` `exchange_profile`) | `user_input` (forwarded JSON) | `schema_findings` | FunctionNode (inner) |
| ↳ domain_rule_validate | Subject/grade codes vs curriculum code list; licence/language/format vs controlled vocabulary; accessibility descriptors vs profile | `resource_records` | `domain_findings` | FunctionNode (inner) |
| ↳ remediation_generate | LLM-draft per-record remediation hints from findings only (skipped in `rules_only` mode) | `schema_findings`, `domain_findings` | `remediation_hints` | FunctionNode (inner) |
| post_process | `ReportHandoffNode` — assemble Markdown report (per-record findings, severity, remediation hints, summary stats), attach mandatory advisory disclaimer, S-3 re-scan | `resource_records`, `schema_findings`, `domain_findings`, `remediation_hints` | `final_report_markdown`, `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry)
                                          pre_process
```

### `rules_only` mode — not explicit in the source proposal, added during implementation

The source proposal's workflow (§4) always ends in an LLM remediation-generation step (step 4),
with no explicit LLM-free path. That makes the pipeline impossible to exercise end-to-end
(Stage ⑤ STG smoke test / CI `run-tests`) without real Azure OpenAI credentials. Mirroring
a `deterministic_only` mode precedent used elsewhere in the fleet, `InputNormaliseNode` accepts an optional
`mode` field in the caller envelope (`"full_remediation"` default, or `"rules_only"`): in
`rules_only` mode the inner graph routes straight from `domain_rule_validate` to `END`, skipping
`remediation_generate` entirely, and `ReportHandoffNode` renders the schema/domain findings
directly without remediation hints. This is also a genuinely useful standalone capability (a
data officer can get the raw rule-finding report without waiting on/paying for an LLM call), not
only a test-support shim.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `source_format` | `str` | `"json"` \| `"xml"` \| `"csv"` | pre_process |
| `profile_version` | `str` | Caller-declared profile version, must match `config/config.yaml exchange_profile.version` | pre_process |
| `remediation_mode` | `str` | `"full_remediation"` (LLM hints) or `"rules_only"` (no LLM) | pre_process |
| `resource_records` | `list[dict]` | Normalised canonical records: `resource_id`, `title`, `subject_code`, `grade_code`, `licence`, `language`, `format`, `url`, `date_published`, `accessibility_descriptors` (`list[str]`) | pre_process |
| `ingest_errors` | `list[dict]` | Quarantined malformed entries: `record_index`, `reason` | pre_process |
| `schema_findings` | `list[dict]` | `resource_id`, `rule_id`, `field`, `severity`, `message` | main (inner: schema_format_validate) |
| `domain_findings` | `list[dict]` | Same shape as `schema_findings` | main (inner: domain_rule_validate) |
| `remediation_hints` | `list[dict]` | `resource_id`, `hint` (empty list in `rules_only` mode) | main (inner: remediation_generate) |
| `final_report_markdown` | `str` | Final report + mandatory advisory disclaimer | post_process |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — `resource_records`/`*_findings`/
  `remediation_hints` are `list[dict]` of primitives (or `list[str]` nested one level for
  `accessibility_descriptors`) only, no nested objects.
- No JWT, API keys, credentials in State (checkpoint DB leakage).
- No student/learner names, IDs, or other individual identifiers in State (proposal §3) —
  defense-in-depth enforced by `InputNormaliseNode._extra_security_gate_input()` (S-2) and
  `ReportHandoffNode._extra_security_gate_output()` (S-3), even though this template's approved
  scope is resource discovery metadata only.
- `InvocationContext` rule: `RemediationGenerateNode` obtains its Azure OpenAI credentials via
  `InvocationContext.from_state(state)` inside `execute()` only (see Framework Utilization below),
  and never stores them in State.
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible).

## Framework Utilization

### Proposal step-label vs. framework S-layer mapping

The source proposal's own workflow diagram (§4) labels steps "(S-1)"/"(S-2)"/"(S-3)" as a
domain-risk shorthand — these are **not** literally the framework's S-1 Trust Gate / S-2 Input
Security Gate / S-3 Output Security Gate layers. The actual mapping used in this
implementation:

| Proposal label | Proposal step | Actual framework layer |
|---|---|---|
| "(S-1)" | Step 1 Input Normalisation | Business validation in `InputNormaliseNode.execute()` (parse/reject malformed payload) — framework S-1 (Trust Gate, `required_trust_level`) is a separate, always-on caller-identity check |
| "(S-2)" | Step 2 Schema & Format Validation | Deterministic business rule (`schema_validate_service.py`), not the framework's S-2 input gate hook — the actual S-2 hook (`_extra_security_gate_input()`) is used for the learner-PII defense-in-depth check on `InputNormaliseNode`, per Risk #4 |
| "(S-3)" | Step 4 LLM Remediation Generation | The actual S-3 hook (`_extra_security_gate_output()`) is implemented on `ReportHandoffNode` (post_process, step 5), not on the LLM node itself — output screening happens once, on the final assembled report text |

### Shared Components Used
- [x] `InvocationContext.from_state(state)` — used by `RemediationGenerateNode._build_llm()`,
      which resolves `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_DEPLOYMENT`
      per-invocation and constructs a fresh `AzureOpenAIClient` for each call, matching the
      fleet-standard pattern used elsewhere in the fleet. No client is built at server
      startup or held as module/instance state.
- [ ] ConnectionPolicy (retry/timeout strategy) — not used; no external service beyond the LLM.
- [ ] SecurityViolationError — not explicitly raised; S-2 rejection sets `status=ERROR` +
      `error_log` (framework convention per `customize-security-gates.md`), S-3 rejection
      raises `RuntimeError` (matches an `OutputValidateNode` precedent used elsewhere in the fleet).
- [x] S-2: `_extra_security_gate_input()` — `InputNormaliseNode` rejects any raw payload that
      appears to carry a learner/student identifier key or an email-address pattern
      (`src/services/learner_pii_scan.py::contains_learner_identifier`) — defense-in-depth per
      Risk #4, even though the approved scope is resource metadata only.
- [x] S-3: `_extra_security_gate_output()` — `ReportHandoffNode` re-scans the finalized report
      text for the same learner-identifier signal, expressed as free-text cue phrases since the
      output is prose (`contains_learner_identifier_text`) — defense-in-depth in case the LLM
      (`full_remediation` mode) echoes an apparent learner identifier from a record field into
      its hint text.
- [x] S-4: `emit_trace_event()` — every node emits at least one domain event
      (`catalogue_ingested`, `schema_format_validated`, `domain_rules_validated`,
      `remediation_generated`, `validation_report_finalized`).

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `RecordValidationWorkflowGraphNode` wraps
  `RecordValidationWorkflowGraph` (inner `BaseGraph`).
- **Composition target**: `src/graph/domain_workflow_graph.py`
- **Error propagation strategy**: `propagate` (default) — an inner-graph error surfaces as
  `SubgraphError` in the outer graph; fail fast, no silent partial validation report.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)

## Known Limitation — Framework S-2 Title-Case Masking (confirmed via e2e testing)

The framework's mandatory, unconditional S-2 gate (`framework/nodes/function_node.py`
`FunctionNode._security_gate_input()`, `@final` — cannot be overridden) scans
`state["user_input"]` and `state["validated_input"]` on **every** `FunctionNode` with
`shared.security.pii_detector.detect_pii()` before `execute()` or this template's own
`_extra_security_gate_input()` hook ever runs. Its `"name"` pattern
(`\b[A-Z][a-z]{1,20}(?:\s[A-Z][a-z]{1,20})+\b`) matches **any** two-or-more consecutive Title
Case words and replaces the match with `"[MASKED]"` in place — the detector's own docstring
warns "high recall and low precision... any two or more consecutive Title Case words match".

This was discovered through real end-to-end testing (`tests/integration/test_graph.py::
test_framework_s2_title_masking_is_cosmetic_only`), not a hypothetical: a resource `title` like
`"Algebra Basics"` arrives at `InputNormaliseNode.execute()` (reading `state["user_input"]`) and
at `SchemaFormatValidateNode.execute()` (reading the forwarded `validated_input` as inner
`state["user_input"]`) already replaced with `"[MASKED]"` — this template cannot recover the
original text, and cannot disable or narrow this framework-level scan (it is not the same as, and
runs strictly before, `InputNormaliseNode`'s own `_extra_security_gate_input()` learner-PII check).

**Confirmed non-impact on validation correctness**: `schema_validate_service.py::validate_schema`
only checks that `title` is non-empty (`SCHEMA-001`) — it never inspects `title`'s content — so a
masked title never produces a false rule finding; every other validated field (`resource_id`,
`subject_code`, `grade_code`, `licence`, `language`, `format`, `url`, `date_published`) is
structured/coded data (uppercase codes, snake_case, URLs, ISO dates) that does not match the
Title Case `name` pattern in this template's own config/test fixtures. **Confirmed impact**: the
human-readable `title` field in the final report may show `"[MASKED]"` instead of the real
resource title whenever the title contains 2+ consecutive Title Case words (a common case for
natural-language English titles) — this is a report-display limitation, not a compliance-logic
defect. Documented here rather than silently accepted; see the regression test above for the
executable proof.

## Known Limitation — Profile/Curriculum-Code/Vocabulary Values Are Illustrative, Not Sourced Institutional Data

`config/config.yaml`'s `exchange_profile`, `curriculum_code_list`, `controlled_vocabulary`, and
`accessibility_profile` dicts are illustrative representative values chosen by the implementing
engineer to make the pipeline runnable end-to-end — at proposal time (§12 Dependencies 1–3) none
of these existed as concrete, approved artefacts from any real institution, MEXT, or publisher.
See README.md Known Limitations. Every deploying institution must supply and review its own
approved profile/code-list/vocabulary pack before relying on the generated report for real
cross-institution or cross-publisher exchange decisions — this matches the source proposal's own
§5 mitigation ("profile-configuration pack model: each institution supplies a versioned profile
pack; canonical internal model is profile-agnostic; profile-specific test fixtures are required
for each pack"). Both `InputNormaliseNode` (profile_version) and the inner graph's
`SchemaFormatValidateNode`/`DomainRuleValidateNode` (pattern/code-list/vocabulary presence)
fail closed (`status=error`) when the corresponding config is absent, per proposal §4 Notes:
"The agent fails closed if the approved profile version, rule tables, or vocabulary tables are
absent."

## Risk Mitigation Mapping (proposal §11)

| # | Risk | Mitigation in this implementation |
|---|------|-----------------------------------|
| 1 | Controlled-vocabulary/curriculum-code tables become stale | Config-driven (`config/config.yaml`), versioned (`version` field per table); `InputNormaliseNode`/`SchemaFormatValidateNode`/`DomainRuleValidateNode` fail closed when a table is absent (see Known Limitation above) |
| 2 | LLM hallucinates policy/fabricates codes/licence values, or a caller embeds prompt-injection content in free-text catalogue fields | `RemediationGenerateNode` passes only `resource_id` + already-computed rule findings to `generate_remediation_hint()` (`remediation_llm_service.py::_build_prompt`) — **no raw catalogue field, including `title`, ever reaches the prompt** (review finding T1-01, fixed; regression-tested at service/node/e2e level: `test_remediation_llm_service.py::test_title_never_reaches_prompt`, `test_remediation_generate_node.py::test_adversarial_title_never_reaches_llm_prompt`, `test_graph.py::test_adversarial_title_never_reaches_llm_end_to_end`). Rule pass/fail/severity is always deterministic (`schema_validate_service.py`/`domain_rule_service.py`), never LLM-arbitrated — Design Decision Record below |
| 3 | Institution exchange profiles vary widely, single canonical model brittle | Canonical record model is profile-agnostic (`catalogue_parse_service.py`); institution-specific rules live entirely in `config/config.yaml`, not in code |
| 4 | Accidental learner-identifier leakage if a profile embeds learner data in resource fields | S-2 defense-in-depth on `InputNormaliseNode` + S-3 defense-in-depth on `ReportHandoffNode` (`learner_pii_scan.py`) |
| 5 | Standards interpretation differences (QTI/LOM/SCORM/xAPI) | Institution-approved profile (`exchange_profile`) is the sole operative source; rule findings cite `rule_id`; unsupported `source_format` is rejected explicitly, not guessed |
| 6 | Large catalogue exports exhaust memory or time | Payloads above 2,000,000 UTF-8 bytes or 10,000 records are rejected before workflow execution; callers must batch larger exports |

## Migration Hardening Boundaries

- The complete exchange/curriculum/vocabulary/accessibility pack is validated during graph
  compilation. Missing sections, invalid regexes, duplicate code values, or unknown accessibility
  references raise `ConfigError`; nodes retain defensive fail-closed checks.
- JSON, XML, and CSV enforce the same record limit and field-size rules. Records without a
  `resource_id` are quarantined consistently; duplicate CSV headers are rejected.
- `SCHEMA-004` validates an actual ISO calendar date, not only its textual shape. URLs containing
  embedded credentials are rejected. `SCHEMA-005` marks duplicate resource IDs critical.
- Report counts are per input record, including duplicate IDs. All dynamic report values are
  flattened to one line and Markdown metacharacters are escaped, preventing caller or LLM text
  from creating forged report sections.
- LLM remediation remains advisory and findings-only; responses above 1,000 characters or with
  unsafe control characters fail closed.

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed 5-step pipeline determined entirely by input catalogue data — no autonomous think→act loop needed |
| Composition pattern | Step-helper (pure-Python, 3 `FunctionNode`s) | GraphNode + inner `BaseGraph` | **GraphNode + inner graph** | Current scaffold convention (`src/examples/graph_cat2_sample.py`); matches a precedent used elsewhere in the fleet (confirmed by direct inspection of that already-implemented sibling project) |
| Rule validation logic location | LLM-arbitrated (single remediation prompt does everything) | Deterministic Python (`schema_validate_service.py`/`domain_rule_service.py`), LLM only for prose | **Deterministic Python** | Which records pass/fail, and against which rule, are exchange-compliance-material judgments — must not be LLM-arbitrated, same principle applied to a `compliance_gap_service.py` used elsewhere in the fleet |
| LLM-free execution path | None (always require LLM) | Add `rules_only` mode | **Added `rules_only` mode** | Without it, the pipeline cannot be exercised in CI/Stage ⑤ STG without real Azure OpenAI credentials; also independently useful (raw rule-finding report without LLM cost/latency) |
| Missing dependency (exchange profile / curriculum code list / controlled vocabulary) handling | Block implementation until real institutional data supplied | Use representative illustrative config values, document clearly, fail closed if absent at runtime | **Representative illustrative values** | Confirmed with user before implementation began; matches proposal's own framing of Dependencies 1-3 as pre-implementation entry criteria rather than hard blockers, and its own Risk #3 mitigation (config-driven, institution-overridable pack) |
| Malformed individual catalogue entry handling | Hard reject whole batch | Quarantine the entry into `ingest_errors`, continue processing the rest | **Quarantine, don't reject whole batch** | Proposal §4 step 1 explicitly: "reject/quarantine malformed payloads" — one bad row/element should not block validation of an entire institution's export |
