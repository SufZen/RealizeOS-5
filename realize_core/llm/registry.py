"""
Provider Registry: Central registry for LLM providers.

Maps model keys (e.g., "claude_sonnet") to provider instances.
Auto-discovers available providers at startup based on installed SDKs and API keys.
"""

import logging
import os
from collections.abc import Mapping

from realize_core.llm.base_provider import BaseLLMProvider, Capability, ModelInfo

logger = logging.getLogger(__name__)

# Order used when nothing else says otherwise; unlisted providers follow in registration order.
_DEFAULT_ORDER = ["claude", "gemini", "openai", "ollama", "litellm"]
# LLM_PRIMARY spellings -> registered provider names.
_PROVIDER_ALIASES = {"anthropic": "claude", "google": "gemini", "google_ai": "gemini"}


class ProviderRegistry:
    """Registry that maps model keys to LLM providers.

    Usage:
        registry = ProviderRegistry()
        registry.auto_register()  # Discovers available providers
        provider = registry.get_provider("claude_sonnet")
        response = await provider.complete(system_prompt, messages)
    """

    def __init__(self):
        self._providers: dict[str, BaseLLMProvider] = {}  # name → provider instance
        self._model_map: dict[str, str] = {}  # model_key → provider name
        self._fallback_chain: list[str] = []  # provider names in fallback order
        self._model_ids: dict[str, str] = {}  # model_key → model_id as registered

    def register(self, provider: BaseLLMProvider, model_keys: dict[str, str] | None = None):
        """Register a provider with optional model key mappings.

        Args:
            provider: The provider instance
            model_keys: Mapping of model_key → model_id
                         e.g., {"claude_sonnet": "claude-sonnet-5-5"}
        """
        self._providers[provider.name] = provider

        if model_keys:
            for key, model_id in model_keys.items():
                if key in self._model_map and self._model_map[key] != provider.name:
                    logger.warning(
                        f"Model key '{key}' already registered to provider "
                        f"'{self._model_map[key]}', skipping re-registration "
                        f"by '{provider.name}'"
                    )
                    continue
                self._model_map[key] = provider.name
                self._model_ids[key] = model_id

        try:
            avail = provider.is_available()
            n_models = len(provider.list_models())
        except BaseException:
            avail = False
            n_models = 0
        logger.info(f"Registered provider: {provider.name} (available={avail}, models={n_models})")

    def get_provider(self, model_key: str) -> BaseLLMProvider | None:
        """Get the provider for a given model key (e.g., 'claude_sonnet').

        Args:
            model_key: The logical model key from config/router

        Returns:
            The provider instance, or None if not found.
        """
        provider_name = self._model_map.get(model_key)
        if provider_name:
            return self._providers.get(provider_name)
        return None

    def get_provider_by_name(self, name: str) -> BaseLLMProvider | None:
        """Get a provider by its name (e.g., 'claude', 'gemini')."""
        return self._providers.get(name)

    def resolve_model_id(self, model_key: str) -> str | None:
        """Resolve a model key to its actual model ID string.

        Config-defined keys (``claude_sonnet``, ``gemini_flash``, ...) resolve
        from ``config.MODELS``. Any other key resolves through the model the
        owning provider registered for it, which must still appear in that
        provider's ``list_models()``.

        Returns:
            The provider's model ID string, or None if the key is unknown.
        """
        from realize_core.config import MODELS

        if model_key in MODELS:
            return MODELS[model_key]
        provider = self.get_provider(model_key)
        model_id = self._model_ids.get(model_key)
        if provider and model_id and any(m.model_id == model_id for m in provider.list_models()):
            return model_id
        return None

    def get_fallback(self, model_key: str) -> BaseLLMProvider | None:
        """Get a fallback provider when the primary is unavailable.

        Walks the fallback chain and returns the first available provider
        that isn't the same as the requested one.
        """
        primary_name = self._model_map.get(model_key)
        for provider_name in self._fallback_chain:
            if provider_name != primary_name:
                provider = self._providers.get(provider_name)
                if provider and provider.is_available():
                    return provider
        return None

    def set_fallback_chain(self, chain: list[str]):
        """Set the provider fallback order.

        Args:
            chain: List of provider names in priority order
                   e.g., ["claude", "gemini", "openai", "ollama"]
        """
        self._fallback_chain = chain

    def list_available(self) -> list[str]:
        """Return names of all currently available providers."""
        return [name for name, p in self._providers.items() if p.is_available()]

    def list_all(self) -> dict[str, bool]:
        """Return all registered providers with their availability status."""
        return {name: p.is_available() for name, p in self._providers.items()}

    def list_all_models(self) -> list[ModelInfo]:
        """Return all models across all available providers."""
        models = []
        for provider in self._providers.values():
            if provider.is_available():
                models.extend(provider.list_models())
        return models

    def fallback_chain(self) -> list[str]:
        """The provider fallback order (copy)."""
        return list(self._fallback_chain)

    def primary_provider_name(self) -> str | None:
        """Name of the first available provider in the fallback chain."""
        for name in self._fallback_chain:
            provider = self._providers.get(name)
            if provider and provider.is_available():
                return name
        return None

    def providers_with_capability(self, capability: Capability, available_only: bool = True) -> list[BaseLLMProvider]:
        """Find providers that support a capability, in fallback-chain order.

        Providers outside the chain follow in registration order. With
        ``available_only`` (the default) unavailable providers are skipped.
        """
        ordered = [n for n in self._fallback_chain if n in self._providers]
        ordered += [n for n in self._providers if n not in ordered]
        providers = [self._providers[n] for n in ordered]
        return [p for p in providers if (not available_only or p.is_available()) and p.supports(capability)]

    def _resolve_fallback_chain(self) -> list[str]:
        """Compute the fallback order from the environment and registered providers.

        The chain always starts with LLM_PRIMARY (when set and registered).
        LLM_FALLBACK entries follow in order, de-duplicated with aliases
        folded and unknown names dropped. When LLM_FALLBACK names at least one
        registered provider, nothing else is appended; otherwise the remaining
        registered providers follow in the default order.
        """
        from realize_core.config import llm_fallback, llm_primary

        chain: list[str] = []
        primary = llm_primary()
        if primary:
            primary = _PROVIDER_ALIASES.get(primary, primary)
            if primary in self._providers:
                chain.append(primary)
            else:
                logger.warning(f"LLM_PRIMARY names unknown provider '{primary}', ignoring it")

        explicit = [_PROVIDER_ALIASES.get(n, n) for n in llm_fallback()]
        if explicit:
            listed = []
            for name in explicit:
                if name not in self._providers:
                    logger.warning(f"LLM_FALLBACK names unknown provider '{name}', ignoring it")
                elif name not in listed:
                    listed.append(name)
            if listed:
                return chain + [n for n in listed if n not in chain]
            logger.warning("LLM_FALLBACK has no registered providers; using the default order")

        rest = [n for n in _DEFAULT_ORDER if n in self._providers]
        rest += [n for n in self._providers if n not in rest]
        return chain + [n for n in rest if n not in chain]

    def auto_register(self):
        """Auto-discover and register all known providers.

        Checks if each provider's SDK is installed and API key is configured.
        Only registers providers that pass is_available().
        """
        from realize_core.config import DEFAULT_CLAUDE_OPUS_MODEL, DEFAULT_CLAUDE_SONNET_MODEL, MODELS

        # Claude
        try:
            from realize_core.llm.providers.claude_provider import ClaudeProvider

            claude = ClaudeProvider()
            self.register(
                claude,
                {
                    "claude_sonnet": MODELS.get("claude_sonnet", DEFAULT_CLAUDE_SONNET_MODEL),
                    "claude_opus": MODELS.get("claude_opus", DEFAULT_CLAUDE_OPUS_MODEL),
                },
            )
        except Exception as e:
            logger.debug(f"Claude provider not registered: {e}")

        # Gemini
        try:
            from realize_core.llm.providers.gemini_provider import GeminiProvider, model_keys

            self.register(GeminiProvider(), model_keys())
        except BaseException as e:
            logger.debug(f"Gemini provider not registered: {e}")

        # OpenAI
        try:
            from realize_core.llm.providers.openai_provider import OpenAIProvider, model_keys

            self.register(OpenAIProvider(), model_keys())
        except Exception as e:
            logger.debug(f"OpenAI provider not registered: {e}")

        # Ollama (available only while a local server answers)
        try:
            from realize_core.llm.providers.ollama_provider import OllamaProvider, model_keys

            self.register(OllamaProvider(), model_keys())
        except Exception as e:
            logger.debug(f"Ollama provider not registered: {e}")

        # LiteLLM (unified gateway to 50+ providers)
        try:
            from realize_core.llm.litellm_provider import LiteLLMProvider

            litellm_p = LiteLLMProvider()
            self.register(
                litellm_p,
                {
                    "o3_mini": "o3-mini",
                    "mistral_large": "mistral/mistral-large-latest",
                    "deepseek_v3": "deepseek/deepseek-chat",
                },
            )
        except Exception as e:
            logger.debug(f"LiteLLM provider not registered: {e}")

        # LLM_FALLBACK / LLM_PRIMARY, else Claude → Gemini → OpenAI → Ollama → LiteLLM
        self.set_fallback_chain(self._resolve_fallback_chain())

        available = self.list_available()
        logger.info(
            f"Provider registry ready: {len(self._providers)} registered, "
            f"{len(available)} available ({', '.join(available) or 'none'})"
        )


# --- Module-level singleton ---

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get or create the global provider registry singleton."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _registry.auto_register()
    return _registry


def reset_registry():
    """Reset the registry (for testing)."""
    global _registry
    _registry = None


def available_providers(env: Mapping[str, str] | None = None) -> list[str]:
    """Names of the LLM providers usable right now; any one of them is enough.

    Without ``env`` this asks the global registry. With ``env`` (for example
    the values of a ``.env`` file that is not loaded into the process) the
    check reads those values laid over a *copy* of the current environment;
    ``os.environ`` is never modified, so a concurrent request cannot see them.
    Ollama is probed here, at call time, at the URL the mapping names. This
    blocks for up to the probe timeout: call it from async code via
    ``asyncio.to_thread``.
    """
    if env is None:
        return get_registry().list_available()
    merged = {**os.environ, **{k: str(v) for k, v in env.items() if v is not None}}
    return _available_in_env(merged)


# Key-based providers: (provider name, API-key variable, module the adapter needs).
_KEYED_PROVIDERS = (
    ("claude", "ANTHROPIC_API_KEY", "anthropic"),
    ("gemini", "GOOGLE_AI_API_KEY", "litellm"),
    ("openai", "OPENAI_API_KEY", "litellm"),
)


def _available_in_env(env: Mapping[str, str]) -> list[str]:
    """Providers usable with the variables in ``env`` (read-only; mirrors each adapter's is_available).

    Same order as ``auto_register``: Claude, Gemini, OpenAI, Ollama, LiteLLM.
    """
    import importlib.util

    names = [
        name for name, key, module in _KEYED_PROVIDERS if env.get(key) and importlib.util.find_spec(module) is not None
    ]
    if _ollama_answers(env):
        names.append("ollama")
    if _litellm_configured(env):
        names.append("litellm")
    return names


def _ollama_answers(env: Mapping[str, str]) -> bool:
    """True when the Ollama server named by ``env`` answers ``/api/tags``."""
    import httpx

    from realize_core.config import ollama_base_url
    from realize_core.llm.providers.ollama_provider import _PROBE_TIMEOUT

    try:
        return httpx.get(f"{ollama_base_url(env)}/api/tags", timeout=_PROBE_TIMEOUT).status_code == 200
    except Exception:
        return False


def _litellm_configured(env: Mapping[str, str]) -> bool:
    """True when the generic LiteLLM provider has an endpoint or the keys its default model needs."""
    try:
        import litellm

        from realize_core.llm.litellm_provider import _FALLBACK_MODEL
    except Exception:
        return False
    if env.get("LITELLM_API_BASE"):
        return True
    model = env.get("LITELLM_MODEL") or _FALLBACK_MODEL
    try:
        # Reads os.environ only; the keys it reports missing are then looked up in ``env``.
        result = litellm.validate_environment(model=model)
    except Exception:
        return False
    if result.get("keys_in_environment"):
        return True
    missing = result.get("missing_keys") or []
    return bool(missing) and all(env.get(k) for k in missing)


def any_provider_available(env: Mapping[str, str] | None = None) -> bool:
    """True when at least one LLM provider is usable (see ``available_providers``)."""
    try:
        return bool(available_providers(env))
    except Exception as e:
        logger.warning(f"Could not check LLM providers: {e}")
        return False
