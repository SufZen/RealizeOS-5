"""
Ollama LLM Provider: Stub for local/self-hosted LLM integration via Ollama.

To activate: install Ollama, pull a model, and set OLLAMA_HOST if not localhost.
No API key required — runs locally.
"""
import logging

from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider (stub — ready for implementation)."""

    @property
    def name(self) -> str:
        return "ollama"

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id="llama3.1:8b",
                display_name="Llama 3.1 8B (local)",
                tier=1,
                capabilities={Capability.TEXT, Capability.CODE},
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                max_tokens=4096,
                context_window=128000,
            ),
            ModelInfo(
                model_id="deepseek-coder-v2:16b",
                display_name="DeepSeek Coder V2 (local)",
                tier=1,
                capabilities={Capability.TEXT, Capability.CODE},
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                max_tokens=4096,
                context_window=128000,
            ),
        ]

    def is_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            import os

            import httpx
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            # Quick sync check — don't block on this
            resp = httpx.get(f"{host}/api/tags", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Text completion via Ollama API (stub)."""
        if not self.is_available():
            return LLMResponse(
                text="Ollama not running. Start Ollama and pull a model first.",
                model=model or "llama3.1:8b", provider=self.name,
                error="not_available",
            )

        # TODO: Implement when ready
        # import httpx, os
        # host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(f"{host}/api/chat", json={
        #         "model": model or "llama3.1:8b",
        #         "messages": [{"role": "system", "content": system_prompt}] + messages,
        #         "options": {"temperature": temperature, "num_predict": max_tokens},
        #         "stream": False,
        #     })
        #     data = response.json()
        #     return LLMResponse(text=data["message"]["content"], ...)

        return LLMResponse(
            text="Ollama provider not yet implemented.",
            model=model or "llama3.1:8b", provider=self.name,
            error="not_implemented",
        )
