# EDU-C2-042 — Integration Tests: HTTP entry point (endpoint-level trust gate)
#
# Uses FastAPI's TestClient against the real src.api.server.app — no live
# socket, but exercises the actual /invoke handler (INVOKE_AUTH_TOKEN check,
# ctx construction, agent.invoke()) rather than only unit-testing individual
# nodes. Complements tests/unit/test_report_handoff_node.py's node-level
# trust-gate test (unit tests can't prove the endpoint itself enforces auth).

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INVOKE_AUTH_TOKEN", "test-endpoint-token")
    # Re-import fresh so the module-level `agent`/token read happens under
    # this fixture's env var (src.api.server reads INVOKE_AUTH_TOKEN
    # per-request inside the handler, not at import time, so a plain import
    # is sufficient here — no importlib.reload needed).
    from src.api.server import app

    return TestClient(app)


def _payload(mode: str = "rules_only") -> dict:
    return {
        "input": json.dumps(
            {
                "source_format": "json",
                "profile_version": "2026.1-illustrative",
                "mode": mode,
                "payload": json.dumps(
                    [
                        {
                            "resource_id": "RES-001",
                            "title": "Algebra Basics",
                            "subject_code": "MATH",
                            "grade_code": "G5",
                            "licence": "CC-BY-4.0",
                            "language": "ja",
                            "format": "pdf",
                            "url": "https://example.org/algebra",
                        }
                    ]
                ),
            }
        ),
        "session_id": "test-session",
    }


def test_health_endpoint_no_auth_required(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_invoke_without_token_returns_401(client):
    """Anonymous caller with no bearer token must be rejected at the
    entry-point boundary (before any node runs), not silently downgraded."""
    resp = client.post("/invoke", json=_payload())
    assert resp.status_code == 401


def test_invoke_with_wrong_token_returns_401(client):
    resp = client.post("/invoke", json=_payload(), headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_invoke_with_correct_token_reaches_the_agent(client):
    """With a valid bearer token the caller runs at VERIFIED_EXTERNAL and the
    request reaches the agent. rules_only mode needs no LLM, so this also
    proves the full pipeline (no Azure OpenAI credentials configured in this
    test environment) succeeds end-to-end via the real HTTP entry point.

    Note: config/config.yaml's illustrative exchange_profile.version
    ("2026.1-illustrative") must match _payload()'s profile_version — the
    server reads config/config.yaml directly at import time (module-level
    code in src/api/server.py), so this is a real integration check of that
    wiring, not a mock.
    """
    resp = client.post("/invoke", json=_payload("rules_only"), headers={"Authorization": "Bearer test-endpoint-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "InitializeNode" in body["node_history"]
    assert "InputNormaliseNode" in body["node_history"]


def test_invoke_with_object_input_and_real_json_payload_reaches_the_agent(client):
    """The caller can send `input` as a real JSON object, with `payload` as
    a real JSON array (no hand-escaping of nested JSON-as-a-string) — the
    server normalises this into the single string BaseGraph.invoke()
    requires. Must produce the same result as the equivalent
    fully-pre-escaped string payload in _payload() above."""
    request_body = {
        "input": {
            "source_format": "json",
            "profile_version": "2026.1-illustrative",
            "mode": "rules_only",
            "payload": [
                {
                    "resource_id": "RES-002",
                    "title": "Biology Basics",
                    "subject_code": "SCI",
                    "grade_code": "G5",
                    "licence": "CC-BY-4.0",
                    "language": "ja",
                    "format": "pdf",
                    "url": "https://example.org/biology",
                }
            ],
        },
        "session_id": "test-session-object-input",
    }
    resp = client.post("/invoke", json=request_body, headers={"Authorization": "Bearer test-endpoint-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "InputNormaliseNode" in body["node_history"]


def test_invoke_with_object_input_and_non_json_source_format_fails_closed(client):
    """A caller sending `payload` as a real JSON array while declaring
    source_format="csv" gets a clear, non-crashing rejection -- the server
    only re-stringifies a dict/list payload, it never inspects
    source_format itself; parse_catalogue's own CSV parser surfaces the
    mismatch instead of silently misparsing."""
    request_body = {
        "input": {
            "source_format": "csv",
            "profile_version": "2026.1-illustrative",
            "mode": "rules_only",
            "payload": [{"resource_id": "RES-003"}],
        },
        "session_id": "test-session-bad-format",
    }
    resp = client.post("/invoke", json=request_body, headers={"Authorization": "Bearer test-endpoint-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
