# ADR 0006 — One Neutral LLM Interface, Capability Lookup Instead of Provider Names

- **Status:** Accepted
- **Date:** 2026-10-14
- **Branch:** `release/5.31`
- **Deciders:** Asaf (owner)
- **Supersedes:** the consequence in [ADR 0003](0003-agent-tool-loop.md) that tool use "runs on providers with a native tool API (Claude)" and that "LiteLLM/OpenAI tool formats are a follow-up".
- **Relates to:** [spec 011](../../.specify/specs/011-provider-agnostic/spec.md) (what was built), [spec 005](../../.specify/specs/005-agent-tool-loop/spec.md) (the tool loop).

## Context

RealizeOS 5.30 advertised "Claude, Gemini, OpenAI and Ollama", but features were built around two of them. The tool loop read Anthropic content blocks directly, so agents with tools worked on Claude only; on any other provider the agent quietly answered without its tools. Image and PDF analysis imported the Claude and Gemini clients by name. The router picked model keys such as `gemini_flash` and `claude_opus`. Status reported which environment keys existed, not which providers worked. A server with only an OpenAI key or only Ollama could chat, and little else.

For the webinar demo and for customers who choose their own model, "any provider works" has to be true for every feature, and has to stay true as code is added.

## Decision

1. **One neutral response.** Every adapter returns `LLMResponse` with `text`, `tool_calls` (`ToolCall`), `stop_reason` and `assistant_message`. Existing fields (`text`, `ok`, `refused`, `raw`) and the signatures of `route_to_llm`, `complete` and `complete_with_tools` are unchanged. Callers read the neutral fields and never an SDK object.
2. **The adapter owns the wire format.** Each provider declares `tools_format` and builds its own follow-up messages (`user_text_message`, `tool_result_messages`). The tool loop converts tool schemas once and appends what the adapter hands back.
3. **LiteLLM for everything except Claude.** Gemini, OpenAI, Ollama and the generic provider run through LiteLLM with a model prefix; one shared adapter parses requests and replies. Claude keeps the Anthropic SDK because its content blocks, `pause_turn` and PDF input are first-class there. A new provider is a small subclass or just a `LITELLM_MODEL` string.
4. **Ask by capability, never by name.** `providers_with_capability(TOOLS | VISION)` returns the available providers in fallback order. Ollama's capabilities come from the model's `/api/show` response. No code outside the adapters tests for a provider.
5. **Tiers, not model keys.** The router speaks `fast`, `standard` and `deep`. Each provider maps tiers to its own models, and `LLM_MODEL_<TIER>` pins one to any LiteLLM model string. `LLM_PRIMARY` and `LLM_FALLBACK` set the order. All of it can be changed in Settings without a restart.
6. **One call path.** `route_completion()` applies limits, resolves the provider and model, and walks the fallback chain. Every caller, including skills and media, uses it. The direct Claude and Gemini last resorts in the router are removed.
7. **Say it when a capability is missing.** If an agent has tools and no provider can run them, the answer says it has no live data, and the trail records a `notice`. Silent degradation is a defect.
8. **A gate keeps it true.** `scripts/check_provider_neutral.py` runs in CI and fails on provider-name checks and direct client use outside an allow-list of adapters and configuration files. A line may opt out with `# provider-neutral: ok <reason>`. A cross-provider parity suite runs the same scenarios on all four adapter shapes, and a live smoke script checks one real provider on demand.
9. **Language coverage travels with provider independence.** Search uses a trigram FTS index and a multilingual embedding model that runs locally (fastembed), so a Hebrew installation does not depend on any provider's embeddings. The index rebuilds when its tokenizer changes.

## Consequences

- Any one provider is enough to run the whole system, including a local Ollama with no key. The setup docs stop saying an Anthropic or Google key is required.
- Quality still differs by model. A small local model may follow tool schemas less reliably. The tier table is a default the operator is expected to adjust.
- `LLMResponse` and `BaseLLMProvider` gain fields and optional arguments. A third-party provider that returned only text keeps working, but gets no tool use until it fills `tool_calls`.
- `/api/status` now reports providers by registry name (`claude`, `gemini`, `openai`, `ollama`, `litellm`) and by whether they are usable, not by which keys exist.
- The gate is a line-by-line heuristic. It misses a comparison split over several lines, so code review still matters.
- Two provider-key checks (the project scanner and the developer health check) still name providers and are a follow-up.
- Upgrading rebuilds the knowledge-base, memory and Synapse indexes once and downloads an embedding model of about 0.22 GB on first use. See [upgrade-to-5.31.md](../upgrade-to-5.31.md).
- This ADR and spec 011 describe the 5.31 release content. They do not claim it is published or deployed.

## References

- `realize_core/llm/base_provider.py`, `realize_core/llm/litellm_provider.py`, `realize_core/llm/providers/`, `realize_core/llm/registry.py`, `realize_core/llm/router.py`
- `realize_core/agents/tool_loop.py`, `realize_core/base_handler.py`, `realize_core/skills/executor.py`, `realize_core/media/__init__.py`
- `realize_core/utils/fts.py`, `realize_core/kb/indexer.py`
- `scripts/check_provider_neutral.py`, `scripts/provider_smoke.py`
- Tests: `tests/test_llm_neutral.py`, `tests/test_llm_providers_adapters.py`, `tests/test_tool_loop_providers.py`, `tests/test_provider_parity.py`, `tests/test_check_provider_neutral.py`
