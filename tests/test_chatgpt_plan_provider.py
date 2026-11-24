"""ChatGPT plan provider (token sharing): sign-in, refresh, stream parsing, fallback.

No network: the token endpoint and the Responses call are replaced.
"""

import json
import os
import time
from urllib.parse import parse_qs, urlparse

import pytest
from realize_core.llm import chatgpt_plan
from realize_core.llm.providers.chatgpt_plan_provider import ChatGPTPlanProvider, build_body, parse_stream


def _creds(**over):
    base = {
        "client_id": "oaiapp_test",
        "ext_agent_host_id": "urn:uuid:00000000-0000-4000-8000-000000000000",
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "expires_in": 3600,
        "scope": chatgpt_plan.SCOPES,
        "saved_at": time.time(),
    }
    base.update(over)
    return chatgpt_plan.Credentials(**base)


@pytest.fixture
def signed_in(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATGPT_PLAN_MODEL", "gpt-test")
    path = tmp_path / chatgpt_plan.CREDENTIALS_FILE
    chatgpt_plan.save_credentials(_creds(), path)
    return path


def _sse(*events):
    return [f"data: {json.dumps(e)}" for e in events]


# --- sign-in -----------------------------------------------------------------


def test_authorize_url_first_registration():
    req = chatgpt_plan.build_authorize_request("urn:uuid:x", port=1455)
    q = {k: v[0] for k, v in parse_qs(urlparse(req.url).query).items()}
    assert req.url.startswith(chatgpt_plan.AUTHORIZE_URL)
    assert q["client_id"] == "dynamic_agent_client"
    assert q["agent_name_hint"] == "RealizeOS"
    assert q["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert q["scope"] == chatgpt_plan.SCOPES
    assert q["resource"] == "https://api.openai.com/v1"
    assert q["code_challenge_method"] == "S256"
    assert q["ext_agent_host_id"] == "urn:uuid:x"
    assert q["state"] == req.state
    assert q["nonce"] == req.nonce


def test_authorize_url_reauthorization_uses_issued_client_and_no_name_hint():
    req = chatgpt_plan.build_authorize_request("urn:uuid:x", client_id="oaiapp_1")
    q = parse_qs(urlparse(req.url).query)
    assert q["client_id"] == ["oaiapp_1"]
    assert "agent_name_hint" not in q
    assert req.first_registration is False


def test_pkce_challenge_matches_verifier():
    import base64
    import hashlib

    verifier, challenge = chatgpt_plan.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected
    assert "=" not in challenge


def test_exchange_requires_plan_scope(monkeypatch):
    req = chatgpt_plan.build_authorize_request("urn:uuid:x")
    monkeypatch.setattr(
        chatgpt_plan, "_token_post", lambda form: {"access_token": "a", "refresh_token": "r", "scope": "openid"}
    )
    with pytest.raises(chatgpt_plan.TokenError) as e:
        chatgpt_plan.exchange_code(req, "code", "oaiapp_1", "urn:uuid:x")
    assert e.value.code == "plan_scope_not_granted"


def test_exchange_sends_issued_client_and_verifier(monkeypatch):
    req = chatgpt_plan.build_authorize_request("urn:uuid:x")
    seen = {}

    def fake(form):
        seen.update(form)
        return {"access_token": "a", "refresh_token": "r", "scope": chatgpt_plan.SCOPES, "expires_in": 3600}

    monkeypatch.setattr(chatgpt_plan, "_token_post", fake)
    creds = chatgpt_plan.exchange_code(req, "code-1", "oaiapp_1", "urn:uuid:x")
    assert seen["client_id"] == "oaiapp_1"
    assert seen["code_verifier"] == req.verifier
    assert seen["redirect_uri"] == req.redirect_uri
    assert seen["resource"] == chatgpt_plan.RESOURCE
    assert creds.client_id == "oaiapp_1"
    assert creds.has_plan_scope()


def test_credentials_file_is_private(tmp_path):
    path = tmp_path / "c.json"
    chatgpt_plan.save_credentials(_creds(), path)
    assert chatgpt_plan.load_credentials(path).refresh_token == "rt-1"
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_host_id_is_created_once(tmp_path):
    first = chatgpt_plan.host_id(tmp_path)
    assert first.startswith("urn:uuid:")
    assert chatgpt_plan.host_id(tmp_path) == first


# --- refresh -----------------------------------------------------------------


def test_refresh_rotates_and_saves(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    chatgpt_plan.save_credentials(_creds(saved_at=time.time() - 4000), path)
    monkeypatch.setattr(
        chatgpt_plan, "_token_post", lambda form: {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600}
    )
    assert chatgpt_plan.valid_access_token(path) == "at-2"
    saved = chatgpt_plan.load_credentials(path)
    assert saved.refresh_token == "rt-2"
    assert saved.access_valid()


def test_terminal_refresh_error_marks_reauth(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    chatgpt_plan.save_credentials(_creds(saved_at=0), path)

    def fail(form):
        raise chatgpt_plan.TokenError("refresh_token_reused", 400)

    monkeypatch.setattr(chatgpt_plan, "_token_post", fail)
    with pytest.raises(chatgpt_plan.ReauthRequiredError):
        chatgpt_plan.valid_access_token(path)
    assert chatgpt_plan.load_credentials(path).needs_reauth is True


def test_valid_token_is_not_refreshed(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    chatgpt_plan.save_credentials(_creds(), path)
    monkeypatch.setattr(chatgpt_plan, "_token_post", lambda form: pytest.fail("refreshed a valid token"))
    assert chatgpt_plan.valid_access_token(path) == "at-1"


# --- request body and stream ---------------------------------------------------


def test_body_has_only_accepted_fields():
    body = build_body(
        "be brief",
        [
            {"role": "system", "content": "dropped"},
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": "hello"},
        ],
        "gpt-test",
    )
    assert body == {
        "model": "gpt-test",
        "input": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        "store": False,
        "stream": True,
        "instructions": "be brief",
    }


def test_stream_success_needs_completed_event():
    text, usage, err = parse_stream(
        _sse(
            {"type": "response.output_text.delta", "delta": "Hel"},
            {"type": "response.output_text.delta", "delta": "lo"},
            {"type": "response.completed", "response": {"usage": {"input_tokens": 5, "output_tokens": 2}}},
        )
    )
    assert (text, err, usage["output_tokens"]) == ("Hello", None, 2)
    _, _, err = parse_stream(_sse({"type": "response.output_text.delta", "delta": "Hel"}))
    assert err == "stream_ended_without_completion"


def test_stream_failed_event_gives_code():
    _, _, err = parse_stream(
        _sse({"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_unavailable"}}})
    )
    assert err == "subscription_sharing_usage_unavailable"


# --- provider ------------------------------------------------------------------


async def test_complete_costs_nothing(signed_in, monkeypatch):
    provider = ChatGPTPlanProvider(credentials_file=signed_in)

    async def fake_post(body, token, timeout):
        assert token == "at-1"
        assert body["store"] is False
        assert body["stream"] is True
        return 200, "ok", {"input_tokens": 3, "output_tokens": 1}, None

    monkeypatch.setattr(provider, "_post", fake_post)
    response = await provider.complete("s", [{"role": "user", "content": "q"}])
    assert response.ok
    assert response.text == "ok"
    assert response.cost_usd == 0.0
    assert response.provider == "chatgpt_plan"
    assert response.model == "gpt-test"


async def test_usage_limit_pauses_and_hides_the_provider(signed_in, monkeypatch):
    provider = ChatGPTPlanProvider(credentials_file=signed_in)
    assert provider.is_available()

    async def limited(body, token, timeout):
        return 429, "", {}, "subscription_sharing_usage_limit_exceeded"

    monkeypatch.setattr(provider, "_post", limited)
    response = await provider.complete("s", [{"role": "user", "content": "q"}])
    assert not response.ok
    assert "usage_limit" in response.error
    assert provider.is_available() is False  # the router now goes to the fallback chain


async def test_not_eligible_disables(signed_in, monkeypatch):
    provider = ChatGPTPlanProvider(credentials_file=signed_in)

    async def denied(body, token, timeout):
        return 403, "", {}, "subscription_sharing_user_not_eligible"

    monkeypatch.setattr(provider, "_post", denied)
    await provider.complete("s", [{"role": "user", "content": "q"}])
    assert provider.is_available() is False
    assert "subscription_sharing_user_not_eligible" in provider.model_errors().values()


async def test_401_forces_one_refresh_then_succeeds(signed_in, monkeypatch):
    provider = ChatGPTPlanProvider(credentials_file=signed_in)
    monkeypatch.setattr(
        chatgpt_plan, "_token_post", lambda form: {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600}
    )
    calls = []

    async def post(body, token, timeout):
        calls.append(token)
        if token == "at-1":
            return 401, "", {}, "subscription_sharing_invalid_user"
        return 200, "ok", {}, None

    monkeypatch.setattr(provider, "_post", post)
    response = await provider.complete("s", [{"role": "user", "content": "q"}])
    assert response.ok
    assert calls == ["at-1", "at-2"]


def test_unavailable_without_sign_in_or_model(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATGPT_PLAN_MODEL", "gpt-test")
    assert ChatGPTPlanProvider(credentials_file=tmp_path / "none.json").is_available() is False
    monkeypatch.delenv("CHATGPT_PLAN_MODEL")
    path = tmp_path / "c.json"
    chatgpt_plan.save_credentials(_creds(), path)
    assert ChatGPTPlanProvider(credentials_file=path).is_available() is False


async def test_router_falls_back_when_the_plan_is_limited(signed_in, monkeypatch):
    """Primary = chatgpt_plan; on a usage limit the next provider answers."""
    from realize_core.llm import router
    from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse
    from realize_core.llm.registry import ProviderRegistry

    class Cheap(BaseLLMProvider):
        @property
        def name(self):
            return "gemini"

        async def complete(self, system_prompt, messages, model=None, **kw):
            return LLMResponse(text="cheap", model="flash-lite", provider="gemini", cost_usd=0.001)

        def list_models(self):
            return []

    plan = ChatGPTPlanProvider(credentials_file=signed_in)

    async def limited(body, token, timeout):
        return 429, "", {}, "subscription_sharing_usage_limit_exceeded"

    monkeypatch.setattr(plan, "_post", limited)
    registry = ProviderRegistry()
    registry.register(plan)
    registry.register(Cheap())
    monkeypatch.setenv("LLM_PRIMARY", "chatgpt_plan")
    monkeypatch.setenv("LLM_FALLBACK", "gemini")
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    registry.set_fallback_chain(registry._resolve_fallback_chain())
    monkeypatch.setattr("realize_core.llm.registry.get_registry", lambda: registry)
    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)

    first = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert first.ok
    assert first.text == "cheap"
    second = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert second.text == "cheap"  # plan paused: not even tried
