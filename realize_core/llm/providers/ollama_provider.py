"""
Ollama LLM Provider: local / self-hosted models through LiteLLM.

No API key. The server URL comes from OLLAMA_BASE_URL (or OLLAMA_HOST), the
model from OLLAMA_MODEL. Tool and vision support are probed from the model itself.
"""

import logging
import time
from typing import Any, ClassVar

import httpx

from realize_core import config
from realize_core.llm.base_provider import Capability, ModelInfo
from realize_core.llm.providers._litellm_adapter import PrefixedLiteLLMProvider

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 2.0
_AVAILABILITY_TTL = 30.0
# A failed /api/show probe is retried after this long (a success is kept).
_CAPABILITY_FAILURE_TTL = 60.0


def model_keys() -> dict[str, str]:
    """Registry model keys -> LiteLLM model IDs for Ollama."""
    return {"ollama": OllamaProvider._model_id()}


class OllamaProvider(PrefixedLiteLLMProvider):
    """Ollama provider. Cost is always zero."""

    prefix = "ollama_chat/"
    tier_models: ClassVar[dict[str, str]] = {"fast": "ollama", "standard": "ollama", "deep": "ollama"}

    def __init__(self) -> None:
        super().__init__(default_model=self._model_id())
        # (base_url, checked_at, reachable)
        self._availability: tuple[str, float, bool] | None = None
        # (base_url, model) -> capabilities the model advertises ("tools", "vision", ...)
        self._capabilities: dict[tuple[str, str], frozenset[str]] = {}
        # (base_url, model) -> when its /api/show probe last failed
        self._probe_failed_at: dict[tuple[str, str], float] = {}

    @property
    def name(self) -> str:
        return "ollama"

    @classmethod
    def _model_id(cls) -> str:
        return f"{cls.prefix}{config.ollama_model()}"

    def is_available(self) -> bool:
        """True when the Ollama server answers ``/api/tags`` (cached for 30s)."""
        base = config.ollama_base_url()
        now = time.monotonic()
        cached = self._availability
        if cached and cached[0] == base and now - cached[1] < _AVAILABILITY_TTL:
            return cached[2]
        try:
            reachable = httpx.get(f"{base}/api/tags", timeout=_PROBE_TIMEOUT).status_code == 200
        except Exception:
            reachable = False
        self._availability = (base, now, reachable)
        return reachable

    def _model_capabilities(self, model: str) -> frozenset[str]:
        """The ``capabilities`` ``/api/show`` lists for ``model`` (empty when unknown).

        A successful probe is cached; a failed one is retried after
        ``_CAPABILITY_FAILURE_TTL`` seconds (the model may still be pulling).
        """
        base = config.ollama_base_url()
        key = (base, model)
        if key in self._capabilities:
            return self._capabilities[key]
        failed_at = self._probe_failed_at.get(key)
        if failed_at is not None and time.monotonic() - failed_at < _CAPABILITY_FAILURE_TTL:
            return frozenset()
        if not self.is_available():
            return frozenset()  # not cached: the server may come up later
        try:
            resp = httpx.post(f"{base}/api/show", json={"model": model, "name": model}, timeout=_PROBE_TIMEOUT)
            resp.raise_for_status()
            caps = frozenset(resp.json().get("capabilities") or [])
        except Exception as e:
            logger.debug("Ollama capability probe failed for %s: %s", model, e)
            self._probe_failed_at[key] = time.monotonic()
            return frozenset()
        self._probe_failed_at.pop(key, None)
        self._capabilities[key] = caps
        return caps

    def _model_has_tools(self, model: str) -> bool:
        """True if ``/api/show`` lists "tools" in the model's capabilities."""
        return "tools" in self._model_capabilities(model)

    def _model_has_vision(self, model: str) -> bool:
        """True if ``/api/show`` lists "vision" (llava, gemma3, qwen2.5vl, ...)."""
        return "vision" in self._model_capabilities(model)

    def list_models(self) -> list[ModelInfo]:
        caps = {Capability.TEXT}
        if self._model_has_tools(config.ollama_model()):
            caps.add(Capability.TOOLS)
        if self._model_has_vision(config.ollama_model()):
            caps.add(Capability.VISION)
        return [
            ModelInfo(
                model_id=self._model_id(),
                display_name=f"{config.ollama_model()} (local)",
                tier=1,
                capabilities=caps,
                max_tokens=4096,
                context_window=128000,
            )
        ]

    def _call_kwargs(self, model: str) -> dict[str, Any]:
        return {"api_base": config.ollama_base_url()}

    def _calc_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0
