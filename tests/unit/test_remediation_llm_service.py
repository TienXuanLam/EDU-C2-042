# EDU-C2-042 — Unit Tests: remediation_llm_service (BL-35..BL-38, BL-81)

import pytest

from src.services.remediation_llm_service import generate_remediation_hint


class _FakeLLM:
    def __init__(self, response):
        self._response = response
        self.last_messages = None

    def complete(self, messages):
        self.last_messages = messages
        return self._response


FINDINGS = [
    {"rule_id": "SCHEMA-001", "field": "title", "severity": "critical", "message": "required field 'title' is missing"}
]


class TestGenerateRemediationHint:
    def test_dict_response_returns_content(self):
        """BL-35: a dict-shaped LLM response returns its 'content' field."""
        llm = _FakeLLM({"content": "Add a title to this resource.", "model": "mock"})
        hint = generate_remediation_hint(llm, "RES-001", FINDINGS)
        assert hint == "Add a title to this resource."

    def test_string_response_returned_as_is(self):
        """BL-36: a bare string response is returned unchanged."""
        llm = _FakeLLM("Add a title to this resource.")
        hint = generate_remediation_hint(llm, "RES-001", FINDINGS)
        assert hint == "Add a title to this resource."

    def test_default_system_prompt_included(self):
        """BL-37: the default system prompt is sent unless explicitly overridden."""
        llm = _FakeLLM({"content": "ok"})
        generate_remediation_hint(llm, "RES-001", FINDINGS)
        assert llm.last_messages[0]["role"] == "system"
        assert "personally identifiable" in llm.last_messages[0]["content"]

    def test_empty_system_prompt_omits_system_turn(self):
        """BL-38: passing "" explicitly omits the system turn."""
        llm = _FakeLLM({"content": "ok"})
        generate_remediation_hint(llm, "RES-001", FINDINGS, system_prompt="")
        assert llm.last_messages[0]["role"] == "user"

    def test_findings_included_in_prompt(self):
        llm = _FakeLLM({"content": "ok"})
        generate_remediation_hint(llm, "RES-001", FINDINGS)
        user_content = llm.last_messages[-1]["content"]
        assert "SCHEMA-001" in user_content
        assert "RES-001" in user_content

    def test_title_never_reaches_prompt(self):
        """BL-81 — review finding T1-01 regression: generate_remediation_hint() has no
        title parameter at all, so an adversarial/prompt-injection-style title
        cannot appear in either the system or user message, regardless of what
        the caller's catalogue record contained. Bounded-evidence boundary:
        only resource_id + deterministic findings reach the LLM."""
        llm = _FakeLLM({"content": "ok"})
        generate_remediation_hint(llm, "RES-001", FINDINGS)
        all_content = " ".join(m["content"] for m in llm.last_messages)
        assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in all_content

    def test_oversized_hint_is_rejected(self):
        llm = _FakeLLM({"content": "x" * 1_001})
        with pytest.raises(ValueError, match="exceeds"):
            generate_remediation_hint(llm, "RES-001", FINDINGS)
