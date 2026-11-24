"""
ChatGPT plan provider: text completions billed to the owner's ChatGPT plan.

Uses OpenAI's token sharing (see ``realize_core.llm.chatgpt_plan``): POST
``/v1/responses`` with the plan's access token, ``store: false`` and
``stream: true`` on every request. No API key and no API billing, so each call
costs $0 against the monthly cap.

Turned on by signing in once (``scripts/chatgpt_signin.py``) and setting
``CHATGPT_PLAN_MODEL`` to a model the account lists. Name it ``chatgpt_plan``
in ``LLM_PRIMARY``.

Fallback: when the plan answers "usage limit reached", the provider pauses for
``CHATGPT_PLAN_PAUSE_SECONDS`` (default 1800) and reports itself unavailable,
so the router goes to the next provider in ``LLM_FALLBACK``. OpenAI never
switches billing on its own; here the owner chooses it by listing a fallback.
Leave ``LLM_FALLBACK`` empty of paid providers to stop instead.

Text only in this version: no tool use, no vision, no transcription. Tool-using
agents are routed to a provider that has tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, ClassVar

from realize_core.llm import chatgpt_plan
from realize_core.llm.base_provider import STOP_END, STOP_ERROR, BaseLLMProvider, Capability, LLMResponse, ModelInfo

logger = logging.getLogger(__name__)

RESPONSES_URL = "https://api.openai.com/v1/responses"
NAME = "chatgpt_plan"

# Error codes from the Responses API (token sharing) and what the provider does.
PAUSE_CODES = frozenset({"subscription_sharing_usage_limit_exceeded"})
DISABLE_CODES = frozenset(
    {
        "subscription_sharing_user_not_eligible",
        "subscription_sharing_route_not_supported",
        "chatpass_v2_scope_not_authorized",
        "chatpass_v2_invalid_authorization_context",
    }
)
REAUTH_CODES = frozenset({"subscription_sharing_invalid_user"})


def plan_model() -> str:
    return os.getenv("CHATGPT_PLAN_MODEL", "").strip()


def _pause_seconds() -> float:
    try:
        return float(os.getenv("CHATGPT_PLAN_PAUSE_SECONDS", "1800"))
    except ValueError:
        return 1800.0


def _text_of(content: Any) -> str:
    """Plain text of an OpenAI- or Claude-shaped message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text"):
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def build_body(system_prompt: str, messages: list[dict], model: str, response_schema: dict | None = None) -> dict:
    """The Responses request: history as input items, the system prompt as instructions.

    Only fields token sharing accepts: no temperature, max_output_tokens or
    metadata; system text goes in ``instructions`` (system input items are rejected).
    """
    instructions = system_prompt or ""
    if response_schema:
        instructions += "\n\nReply with JSON only, matching this JSON schema:\n" + json.dumps(
            response_schema, ensure_ascii=False
        )
    items = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _text_of(m.get("content"))
        if text:
            items.append({"role": role, "content": text})
    body: dict[str, Any] = {"model": model, "input": items, "store": False, "stream": True}
    if instructions.strip():
        body["instructions"] = instructions
    return body


def parse_stream(lines) -> tuple[str, dict, str | None]:
    """Read SSE lines: (text, usage, error code or None).

    Success is a ``response.completed`` event; a stream that ends without one
    is an error.
    """
    chunks: list[str] = []
    usage: dict = {}
    completed = False
    error: str | None = None
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "response.output_text.delta":
            chunks.append(str(event.get("delta", "")))
        elif kind == "response.completed":
            completed = True
            response = event.get("response") or {}
            usage = response.get("usage") or {}
            if not chunks and isinstance(response.get("output_text"), str):
                chunks.append(response["output_text"])
        elif kind == "response.failed":
            err = (event.get("response") or {}).get("error") or {}
            error = err.get("code") or "response_failed"
        elif kind == "response.incomplete":
            error = error or "response_incomplete"
        elif kind == "error":
            error = event.get("code") or (event.get("error") or {}).get("code") or "stream_error"
    if error is None and not completed:
        error = "stream_ended_without_completion"
    return "".join(chunks), usage, error


class ChatGPTPlanProvider(BaseLLMProvider):
    """Text completions on the owner's ChatGPT plan through token sharing."""

    tier_models: ClassVar[dict[str, str]] = {}

    def __init__(self, credentials_file: Path | None = None) -> None:
        self._credentials_file = credentials_file
        self._paused_until = 0.0
        self._disabled_reason: str | None = None

    @property
    def name(self) -> str:
        return NAME

    @property
    def credentials_file(self) -> Path:
        return self._credentials_file or chatgpt_plan.credentials_path()

    def default_model_id(self) -> str | None:
        return plan_model() or None

    def list_models(self) -> list[ModelInfo]:
        model = plan_model()
        if not model:
            return []
        return [ModelInfo(model_id=model, display_name=f"{model} (ChatGPT plan)", tier=2)]

    def is_available(self) -> bool:
        """Signed in, a model configured, not paused by a usage limit, not disabled."""
        if not plan_model() or self._disabled_reason or time.time() < self._paused_until:
            return False
        creds = chatgpt_plan.load_credentials(self.credentials_file)
        return bool(creds and not creds.needs_reauth and creds.refresh_token)

    def model_errors(self) -> dict[str, str]:
        if self._disabled_reason:
            return {plan_model() or NAME: self._disabled_reason}
        return {}

    def supports(self, capability: Capability) -> bool:
        return capability == Capability.TEXT

    def _pause(self, reason: str) -> None:
        self._paused_until = time.time() + _pause_seconds()
        logger.warning(f"ChatGPT plan paused for {_pause_seconds():.0f}s ({reason}); using the fallback chain")

    async def _post(self, body: dict, token: str, timeout: float) -> tuple[int, str, dict, str | None]:
        """POST and read the stream: (status, text, usage, error code)."""
        import httpx

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", RESPONSES_URL, json=body, headers=headers) as response,
        ):
            if response.status_code != 200:
                raw = await response.aread()
                return response.status_code, "", {}, _error_code(raw, response.status_code)
            lines = [line async for line in response.aiter_lines()]
        text, usage, error = parse_stream(lines)
        return 200, text, usage, error

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,  # not accepted by token sharing; ignored
        temperature: float = 0.7,  # not accepted by token sharing; ignored
        timeout: float = 120.0,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        model = (model or "").removeprefix(f"{NAME}/") or plan_model()
        if not model:
            return self._error("", "CHATGPT_PLAN_MODEL is not set")
        body = build_body(system_prompt, messages, model, response_schema)

        for attempt in (1, 2):
            try:
                token = await asyncio.to_thread(
                    chatgpt_plan.valid_access_token, self.credentials_file, force=attempt == 2
                )
            except chatgpt_plan.ReauthRequiredError as e:
                return self._error(model, f"chatgpt_plan_reauth_required: {e}")
            except chatgpt_plan.TokenError as e:
                return self._error(model, f"chatgpt_plan_refresh_failed: {e.code}")
            try:
                status, text, usage, code = await self._post(body, token, timeout)
            except Exception as e:  # network, timeout
                return self._error(model, f"chatgpt_plan_request_failed: {type(e).__name__}")

            if code is None:
                return LLMResponse(
                    text=text,
                    model=model,
                    provider=NAME,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cost_usd=0.0,  # billed to the ChatGPT plan, not the API
                    stop_reason=STOP_END,
                )
            if code in PAUSE_CODES or status == 429:
                self._pause(code)
            elif code in DISABLE_CODES:
                self._disabled_reason = code
                logger.error(f"ChatGPT plan disabled: {code}")
            elif (code in REAUTH_CODES or status == 401) and attempt == 1:
                continue  # one forced refresh, then give up for this call
            return self._error(model, f"chatgpt_plan: {code}")
        return self._error(model, "chatgpt_plan: unauthorized after refresh")

    def _error(self, model: str, error: str) -> LLMResponse:
        return LLMResponse(text="", model=model, provider=NAME, error=error, stop_reason=STOP_ERROR)


def _error_code(raw: bytes, status: int) -> str:
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict) and err.get("code"):
        return str(err["code"])
    return f"http_{status}"
