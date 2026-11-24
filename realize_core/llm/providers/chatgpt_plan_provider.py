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
from realize_core.llm.base_provider import (
    REFUSAL_ERROR,
    REFUSAL_TEXT,
    STOP_END,
    STOP_ERROR,
    STOP_REFUSAL,
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

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


class StreamParser:
    """Reads SSE lines as they arrive and says when the response is final.

    Success is a ``response.completed`` event; a stream that ends without a
    terminal event is an error. A refusal (``response.refusal.*`` or an
    incomplete response stopped by the content filter) is reported as
    ``REFUSAL_ERROR`` so the router does not retry it elsewhere.
    """

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.refusal: list[str] = []
        self.usage: dict = {}
        self.completed = False
        self.error: str | None = None

    def feed(self, raw: str | bytes) -> bool:
        """Take one line; True once a terminal event has been seen."""
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            return False
        data = line[5:].strip()
        if not data or data == "[DONE]":
            return data == "[DONE]"
        try:
            event = json.loads(data)
        except ValueError:
            return False
        kind = event.get("type")
        response = event.get("response") or {}
        if kind == "response.output_text.delta":
            self.chunks.append(str(event.get("delta", "")))
        elif kind == "response.refusal.delta":
            self.refusal.append(str(event.get("delta", "")))
        elif kind == "response.refusal.done":
            if not self.refusal:
                self.refusal.append(str(event.get("refusal", "")))
            return True  # final: do not wait for (or depend on) the rest of the stream
        elif kind == "response.completed":
            self.completed = True
            self.usage = response.get("usage") or {}
            if not self.chunks and isinstance(response.get("output_text"), str):
                self.chunks.append(response["output_text"])
            return True
        elif kind == "response.failed":
            self.error = (response.get("error") or {}).get("code") or "response_failed"
            return True
        elif kind == "response.incomplete":
            reason = (response.get("incomplete_details") or {}).get("reason")
            if reason == "content_filter":
                self.refusal.append("")
            else:
                self.error = f"response_incomplete:{reason or 'unknown'}"
            return True
        elif kind == "error":
            self.error = event.get("code") or (event.get("error") or {}).get("code") or "stream_error"
            return True
        return False

    def result(self) -> tuple[str, dict, str | None]:
        """(text, usage, error code or None). A refusal gives its text and REFUSAL_ERROR."""
        if self.refusal:
            return "".join(self.refusal).strip() or REFUSAL_TEXT, self.usage, REFUSAL_ERROR
        if self.error is None and not self.completed:
            return "".join(self.chunks), self.usage, "stream_ended_without_completion"
        return "".join(self.chunks), self.usage, self.error


def parse_stream(lines) -> tuple[str, dict, str | None]:
    """Parse a whole list of SSE lines (see ``StreamParser``)."""
    parser = StreamParser()
    for line in lines:
        if parser.feed(line):
            break
    return parser.result()


class ChatGPTPlanProvider(BaseLLMProvider):
    """Text completions on the owner's ChatGPT plan through token sharing."""

    tier_models: ClassVar[dict[str, str]] = {}
    billable: ClassVar[bool] = False  # billed to the ChatGPT plan, not the API

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
        """POST and read the stream as it arrives: (status, text, usage, error code).

        Stops at the first terminal event, and the whole call has a wall-clock
        deadline of ``timeout`` seconds (a stream kept open by heartbeats still ends).
        """
        import httpx

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        parser = StreamParser()
        async with asyncio.timeout(timeout):
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream("POST", RESPONSES_URL, json=body, headers=headers) as response,
            ):
                if response.status_code != 200:
                    raw = await response.aread()
                    return response.status_code, "", {}, _error_code(raw, response.status_code)
                async for line in response.aiter_lines():
                    if parser.feed(line):
                        break
        text, usage, error = parser.result()
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

        rejected: str | None = None
        for attempt in (1, 2):
            try:
                token = await asyncio.to_thread(
                    chatgpt_plan.valid_access_token, self.credentials_file, rejected=rejected
                )
            except chatgpt_plan.ReauthRequiredError as e:
                return self._error(model, f"chatgpt_plan_reauth_required: {e}")
            except chatgpt_plan.TokenError as e:
                return self._error(model, f"chatgpt_plan_refresh_failed: {e.code}")
            try:
                status, text, usage, code = await self._post(body, token, timeout)
            except Exception as e:  # network, timeout
                return self._error(model, f"chatgpt_plan_request_failed: {type(e).__name__}")

            if code == REFUSAL_ERROR:
                # Final: the router returns a refusal as-is and does not retry elsewhere.
                return LLMResponse(
                    text=text or REFUSAL_TEXT,
                    model=model,
                    provider=NAME,
                    error=REFUSAL_ERROR,
                    stop_reason=STOP_REFUSAL,
                )
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
                rejected = token  # refresh unless another process already replaced this token
                continue
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
