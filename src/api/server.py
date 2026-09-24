"""Standalone HTTP adapter for EDU-C2-042."""

import json
import os
import secrets
from pathlib import Path
from typing import Any, Union
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from framework.utils.config_loader import load_config
from shared.secrets import factory as secrets_factory
from shared.secrets.inmemory_provider import InMemoryProvider
from src.graph.graph import EducationLearningResourceMetadataExchangeValidatorAgent

app = FastAPI(title="Agent")

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_config = load_config(str(_CONFIG_PATH)) if _CONFIG_PATH.exists() else {}

# Standalone Podman/Docker runs inject secrets through process environment,
# while the configured provider covers platform-managed execution. Merge both
# channels into the invocation-scoped provider without exposing secret values
# to state or telemetry -- RemediationGenerateNode resolves the Azure OpenAI
# secrets per-invocation through InvocationContext, not from this
# module-level provider directly.
_configured_secrets_provider = secrets_factory(
    namespace="EDU", agent_name="EducationLearningResourceMetadataExchangeValidatorAgent"
)
_azure_secret_keys = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")
_secrets_provider = InMemoryProvider(
    {
        key: value
        for key in _azure_secret_keys
        if (value := os.environ.get(key) or _configured_secrets_provider.get(key)) is not None
    },
    namespace="EDU",
    agent_name="EducationLearningResourceMetadataExchangeValidatorAgent",
)

agent = EducationLearningResourceMetadataExchangeValidatorAgent(config=_config)
_hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
_needs_checkpointer = agent.config.get("memory_enabled") or _hitl_enabled
agent.compile(checkpointer=MemorySaver() if _needs_checkpointer else None)
agent.provision_secrets(_secrets_provider)


class InvokeRequest(BaseModel):
    # Accepts either a plain JSON string (legacy/STG payload shape) or a
    # real JSON object -- the caller never needs to hand-escape a nested
    # JSON payload as a string-within-a-string. See the /invoke handler
    # below for how a dict input is normalised into the single string
    # BaseGraph.invoke() requires.
    input: Union[str, dict[str, Any]]
    session_id: str = ""


def _bearer_matches(supplied: str, expected: str) -> bool:
    """Compare bearer credentials in constant time, including non-ASCII headers."""
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_standalone_trust(
    current: TrustLevel,
    authorization: str,
    invoke_auth_token: str | None,
    internal_runner_token: str | None,
) -> TrustLevel:
    """Map distinct standalone credentials to their exact trust levels."""
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_runner_token and _bearer_matches(authorization, internal_runner_token):
        return TrustLevel.INTERNAL
    if invoke_auth_token and _bearer_matches(authorization, invoke_auth_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if internal_runner_token or invoke_auth_token:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> Any:
    trust = _resolve_standalone_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )

    if isinstance(req.input, dict):
        envelope = dict(req.input)
        # Only source_format="json" can legitimately have `payload` as a
        # real JSON array/object here -- csv/xml payload must already be a
        # raw-text string (left untouched). A caller that mistakenly sends
        # a dict/list payload for csv/xml gets a clear CatalogueSyntaxError
        # from parse_catalogue downstream, not a silent misparse.
        payload = envelope.get("payload")
        if isinstance(payload, (dict, list)):
            envelope["payload"] = json.dumps(payload)
        user_input = json.dumps(envelope)
    else:
        user_input = req.input

    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        return agent.invoke(user_input, ctx=ctx)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "EducationLearningResourceMetadataExchangeValidatorAgent"}
