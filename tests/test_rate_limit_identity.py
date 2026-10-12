"""QA 5.14 S-3 / D-2: rate-limit buckets can't be spoofed; setup shows no key prefix."""

from types import SimpleNamespace

import pytest


def _request(peer="203.0.113.7", headers=None, user_id=None):
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers={k.lower(): v for k, v in (headers or {}).items()},
        state=SimpleNamespace(user_id=user_id) if user_id else SimpleNamespace(),
    )


@pytest.fixture(autouse=True)
def no_proxies(monkeypatch):
    monkeypatch.delenv("REALIZE_TRUSTED_PROXIES", raising=False)


def test_client_chosen_tenant_header_is_ignored():
    from realize_api.security_middleware import _rate_limit_key

    a = _rate_limit_key(_request(headers={"X-Tenant-ID": "fresh-bucket-1"}))
    b = _rate_limit_key(_request(headers={"X-Tenant-ID": "fresh-bucket-2"}))
    assert a == b == "ip:203.0.113.7"


def test_signed_in_caller_is_limited_per_user():
    from realize_api.security_middleware import _rate_limit_key

    assert _rate_limit_key(_request(user_id="dana@acme.io")) == "user:dana@acme.io"
    assert _rate_limit_key(_request(peer="10.0.1.1", user_id="hermes")) == "user:hermes"


def test_forwarded_for_is_trusted_only_from_a_configured_proxy(monkeypatch):
    from realize_api.security_middleware import _rate_limit_key

    spoofed = _request(peer="203.0.113.7", headers={"X-Forwarded-For": "1.2.3.4"})
    assert _rate_limit_key(spoofed) == "ip:203.0.113.7"

    monkeypatch.setenv("REALIZE_TRUSTED_PROXIES", "10.0.1.0/24")
    proxied = _request(peer="10.0.1.1", headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.9"})
    assert _rate_limit_key(proxied) == "ip:198.51.100.9"  # the hop our proxy saw, not a client-written one


def test_http_limit_is_separate_from_the_llm_limit():
    from realize_core.config import API_RATE_LIMIT_PER_MINUTE
    from realize_core.utils.rate_limiter import build_rate_limiter

    assert build_rate_limiter().requests_per_minute == API_RATE_LIMIT_PER_MINUTE


def test_setup_masks_all_but_the_last_four():
    from realize_api.routes.setup import _mask_value

    key = "sk-ant-api03-abcdefghijklmnopWXYZ"
    masked = _mask_value(key)
    assert masked == "••••WXYZ"
    assert key[:4] not in masked
    assert _mask_value("short-secret") == "••••"
