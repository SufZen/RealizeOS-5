"""STORY-12 — adversarial tests for the CodeQL-reported security fixes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# FABRIC venture resolution (py/path-injection in routes/fabric.py)
# ---------------------------------------------------------------------------


class TestFindVentureDir:
    def test_finds_systems_venture(self, tmp_path):
        from realize_core.scaffold import find_venture_dir

        (tmp_path / "systems" / "acme").mkdir(parents=True)
        assert find_venture_dir(tmp_path, "acme") == tmp_path / "systems" / "acme"

    def test_falls_back_to_legacy_ventures_root(self, tmp_path):
        from realize_core.scaffold import find_venture_dir

        (tmp_path / "ventures" / "old-biz").mkdir(parents=True)
        assert find_venture_dir(tmp_path, "old-biz") == tmp_path / "ventures" / "old-biz"

    @pytest.mark.parametrize(
        "key",
        ["", "..", "../..", "../../etc", "acme/../..", "/etc", "C:\\Windows", "acme/sub", "missing"],
    )
    def test_rejects_traversal_and_unknown(self, tmp_path, key):
        from realize_core.scaffold import find_venture_dir

        (tmp_path / "systems" / "acme" / "sub").mkdir(parents=True)
        assert find_venture_dir(tmp_path, key) is None


@pytest.fixture
def kb_client(tmp_path, monkeypatch):
    """App client whose FABRIC routes resolve ventures under ``tmp_path``."""
    from realize_api.main import create_app
    from realize_core import config

    kb = tmp_path / "kb"
    (kb / "systems" / "acme").mkdir(parents=True)
    monkeypatch.setattr(config, "KB_PATH", kb)
    return TestClient(create_app()), kb


class TestFabricRoutesNoTraversal:
    @pytest.mark.parametrize("venture", ["../../outside", "..", "nope"])
    def test_lint_unknown_or_traversal_venture_is_400_and_creates_nothing(self, kb_client, venture):
        client, kb = kb_client
        before = {p.relative_to(kb.parent) for p in kb.parent.rglob("*")}

        resp = client.post("/api/fabric/lint", params={"venture": venture})

        assert resp.status_code == 400
        after = {p.relative_to(kb.parent) for p in kb.parent.rglob("*")}
        assert after == before, f"directories were created: {sorted(after - before)}"

    def test_create_entity_in_unknown_venture_does_not_scaffold(self, kb_client):
        client, kb = kb_client

        resp = client.post(
            "/api/fabric/entities",
            json={"venture": "../../evil", "entity_type": "insight", "title": "x"},
        )

        assert resp.status_code == 400
        assert not (kb.parent / "evil").exists()
        assert not (kb / "systems" / "evil").exists()

    def test_lint_existing_venture_still_works(self, kb_client):
        client, _ = kb_client

        resp = client.post("/api/fabric/lint", params={"venture": "acme"})

        assert resp.status_code == 200
        assert resp.json()["entities_scanned"] == 0


# ---------------------------------------------------------------------------
# SSRF guard (py/full-ssrf in ingestion/extractor.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_dns(monkeypatch):
    """Resolve a few test hostnames without touching the network."""
    import socket

    table = {
        "public.test": "93.184.216.34",
        "rebind.test": "127.0.0.1",
        "intranet.test": "10.1.2.3",
        "metadata.test": "169.254.169.254",
    }

    def _getaddrinfo(host, *_args, **_kwargs):
        if host not in table:
            raise socket.gaierror(f"unknown host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)


class TestCheckUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://localhost.localdomain.invalid/",  # unresolvable → refused, not fetched
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://0.0.0.0/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "file:///etc/passwd",
            "gopher://public.test/",
            "http:///nohost",
            "http://rebind.test/",
            "http://metadata.test/",
            "http://intranet.test/",
        ],
    )
    def test_blocked_by_default(self, fake_dns, url):
        from realize_core.security.url_guard import UnsafeURLError, check_url

        with pytest.raises(UnsafeURLError):
            check_url(url)

    def test_public_host_allowed(self, fake_dns):
        from realize_core.security.url_guard import check_url

        check_url("https://public.test/page")

    def test_allow_private_permits_intranet_only(self, fake_dns):
        from realize_core.security.url_guard import UnsafeURLError, check_url

        check_url("http://intranet.test/wiki", allow_private=True)
        check_url("http://192.168.1.10/", allow_private=True)
        for url in ("http://127.0.0.1/", "http://metadata.test/", "http://169.254.169.254/"):
            with pytest.raises(UnsafeURLError):
                check_url(url, allow_private=True)


class TestGuardedGetRedirects:
    @pytest.mark.asyncio
    async def test_redirect_to_metadata_is_refused(self, fake_dns):
        import httpx
        from realize_core.security.url_guard import UnsafeURLError, guarded_get

        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

        with pytest.raises(UnsafeURLError):
            await guarded_get("http://public.test/", transport=httpx.MockTransport(handler))
        assert requested == ["http://public.test/"]  # the internal hop was never contacted

    @pytest.mark.asyncio
    async def test_public_redirect_chain_followed(self, fake_dns):
        import httpx
        from realize_core.security.url_guard import guarded_get

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(301, headers={"location": "/final"})
            return httpx.Response(200, text="ok")

        resp = await guarded_get("http://public.test/start", transport=httpx.MockTransport(handler))
        assert resp.status_code == 200
        assert resp.text == "ok"

    @pytest.mark.asyncio
    async def test_redirect_loop_stops(self, fake_dns):
        import httpx
        from realize_core.security.url_guard import UnsafeURLError, guarded_get

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "/again"})

        with pytest.raises(UnsafeURLError, match="redirects"):
            await guarded_get("http://public.test/", transport=httpx.MockTransport(handler))


class TestIngestionUsesGuard:
    @pytest.mark.asyncio
    async def test_extract_from_url_refuses_internal_host(self, fake_dns):
        from realize_core.ingestion.extractor import extract_from_url

        result = await extract_from_url("http://rebind.test/admin")
        assert "error" in result
        assert result["error"].startswith("URL not allowed")

    @pytest.mark.asyncio
    async def test_web_fetch_refuses_hostname_resolving_to_loopback(self, fake_dns):
        from realize_core.tools.web import web_fetch

        result = await web_fetch("http://rebind.test/")
        assert result.get("error", "").startswith("URL blocked")

    def test_ingestion_config_defaults_to_blocking_private(self):
        from realize_core.config import get_ingestion_config

        assert get_ingestion_config({})["allow_private_urls"] is False
        assert get_ingestion_config({"ingestion": {"allow_private_urls": True}})["allow_private_urls"] is True
