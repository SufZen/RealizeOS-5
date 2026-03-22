"""
Provider Registry: Central registry for LLM providers.

Maps model keys (e.g., "claude_sonnet") to provider instances.
Auto-discovers available providers at startup based on installed SDKs and API keys.
"""
import logging
from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse, Capability, ModelInfo

logger = logging.getLogger(__name__)


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

    def register(self, provider: BaseLLMProvider, model_keys: dict[str, str] | None = None):
        """Register a provider with optional model key mappings.

        Args:
            provider: The provider instance
            model_keys: Mapping of model_key → model_id
                         e.g., {"claude_sonnet": "claude-sonnet-4-6-20260217"}
        """
        self._providers[provider.name] = provider

        if model_keys:
            for key, model_id in model_keys.items():
                self._model_map[key] = provider.name

        logger.info(f"Registered provider: {provider.name} "
                     f"(available={provider.is_available()}, models={len(provider.list_models())})")

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

        Args:
            model_key: e.g., "claude_sonnet"

        Returns:
            The provider's model ID string (e.g., "claude-sonnet-4-6-20260217")
        """
        from realize_core.config import MODELS
        return MODELS.get(model_key)

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

    def providers_with_capability(self, capability: Capability) -> list[BaseLLMProvider]:
        """Find all available providers that support a specific capability."""
        return [
            p for p in self._providers.values()
            if p.is_available() and p.supports(capability)
        ]

    def auto_register(self):
        """Auto-discover and register all known providers.

        Checks if each provider's SDK is installed and API key is configured.
        Only registers providers that pass is_available().
        """
        from realize_core.config import MODELS

        # Claude
        try:
            from realize_core.llm.providers.claude_provider import ClaudeProvider
            claude = ClaudeProvider()
            self.register(claude, {
                "claude_sonnet": MODELS.get("claude_sonnet", "claude-sonnet-4-6-20260217"),
                "claude_opus": MODELS.get("claude_opus", "claude-opus-4-6-20260205"),
            })
        except Exception as e:
            logger.debug(f"Claude provider not registered: {e}")

        # Gemini
        try:
            from realize_core.llm.providers.gemini_provider import GeminiProvider
            gemini = GeminiProvider()
            self.register(gemini, {
                "gemini_flash": MODELS.get("gemini_flash", "gemini-2.5-flash"),
            })
        except Exception as e:
            logger.debug(f"Gemini provider not registered: {e}")

        # OpenAI (stub — registers but is_available will return False without SDK/key)
        try:
            from realize_core.llm.providers.openai_provider import OpenAIProvider
            openai_p = OpenAIProvider()
            self.register(openai_p, {
                "gpt4o": "gpt-4o",
                "gpt4o_mini": "gpt-4o-mini",
            })
        except Exception as e:
            logger.debug(f"OpenAI provider not registered: {e}")

        # Ollama (stub — registers but is_available depends on local server)
        try:
            from realize_core.llm.providers.ollama_provider import OllamaProvider
            ollama = OllamaProvider()
            self.register(ollama, {
                "llama": "llama3.1:8b",
                "deepseek": "deepseek-coder-v2:16b",
            })
        except Exception as e:
            logger.debug(f"Ollama provider not registered: {e}")

        # Default fallback chain: Claude → Gemini → OpenAI → Ollama
        self.set_fallback_chain(["claude", "gemini", "openai", "ollama"])

        available = self.list_available()
        logger.info(f"Provider registry ready: {len(self._providers)} registered, "
                     f"{len(available)} available ({', '.join(available) or 'none'})")


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
