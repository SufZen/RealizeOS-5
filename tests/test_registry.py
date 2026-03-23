"""Tests for realize_core.llm.registry — provider registry.

Covers:
- Provider registration and lookup
- Model key → provider mapping
- Fallback chain behavior
- Capability-based provider querying
- Auto-registration (mocked)
- Singleton lifecycle
"""

from unittest.mock import MagicMock, patch

import pytest
from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)
from realize_core.llm.registry import ProviderRegistry, reset_registry

# ---------------------------------------------------------------------------
# Test provider stubs
# ---------------------------------------------------------------------------


class FakeProviderA(BaseLLMProvider):
    _available = True

    @property
    def name(self):
        return "provider_a"

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(text="response from A", model="model-a", provider=self.name)

    def list_models(self):
        return [ModelInfo(model_id="model-a", tier=2, capabilities={Capability.TEXT, Capability.TOOLS})]

    def is_available(self):
        return self._available


class FakeProviderB(BaseLLMProvider):
    _available = True

    @property
    def name(self):
        return "provider_b"

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(text="response from B", model="model-b", provider=self.name)

    def list_models(self):
        return [ModelInfo(model_id="model-b", tier=1, capabilities={Capability.TEXT, Capability.VISION})]

    def is_available(self):
        return self._available


class UnavailableProvider(BaseLLMProvider):
    @property
    def name(self):
        return "unavailable"

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(text="error", error="not_available")

    def list_models(self):
        return [ModelInfo(model_id="none")]

    def is_available(self):
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    return ProviderRegistry()


@pytest.fixture
def populated_registry():
    reg = ProviderRegistry()
    reg.register(FakeProviderA(), {"key_a": "model-a"})
    reg.register(FakeProviderB(), {"key_b": "model-b"})
    reg.set_fallback_chain(["provider_a", "provider_b"])
    return reg


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset the module singleton between tests."""
    reset_registry()
    yield
    reset_registry()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_provider(self, registry):
        pa = FakeProviderA()
        registry.register(pa, {"my_key": "model-a"})
        assert registry.get_provider("my_key") is pa

    def test_register_multiple(self, registry):
        registry.register(FakeProviderA(), {"key_a": "model-a"})
        registry.register(FakeProviderB(), {"key_b": "model-b"})
        assert registry.get_provider("key_a") is not None
        assert registry.get_provider("key_b") is not None

    def test_get_provider_by_name(self, registry):
        pa = FakeProviderA()
        registry.register(pa)
        assert registry.get_provider_by_name("provider_a") is pa

    def test_get_nonexistent_provider(self, registry):
        assert registry.get_provider("nonexistent") is None

    def test_get_nonexistent_by_name(self, registry):
        assert registry.get_provider_by_name("nonexistent") is None

    def test_register_without_model_keys(self, registry):
        pa = FakeProviderA()
        registry.register(pa)
        # Should be accessible by name but not by model key
        assert registry.get_provider_by_name("provider_a") is pa
        assert registry.get_provider("any_key") is None


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_list_available(self, populated_registry):
        available = populated_registry.list_available()
        assert "provider_a" in available
        assert "provider_b" in available

    def test_list_available_excludes_unavailable(self, registry):
        registry.register(FakeProviderA(), {"a": "m"})
        registry.register(UnavailableProvider(), {"u": "m"})
        available = registry.list_available()
        assert "provider_a" in available
        assert "unavailable" not in available

    def test_list_all(self, populated_registry):
        all_providers = populated_registry.list_all()
        assert all_providers["provider_a"] is True
        assert all_providers["provider_b"] is True

    def test_list_all_models(self, populated_registry):
        models = populated_registry.list_all_models()
        model_ids = [m.model_id for m in models]
        assert "model-a" in model_ids
        assert "model-b" in model_ids


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


class TestFallback:
    def test_fallback_returns_other_provider(self, populated_registry):
        # key_a maps to provider_a; fallback should be provider_b
        fallback = populated_registry.get_fallback("key_a")
        assert fallback is not None
        assert fallback.name == "provider_b"

    def test_fallback_skips_unavailable(self, registry):
        pa = FakeProviderA()
        pb = FakeProviderB()
        pb._available = False
        registry.register(pa, {"key_a": "model-a"})
        registry.register(pb, {"key_b": "model-b"})
        registry.set_fallback_chain(["provider_a", "provider_b"])

        fallback = registry.get_fallback("key_a")
        # provider_b is unavailable, so no fallback
        assert fallback is None

    def test_fallback_no_chain(self, registry):
        registry.register(FakeProviderA(), {"key_a": "model-a"})
        fallback = registry.get_fallback("key_a")
        assert fallback is None

    def test_fallback_for_unknown_key(self, populated_registry):
        # Unknown key → no primary provider → fallback returns first available
        fallback = populated_registry.get_fallback("nonexistent_key")
        assert fallback is not None


# ---------------------------------------------------------------------------
# Capability queries
# ---------------------------------------------------------------------------


class TestCapabilityQuery:
    def test_providers_with_tools(self, populated_registry):
        providers = populated_registry.providers_with_capability(Capability.TOOLS)
        names = [p.name for p in providers]
        assert "provider_a" in names
        assert "provider_b" not in names

    def test_providers_with_vision(self, populated_registry):
        providers = populated_registry.providers_with_capability(Capability.VISION)
        names = [p.name for p in providers]
        assert "provider_b" in names
        assert "provider_a" not in names

    def test_providers_with_text(self, populated_registry):
        providers = populated_registry.providers_with_capability(Capability.TEXT)
        assert len(providers) == 2

    def test_no_providers_with_streaming(self, populated_registry):
        providers = populated_registry.providers_with_capability(Capability.STREAMING)
        assert len(providers) == 0


# ---------------------------------------------------------------------------
# Auto-registration (mocked to avoid real imports)
# ---------------------------------------------------------------------------


class TestAutoRegister:
    def test_auto_register_sets_fallback_chain(self):
        """Auto-register should set the default fallback chain."""
        reg = ProviderRegistry()
        with patch.dict(
            "realize_core.config.MODELS",
            {
                "gemini_flash": "gemini-2.5-flash",
                "claude_sonnet": "claude-sonnet-test",
                "claude_opus": "claude-opus-test",
            },
        ):
            # Mock provider imports to avoid SDK dependency
            with patch("realize_core.llm.providers.claude_provider.ClaudeProvider") as mock_claude_cls:
                mock_claude = MagicMock(spec=BaseLLMProvider)
                mock_claude.name = "claude"
                mock_claude.is_available.return_value = True
                mock_claude.list_models.return_value = []
                mock_claude_cls.return_value = mock_claude

                with patch("realize_core.llm.providers.gemini_provider.GeminiProvider") as mock_gemini_cls:
                    mock_gemini = MagicMock(spec=BaseLLMProvider)
                    mock_gemini.name = "gemini"
                    mock_gemini.is_available.return_value = True
                    mock_gemini.list_models.return_value = []
                    mock_gemini_cls.return_value = mock_gemini

                    reg.auto_register()

        assert len(reg._fallback_chain) > 0
        assert "claude" in reg._fallback_chain
        assert "gemini" in reg._fallback_chain


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_registry_returns_same(self):
        from realize_core.llm.registry import get_registry

        with patch("realize_core.llm.registry.ProviderRegistry.auto_register"):
            r1 = get_registry()
            r2 = get_registry()
            assert r1 is r2

    def test_reset_clears_singleton(self):
        from realize_core.llm.registry import get_registry, reset_registry

        with patch("realize_core.llm.registry.ProviderRegistry.auto_register"):
            r1 = get_registry()
            reset_registry()
            r2 = get_registry()
            assert r1 is not r2
