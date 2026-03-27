"""
Integration tests for RealizeOS V5 tool ecosystem audit.

Covers:
1. Tool Registry  — auto_discover, refresh, collision detection
2. Approval System — persistence, cleanup, serialization
3. Stripe Safety  — amount validation, idempotency, error parsing, webhooks
4. Browser SSRF   — URL validation blocking private IPs / dangerous protocols
5. Web SSRF       — URL validation in web_fetch
6. MCP Health     — health_check, hub tracking
7. Google Auth    — credential clearing on refresh failure
"""

import hashlib
import hmac
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the package is importable
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. TOOL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════


class TestToolRegistry:
    """Tests for tool registry discovery, refresh, and collision detection."""

    def test_auto_discover_has_required_modules(self):
        """auto_discover must include all known tool modules."""
        from realize_core.tools.tool_registry import ToolRegistry

        _registry = ToolRegistry.__new__(ToolRegistry)  # noqa: F841
        # We need to check the hardcoded list includes the modules we added
        import inspect
        source = inspect.getsource(ToolRegistry.auto_discover)
        required = [
            "doc_generator",
            "voice",
            "telephony",
            "automation",
        ]
        for mod in required:
            assert mod in source, f"auto_discover missing module: {mod}"

    def test_refresh_clears_and_reloads(self):
        """refresh() should clear tools and re-run discovery."""
        from realize_core.tools.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._tools = {"stale_tool": MagicMock()}
        registry._action_map = {"stale_action": MagicMock()}

        with patch.object(registry, "auto_discover") as mock_discover:
            registry.refresh()
            assert registry._tools == {}
            assert registry._action_map == {}
            mock_discover.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 2. APPROVAL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalSystem:
    """Tests for approval persistence, cleanup, and JSON serialization."""

    def test_metadata_json_serialization(self):
        """Metadata must be serialized as JSON, not str()."""
        from realize_core.tools.approval import ApprovalStore

        store = ApprovalStore.__new__(ApprovalStore)
        store._db_path = None
        store._pending = {}

        # Verify that JSON serialization logic exists in _persist
        import inspect
        source = inspect.getsource(ApprovalStore._persist)
        assert "json.dumps" in source, "_persist must use json.dumps for metadata"

    def test_cleanup_expired(self):
        """cleanup_expired() must remove expired pending requests."""
        from realize_core.tools.approval import ApprovalRequest, ApprovalStatus, ApprovalStore

        store = ApprovalStore.__new__(ApprovalStore)
        store._db_path = None
        store._requests = {}

        # Create an expired request mock
        expired = MagicMock(spec=ApprovalRequest)
        expired.request_id = "test-expired"
        expired.is_expired = True
        expired.status = ApprovalStatus.PENDING

        # Create a fresh request mock
        fresh = MagicMock(spec=ApprovalRequest)
        fresh.request_id = "test-fresh"
        fresh.is_expired = False
        fresh.status = ApprovalStatus.PENDING

        store._requests = {"test-expired": expired, "test-fresh": fresh}
        count = store.cleanup_expired()

        assert count == 1
        assert "test-expired" not in store._requests
        assert "test-fresh" in store._requests

    def test_load_from_db_exists(self):
        """ApprovalStore must have a load_from_db method."""
        from realize_core.tools.approval import ApprovalStore

        assert hasattr(ApprovalStore, "load_from_db"), "Missing load_from_db method"


# ═══════════════════════════════════════════════════════════════════════════
# 3. STRIPE SAFETY
# ═══════════════════════════════════════════════════════════════════════════


class TestStripeSafety:
    """Tests for financial safety: amount validation, idempotency, error parsing."""

    def test_validate_amount_positive(self):
        """Valid amounts should pass."""
        from realize_core.tools.stripe_tools import _validate_amount

        assert _validate_amount(100) is None
        assert _validate_amount(1) is None
        assert _validate_amount(99_999_999) is None

    def test_validate_amount_rejects_zero(self):
        from realize_core.tools.stripe_tools import _validate_amount

        result = _validate_amount(0)
        assert result is not None
        assert "positive" in result.lower() or "must be" in result.lower()

    def test_validate_amount_rejects_negative(self):
        from realize_core.tools.stripe_tools import _validate_amount

        result = _validate_amount(-500)
        assert result is not None

    def test_validate_amount_rejects_too_large(self):
        from realize_core.tools.stripe_tools import _validate_amount

        result = _validate_amount(100_000_000)
        assert result is not None
        assert "exceed" in result.lower() or "maximum" in result.lower() or "large" in result.lower()

    def test_idempotency_key_deterministic(self):
        """Same inputs should always produce the same key."""
        from realize_core.tools.stripe_tools import _make_idempotency_key

        key1 = _make_idempotency_key("user@test.com", "action1")
        key2 = _make_idempotency_key("user@test.com", "action1")
        assert key1 == key2

    def test_idempotency_key_unique_for_different_inputs(self):
        from realize_core.tools.stripe_tools import _make_idempotency_key

        key1 = _make_idempotency_key("user@test.com", "action1")
        key2 = _make_idempotency_key("other@test.com", "action1")
        assert key1 != key2

    def test_parse_stripe_error(self):
        """Error parsing should extract message from Stripe error format."""
        from realize_core.tools.stripe_tools import _parse_stripe_error

        response = {
            "error": {
                "type": "card_error",
                "message": "Your card was declined.",
                "code": "card_declined",
            }
        }
        result = _parse_stripe_error(response)
        assert "declined" in result.lower()

    def test_parse_stripe_error_handles_missing_field(self):
        from realize_core.tools.stripe_tools import _parse_stripe_error

        result = _parse_stripe_error({"status": "fail"})
        assert isinstance(result, str)

    def test_verify_webhook_signature_valid(self):
        """A correctly signed webhook should pass verification."""
        from realize_core.tools.stripe_tools import verify_webhook_signature

        secret = "whsec_test_secret_key"
        payload = b'{"id":"evt_test","type":"payment_intent.succeeded"}'
        timestamp = str(int(time.time()))

        # Build signature the same way Stripe does
        signed_payload = f"{timestamp}.{payload.decode()}"
        expected_sig = hmac.new(
            secret.encode(), signed_payload.encode(), hashlib.sha256
        ).hexdigest()
        sig_header = f"t={timestamp},v1={expected_sig}"

        assert verify_webhook_signature(payload, sig_header, secret) is True

    def test_verify_webhook_signature_invalid(self):
        from realize_core.tools.stripe_tools import verify_webhook_signature

        assert (
            verify_webhook_signature(b"payload", "t=12345,v1=bad_sig", "whsec_test")
            is False
        )

    def test_verify_webhook_signature_no_secret(self):
        from realize_core.tools.stripe_tools import verify_webhook_signature

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": ""}):
            assert (
                verify_webhook_signature(b"payload", "t=12345,v1=sig", None) is False
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. BROWSER SSRF PROTECTION
# ═══════════════════════════════════════════════════════════════════════════


class TestBrowserSSRF:
    """Tests for SSRF prevention in browser.py."""

    def test_blocks_file_protocol(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("file:///etc/passwd")
        assert result is not None
        assert "blocked" in result.lower() or "file" in result.lower()

    def test_blocks_ftp_protocol(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("ftp://internal.server/data")
        assert result is not None

    def test_blocks_localhost(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("http://localhost:8080/admin")
        assert result is not None
        assert "blocked" in result.lower()

    def test_blocks_private_ip(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("http://192.168.1.1/admin")
        assert result is not None

    def test_blocks_link_local(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("http://169.254.169.254/latest/meta-data/")
        assert result is not None

    def test_blocks_metadata_google(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("http://metadata.google.internal/computeMetadata/v1/")
        assert result is not None

    def test_allows_public_urls(self):
        from realize_core.tools.browser import _validate_url

        assert _validate_url("https://www.google.com") is None
        assert _validate_url("https://example.com/path?q=1") is None

    def test_blocks_gopher_protocol(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("gopher://evil.com")
        assert result is not None

    def test_blocks_loopback_ipv4(self):
        from realize_core.tools.browser import _validate_url

        result = _validate_url("http://127.0.0.1:9200/_cat/indices")
        assert result is not None

    @pytest.mark.asyncio
    async def test_browser_navigate_blocks_ssrf(self):
        """browser_navigate should return error dict for blocked URLs."""
        from realize_core.tools.browser import browser_navigate

        result = await browser_navigate("http://169.254.169.254/latest/meta-data/")
        assert "error" in result
        assert "blocked" in result["error"].lower() or "url" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 5. WEB SSRF PROTECTION
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSSRF:
    """Tests for SSRF prevention in web.py."""

    def test_blocks_file_protocol(self):
        from realize_core.tools.web import _validate_url

        result = _validate_url("file:///etc/shadow")
        assert result is not None

    def test_blocks_private_ip(self):
        from realize_core.tools.web import _validate_url

        result = _validate_url("http://10.0.0.1/internal")
        assert result is not None

    def test_allows_public_urls(self):
        from realize_core.tools.web import _validate_url

        assert _validate_url("https://api.stripe.com/v1") is None

    @pytest.mark.asyncio
    async def test_web_fetch_blocks_ssrf(self):
        """web_fetch should return error dict for blocked URLs."""
        from realize_core.tools.web import web_fetch

        result = await web_fetch("http://192.168.0.1/admin")
        assert "error" in result
        assert "blocked" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 6. MCP HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPHealth:
    """Tests for MCP server health check and hub status tracking."""

    def test_health_check_exists(self):
        from realize_core.tools.mcp import MCPServerConnection

        assert hasattr(MCPServerConnection, "health_check")

    @pytest.mark.asyncio
    async def test_health_check_fails_when_disconnected(self):
        from realize_core.tools.mcp import MCPServerConnection

        server = MCPServerConnection(
            name="test", command="echo", args=[], env={}, enabled=True
        )
        assert await server.health_check() is False

    def test_hub_connected_count_properties(self):
        from realize_core.tools.mcp import MCPClientHub

        hub = MCPClientHub()
        assert hub.connected_count == 0
        assert hub.total_count == 0
        assert hub.fully_initialized is False

    def test_hub_fully_initialized_after_all_connect(self):
        from realize_core.tools.mcp import MCPClientHub

        hub = MCPClientHub()
        hub._initialized = True
        hub._connected_count = 3
        hub._total_count = 3
        assert hub.fully_initialized is True

    def test_hub_not_fully_initialized_on_partial(self):
        from realize_core.tools.mcp import MCPClientHub

        hub = MCPClientHub()
        hub._initialized = True
        hub._connected_count = 1
        hub._total_count = 3
        assert hub.fully_initialized is False


# ═══════════════════════════════════════════════════════════════════════════
# 7. GOOGLE AUTH CREDENTIAL HANDLING
# ═══════════════════════════════════════════════════════════════════════════


class TestGoogleAuth:
    """Tests for Google Auth credential clearing on failure."""

    def test_get_credentials_clears_on_refresh_failure(self):
        """When token refresh fails, _credentials global should be cleared."""
        # Verify the source contains the fix
        import inspect

        import realize_core.tools.google_auth as gauth
        source = inspect.getsource(gauth.get_credentials)
        # Must clear _credentials on Exception
        assert "_credentials = None" in source, (
            "get_credentials must set _credentials = None on refresh failure"
        )
        # Must not leave stale credentials
        assert "Re-run OAuth flow" in source or "re-authorize" in source.lower(), (
            "Error message should instruct user to re-authorize"
        )

    def test_module_has_required_functions(self):
        from realize_core.tools import google_auth

        assert callable(getattr(google_auth, "get_credentials", None))
        assert callable(getattr(google_auth, "_save_tokens", None))


# ═══════════════════════════════════════════════════════════════════════════
# 8. BROWSER SESSION LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


class TestBrowserSessionLifecycle:
    """Tests for browser session timeout and cleanup."""

    def test_session_has_created_at(self):
        from realize_core.tools.browser import BrowserSession

        session = BrowserSession()
        assert hasattr(session, "_created_at")
        assert isinstance(session._created_at, float)

    def test_max_session_age_configurable(self):
        from realize_core.tools import browser

        assert hasattr(browser, "MAX_SESSION_AGE")
        assert isinstance(browser.MAX_SESSION_AGE, int)
        assert browser.MAX_SESSION_AGE > 0


# ═══════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
