"""
Hermes Runtime Adapter.

Makes the deployed Hermes agent (NousResearch/hermes-agent) a governed
runtime peer in the kernel by satisfying the AgentRuntime contract.

Hermes exposes an OpenAI-compatible HTTP API (its gateway runs on the VPS,
typically ``http://<host>:8642/v1`` and is the same endpoint Open-WebUI uses).
This adapter is a thin, robustly-guarded facade over that API:

- ``health_check()`` → GET ``{base_url}/models`` (short timeout).
- ``invoke()``       → POST ``{base_url}/chat/completions`` with ``stream: true``,
                        translating SSE deltas into RuntimeEvents.
- everything else    → cheap/local or no-ops.

Every network call is guarded; ``health_check`` and ``invoke`` never raise out
(``invoke`` yields an ``ErrorEvent`` instead). The adapter only ever gets
registered when a ``runtimes.hermes.base_url`` is configured, so it is inert by
default.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from realize_core.runtimes.contract import (
    Capability,
    CapabilitySet,
    Context,
    CostClass,
    CostEstimate,
    HealthStatus,
    MissionStep,
    Modality,
    Skill,
    Task,
    ToolProtocol,
)
from realize_core.runtimes.events import (
    ErrorEvent,
    FinalResultEvent,
    ProgressEvent,
    RuntimeEvent,
    TextEvent,
)

logger = logging.getLogger(__name__)

# Default model name advertised by the Hermes gateway.
DEFAULT_MODEL = "hermes"
# Health checks must return well within the registry's 5s timeout.
HEALTH_TIMEOUT_SEC = 4.0
# Generation is allowed to run longer (streamed).
INVOKE_TIMEOUT_SEC = 120.0


def _resolve_secret(value: str | None) -> str:
    """
    Resolve a possibly-env-referenced secret.

    Accepts ``${ENV_VAR}`` or ``$ENV_VAR`` references and resolves them from the
    environment. Plain values are returned unchanged. ``None`` → "".
    """
    if not value:
        return ""
    value = value.strip()
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    if value.startswith("$"):
        return os.getenv(value[1:], "")
    return value


class HermesAdapter:
    """
    Adapter wrapping a deployed Hermes (OpenAI-compatible) endpoint as a runtime.

    Construct from a ``runtimes.hermes`` config block::

        HermesAdapter.from_config({"base_url": "http://host:8642/v1",
                                   "api_key": "${HERMES_API_KEY}",
                                   "model": "hermes"})
    """

    runtime_id: str = "hermes"
    display_name: str = "Hermes (NousResearch)"
    version: str = "0.1.0"
    runtime_version: str | None = None

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
    ):
        # Normalise: drop trailing slash so we can join cleanly.
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = _resolve_secret(api_key)
        self.model = model or DEFAULT_MODEL

    @classmethod
    def from_config(cls, hermes_config: dict) -> HermesAdapter:
        """Build a HermesAdapter from a ``runtimes.hermes`` config dict."""
        return cls(
            base_url=hermes_config.get("base_url", ""),
            api_key=hermes_config.get("api_key"),
            model=hermes_config.get("model"),
        )

    # === Capability declaration ===

    def capabilities(self) -> CapabilitySet:
        """Declare general text/chat capability for Hermes."""
        return CapabilitySet(
            capabilities=[
                Capability(name="research", confidence=0.7, cost_class=CostClass.MODERATE),
                Capability(name="reasoning.general", confidence=0.7, cost_class=CostClass.MODERATE),
                Capability(name="writing.general", confidence=0.7, cost_class=CostClass.MODERATE),
            ],
            languages=["en"],
            modalities=[Modality.TEXT],
            tool_protocols=[ToolProtocol.OPENAI_FUNCTION],
            streaming=True,
            cancellation=False,
            parallelism=1,
            requires_internet=True,
            is_local=False,
        )

    # === Lifecycle ===

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def health_check(self) -> HealthStatus:
        """
        GET {base_url}/models with a short timeout.

        HEALTHY (ready=True) on a 2xx, OFFLINE (ready=False) otherwise. Never
        raises — any transport/timeout error becomes a not-ready HealthStatus.
        """
        if not self.base_url:
            return HealthStatus(ready=False, error="No base_url configured")

        try:
            import httpx
        except ImportError as e:  # pragma: no cover - httpx is a hard dep
            return HealthStatus(ready=False, error=f"httpx not available: {e}")

        started = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SEC) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
            latency_ms = int((datetime.now() - started).total_seconds() * 1000)

            if resp.status_code // 100 == 2:
                # Best-effort: surface a model id as the runtime_version.
                version = None
                try:
                    data = resp.json()
                    models = data.get("data") or data.get("models") or []
                    if models and isinstance(models, list):
                        first = models[0]
                        version = first.get("id") if isinstance(first, dict) else str(first)
                except Exception:
                    version = None
                self.runtime_version = version
                return HealthStatus(
                    ready=True,
                    degraded=False,
                    latency_ms=latency_ms,
                    runtime_version=version,
                )

            return HealthStatus(
                ready=False,
                latency_ms=latency_ms,
                error=f"HTTP {resp.status_code} from {self.base_url}/models",
            )
        except Exception as e:
            return HealthStatus(ready=False, error=f"{type(e).__name__}: {e}")

    async def warmup(self) -> None:
        """No explicit warmup; a health_check is enough to validate the endpoint."""
        pass

    async def shutdown(self) -> None:
        """No persistent resources held — clients are per-call and closed."""
        pass

    # === Cost & estimation ===

    async def cost_estimate(self, task: Task, context: Context) -> CostEstimate:
        """Static, network-free estimate for a Hermes generation."""
        estimated_tokens = task.expected_output_tokens or 2000
        # Hermes is self-hosted; treat monetary cost as negligible but non-zero.
        estimated_cost = (estimated_tokens / 1000) * 0.0005
        return CostEstimate(
            estimated_tokens=estimated_tokens,
            estimated_duration_sec=8.0,
            estimated_cost_eur=estimated_cost,
            confidence=0.4,
        )

    # === Execution ===

    def _build_messages(self, mission_step: MissionStep, context: Context) -> list[dict]:
        """Build OpenAI-style chat messages from the step + context."""
        messages: list[dict] = []

        # Optional system framing from the agent/user soul + venture summary.
        system_bits: list[str] = []
        if context.venture_summary:
            system_bits.append(f"Venture context: {context.venture_summary}")
        if isinstance(context.agent_soul, dict):
            persona = context.agent_soul.get("persona") or context.agent_soul.get("description")
            if persona:
                system_bits.append(str(persona))
        if system_bits:
            messages.append({"role": "system", "content": "\n\n".join(system_bits)})

        # Prior history, if any (already in {role, content} shape by convention).
        if context.history:
            for turn in context.history:
                if isinstance(turn, dict) and "role" in turn and "content" in turn:
                    messages.append({"role": turn["role"], "content": str(turn["content"])})

        # The actual instruction: prefer an explicit prompt/goal input, else the
        # step description.
        prompt = mission_step.inputs.get("prompt") or mission_step.inputs.get("goal") or mission_step.description
        messages.append({"role": "user", "content": str(prompt)})
        return messages

    async def invoke(
        self,
        mission_step: MissionStep,
        context: Context,
    ) -> AsyncIterator[RuntimeEvent]:
        """
        Execute a mission step against the Hermes chat-completions endpoint.

        Streams ``TextEvent`` per delta and concludes with a ``FinalResultEvent``.
        Any HTTP/transport error yields an ``ErrorEvent`` (never raises out).
        """
        run_id = uuid.uuid4().hex[:16]
        started_at = datetime.now()

        yield ProgressEvent(
            run_id=run_id,
            message=f"Dispatching to Hermes: {mission_step.description}",
            percent_complete=0.0,
        )

        if not self.base_url:
            yield ErrorEvent(
                run_id=run_id,
                error_type="invalid_input",
                message="Hermes adapter has no base_url configured",
                retryable=False,
            )
            return

        try:
            import httpx
        except ImportError as e:  # pragma: no cover - httpx is a hard dep
            yield ErrorEvent(
                run_id=run_id,
                error_type="internal",
                message=f"httpx not available: {e}",
                retryable=False,
            )
            return

        model = mission_step.inputs.get("model") or self.model
        payload = {
            "model": model,
            "messages": self._build_messages(mission_step, context),
            "stream": True,
        }

        assembled: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=INVOKE_TIMEOUT_SEC) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status_code // 100 != 2:
                        # Drain the body for a useful message, then error out.
                        body = ""
                        try:
                            body = (await resp.aread()).decode("utf-8", "replace")[:500]
                        except Exception:
                            body = ""
                        yield ErrorEvent(
                            run_id=run_id,
                            error_type="upstream",
                            message=f"Hermes HTTP {resp.status_code}: {body}",
                            retryable=resp.status_code >= 500,
                        )
                        return

                    async for line in resp.aiter_lines():
                        delta = _parse_sse_delta(line)
                        if delta:
                            assembled.append(delta)
                            yield TextEvent(run_id=run_id, delta=delta)

        except Exception as e:
            logger.error("Hermes adapter invoke error: %s", e)
            yield ErrorEvent(
                run_id=run_id,
                error_type="upstream",
                message=f"{type(e).__name__}: {e}",
                retryable=True,
            )
            return

        elapsed = (datetime.now() - started_at).total_seconds()
        output_text = "".join(assembled)
        yield FinalResultEvent(
            run_id=run_id,
            output={"text": output_text},
            cost_actual={
                "actual_tokens": len(output_text.split()) * 2,  # rough estimate
                "actual_duration_sec": elapsed,
                "actual_cost_eur": 0.0,
            },
            status="success",
        )

    async def cancel(self, run_id: str) -> bool:
        """Hermes exposes no cancel endpoint here — best-effort no-op."""
        return False

    # === Skill exchange (not bridged) ===

    async def export_skills(self) -> list[Skill] | None:
        """Hermes has no skill-library bridge here."""
        return None

    async def import_skill(self, skill: Skill) -> bool:
        """Hermes has no skill-library bridge here."""
        return False


def _parse_sse_delta(line: str) -> str | None:
    """
    Extract the text delta from one OpenAI-style SSE line.

    Lines look like ``data: {json}`` with a terminal ``data: [DONE]``. Returns
    the assistant content delta, or ``None`` for keep-alives / non-data lines /
    malformed chunks.
    """
    if not line:
        return None
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return None
    try:
        choices = obj.get("choices") or []
        if not choices:
            return None
        choice = choices[0]
        # Streaming chunks carry {"delta": {"content": ...}}; some servers send
        # a full {"message": {"content": ...}} instead.
        delta = choice.get("delta") or choice.get("message") or {}
        content = delta.get("content")
        if content:
            return str(content)
    except (AttributeError, TypeError, KeyError):
        return None
    return None
