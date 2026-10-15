# Provider-Agnostic LLM Layer — v0.1

> Every RealizeOS feature works on every LLM provider: Anthropic, Gemini, OpenAI, Ollama, and anything LiteLLM routes to. A provider may be better at a task; none is required. Decided in [ADR 0006](../../../docs/adr/0006-neutral-llm-interface.md).
>
> Status: Implemented in the 5.31 release content (branch `release/5.31`, not yet published) · Builds on [spec 005](../005-agent-tool-loop/spec.md) (the tool loop) and [spec 006](../006-what-i-used-trail/spec.md) (the trail) · No feature flag: the layer is always on

---

## 1. Goals and non-goals

**Goals**

- One neutral request/response shape (`LLMResponse`, `ToolCall`, stop reasons) so the router, the tool loop, skills and media code never read a provider's own format.
- Tools, vision, structured JSON output and refusals work on every provider that can do them, found by capability and not by name.
- When a provider cannot do something, the system says so. It never drops tools or data silently.
- The primary provider and the per-tier models are set by the operator (environment or Settings), not by code.
- Knowledge-base, memory and Synapse search work for Hebrew and other non-English text without an English-only model.
- A gate in CI stops a feature from naming a provider again.

**Non-goals**

- No new provider SDKs. Gemini, OpenAI, Ollama and the generic provider run through LiteLLM; Claude keeps its own SDK client.
- No automatic quality benchmarking across providers. The parity suite checks behaviour with fakes, and a live smoke script checks one real provider on request.
- No change to the governance engine. Every tool call still goes through `ToolRegistry.execute` and the approval gate.
- No new runtime services. Embeddings run in-process (fastembed), not behind a server.

---

## 2. Design

### 2.1 Neutral types

`realize_core/llm/base_provider.py` defines the shapes every adapter returns.

| Name | What it carries |
|---|---|
| `ToolCall` | `id`, `name`, `arguments` (a dict) |
| `LLMResponse` | `text`, `ok`, `refused`, `error`, `raw` (unchanged), plus `tool_calls`, `stop_reason`, `assistant_message` |
| Stop reasons | `end`, `tool_use`, `max_tokens`, `refusal`, `pause`, `error` |
| `EMPTY_ERROR` | `empty_response`: a reply with no text and no tool calls is an error, not an answer |

`BaseLLMProvider` gains `tools_format` (`"claude"` or `"openai"`), `user_text_message()` and `tool_result_messages()`, so the caller builds follow-up turns without knowing the wire format. `complete()` takes an optional `response_schema`. Existing signatures (`route_to_llm`, `complete`, `complete_with_tools`) keep working.

`ToolSchema.to_openai_format()` and `convert_tool_schemas(tools, fmt)` convert the registry's tool definitions once per loop.

### 2.2 Adapters

| Provider | Adapter | Transport | Model id |
|---|---|---|---|
| Anthropic | `ClaudeProvider` | Anthropic SDK | bare (`claude-sonnet-5-5`) |
| Gemini | `GeminiProvider` | LiteLLM | `gemini/…` |
| OpenAI | `OpenAIProvider` | LiteLLM | `openai/…` |
| Ollama | `OllamaProvider` | LiteLLM (`ollama_chat/…`) | the `OLLAMA_MODEL` tag |
| Anything else | `LiteLLMProvider` | LiteLLM | `LITELLM_MODEL` |

- Gemini, OpenAI and Ollama share `PrefixedLiteLLMProvider` (`realize_core/llm/providers/_litellm_adapter.py`), which adds the model prefix, per-provider kwargs and a `max_tokens` floor. Request building and response parsing are inherited, not copied.
- Ollama is available when `/api/tags` answers (cached for 30 seconds). **Tool and vision support are read from `/api/show`**, per model, not assumed. A server that is down is never cached as "no tools".
- `ANTHROPIC_WORKSPACE_ID` is sent as the `anthropic-workspace-id` header for workspace-scoped keys. The client is rebuilt when the key or workspace changes.
- Refusals carry text on every provider (a Gemini safety block, an OpenAI `content_filter`, a Claude `refusal`), so the answer is never empty.

### 2.3 Registry and routing

- `ProviderRegistry.fallback_chain()` resolves the order. It always starts with `LLM_PRIMARY` (when set and registered). With `LLM_FALLBACK` set, its providers follow in order (aliases folded, duplicates dropped) and no others are tried; without it, claude, gemini, openai, ollama, litellm follow, then any other registered provider. Unknown names are dropped with a warning. `LLM_FALLBACK` never replaces the primary.
- `providers_with_capability(cap)` returns the available providers that have a capability (`TOOLS`, `VISION`), in chain order. This is the only way code asks "who can do tools?".
- The router works in **tiers**: `fast`, `standard`, `deep`. `select_model(task_type)` returns a tier (simple to fast; content, reasoning, financial, google and web work to standard; complex to deep). Each provider maps tiers to its own models (`tier_models`).
- `LLM_MODEL_FAST`, `LLM_MODEL_STANDARD` and `LLM_MODEL_DEEP` pin a tier to a LiteLLM model string (`provider/model`). The prefix picks the provider.
- `route_completion()` is the single call path. It applies rate and cost limits, honours an explicit `model`, `tier` or `task_type`, passes `max_tokens`, `temperature` and `response_schema` only when set, accepts a refusal as final, and otherwise walks the fallback chain using each provider's own model for the same tier. When a pinned model (`model` or `LLM_MODEL_<TIER>`) fails, its provider stays in the walk and is retried with its own tier model. `route_to_llm()` keeps its signature and returns `route_completion(...).text`.
- Every caller that used to import a provider client (prompt refiner, skill suggester, evolution intent, semantic skill matcher, skill creator, review) goes through `route_completion`.
- `/api/status` and the MCP `realize_status` tool report `llm` from the registry (`{provider: "available"}`), not from which environment keys exist. So do the security scan, the developer health check, the workspace state, `doctor` and `cli.py status`, through `available_providers()` / `any_provider_available()` (an Ollama-only or LiteLLM-only install passes).

### 2.4 The agent tool loop on any provider

- `tool_capable_provider()` returns the first provider in the chain with the `TOOLS` capability, or `None`.
- The loop follows tier routing. The tier comes from the user's message (`message_tier`: a matched task category's tier, `standard` when none matches). The provider `resolve_tier` picks for it (an `LLM_MODEL_<TIER>` pin, else the primary) runs the loop with that model when it is available and supports tools; otherwise `tool_capable_provider()` runs it with its own model for the tier.
- `run_tool_loop` converts tools once with the provider's `tools_format`, appends `assistant_message` and the provider's own `tool_result_messages`, and handles each stop reason (`refusal` stops, `pause` continues, `max_tokens` and `end` finish). It never reads SDK block attributes.
- **No silent fallback.** When an agent has tools but no tool-capable provider is available, or the loop ends in an error, the system logs it, emits a `notice` event (`tools_unavailable` or `tools_error`), records the notice in the "what I used" trail, and answers with a note in the system prompt that it has no live data in this turn. The old behaviour (quietly answering from the model alone) is removed.

### 2.5 Skills

- A skill, or a single step, may set `tier:` (`fast`, `standard`, `deep`) or `model:` (a LiteLLM model string). Precedence: step `model`, step `tier`, skill `model`, skill `tier`, skill `task_type`; with none, the tier follows the classification of the user's own message.
- An agent step whose output feeds a later tool step's `json_params` is a **JSON step**. It asks the provider for structured output (`response_schema`, always an object at the root), validates the reply against the consumer's parameter schema, and retries once with the reason. A second failure fails the step. When the consumer's schema is empty or untyped, no `response_schema` is sent and the step relies on parsing and the retry. A failed LLM call (`ok` false) fails the step at once with the provider's error, with no JSON retry, and is never passed on as step output.
- **Placeholder guard.** Only the step's template is scanned: a `{name}` naming a known step that has no result yet fails the step ("unresolved placeholder"). Values are substituted in one pass and never scanned, so a step result or variable that contains `{some_step}` (untrusted data) is inserted as it is. A JSON step whose answer is a bare `{name}` or only the example row's labels is rejected and retried once.
- The demo packs' payment and requirements skills pin `tier: standard`.

### 2.6 Media

`analyze_image` walks the providers with the `VISION` capability in chain order. A PDF goes to a provider that accepts PDF input; any other provider gets the extracted text. The first non-empty answer wins, and the result names the provider that gave it. When no vision provider read a PDF, its extracted text goes through `route_completion` to any text-capable provider, so a text-only Ollama reads PDFs too.

`transcribe_audio` asks the available providers in chain order for the transcription capability (`supports_transcription()` / `transcribe()`). OpenAI (Whisper) and the generic LiteLLM provider (`LITELLM_TRANSCRIPTION_MODEL`, for example `groq/whisper-large-v3`) go through `litellm.atranscription`; Gemini reads the audio as an `input_audio` chat part. Claude and Ollama have no transcription. Without a capable provider the result says "No transcription-capable provider configured".

### 2.7 Multilingual search

- `realize_core/utils/fts.py` builds safe FTS queries: Unicode normalisation, Hebrew niqqud removed, a small stopword list, terms quoted and OR'ed, and Hebrew prefix letters (ו ה ב ל מ ש כ) stripped as extra alternates on the query side. Index text is not rewritten.
- The FTS tokenizer depends on the SQLite version:

  | SQLite | Tokenizer |
  |---|---|
  | 3.45 or later | `trigram remove_diacritics 1` |
  | 3.34 to 3.44 (includes the Docker image) | `trigram` |
  | older | `unicode61 remove_diacritics 2` |

- The knowledge-base, memory and Synapse indexes store a schema version and the tokenizer in use. **When the tokenizer changes, the index rebuilds itself** on first open.
- Results rank by `bm25`. A query that has no usable FTS term falls back to a scoped `LIKE` over short tokens, and the venture scope always applies.
- Embeddings use fastembed with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (about 0.22 GB), overridable with `KB_EMBED_MODEL` (unset = default; empty, `none`, `off`, `0` or `false` turn them off). Changing the model clears the stored vectors and re-embeds. A model that cannot load logs a warning and search stays keyword-only.
- `POST /api/kb/reindex` (and `realize kb reindex`) rebuilds on demand, with the same auth as `/settings/reindex`.
- MCP `kb_search` is scoped to the caller's ventures, inside the handler as well as in the dispatcher.
- Token estimates count Hebrew and Arabic letters at 1.5 characters per token, so prompts are not under-counted. A short Hebrew question (3 or more characters) now triggers the knowledge-base lookup.

### 2.8 Settings and dashboard

- `GET /api/llm/routing` returns the task-type rules with tier, provider and resolved model, the three tiers (and whether each came from the environment), the providers with their models, the effective primary and fallback chain, and the raw configured values. `PUT /api/llm/routing` changes only the fields sent, validates everything before writing, and applies without a restart. It needs `system:manage` and is closed to venture-limited callers.
- Settings has an editable LLM Routing form (primary, a model per tier, fallback order), and onboarding lets the owner choose the primary once a provider is connected, in English and Hebrew. LiteLLM is a connectable provider. The "Recommended" badge on one provider is gone.
- A `notice` event shows in the trail panel as a warning line, live and in stored trails.

### 2.9 Guard rails

- `scripts/check_provider_neutral.py` fails CI when code in `realize_core/`, `realize_api/`, `cli.py`, `scripts/` or `plugins/` outside the allow-listed adapter, configuration and setup files calls a provider client, compares to a provider name, tests a model string for a provider, or reads a provider API key (`ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) from the environment. A single line may opt out with `# provider-neutral: ok <reason>`; the reason is required.
- `tests/test_provider_parity.py` runs the same scenarios on all four adapters (Anthropic, OpenAI, Gemini, Ollama shapes) with only the network transport faked.
- `scripts/provider_smoke.py` is the live per-provider check (§3, criterion 12).

---

## 3. Acceptance

1. With only `GOOGLE_AI_API_KEY` set, chat, tool use, skills, vision and search all work. The same holds with only `OPENAI_API_KEY`, only a local Ollama, only `ANTHROPIC_API_KEY`, or only `LITELLM_MODEL`.
2. An agent with tools uses them on any tool-capable provider, and the trail shows the same events on each.
3. With no tool-capable provider, the agent says it has no live data, and the trail shows a `tools_unavailable` notice.
4. `LLM_PRIMARY`, `LLM_FALLBACK` and `LLM_MODEL_*` change the routing without a restart when set through Settings.
5. A skill with `tier:` or `model:` uses it; a JSON step returns validated JSON or fails with a reason; an unresolved placeholder fails the step.
6. `analyze_image` works on any vision-capable provider, and on a PDF with a provider that has no PDF input.
7. A Hebrew question finds Hebrew documents with and without a prefix letter, in the knowledge base, memory and Synapse.
8. Upgrading rebuilds the indexes automatically; an existing install loses no data.
9. A venture-limited MCP caller cannot read another venture's documents through `kb_search`.
10. `python scripts/check_provider_neutral.py` passes on the tree, and CI runs it.
11. The cross-provider parity suite passes; all new tests use fakes and make no network call.
12. `python scripts/provider_smoke.py --provider <name>` passes against that one real provider (run by hand or nightly, never in pull-request CI, never against the demo install).
13. Existing public signatures and the existing tests keep working (the 8 known Windows-only baseline failures are unchanged).

---

## 4. Decisions

Rulings made during the build, each with the cost if it was wrong.

1. **Trigram tokenizer, gated on SQLite.** `trigram remove_diacritics 1` needs SQLite 3.45. Hosts on 3.34 to 3.44, which includes the Docker base image, get plain `trigram` (niqqud in indexed text is not stripped there, which is rare in documents). Only older hosts fall back to `unicode61`, with weaker Hebrew matching. The tokenizer is recorded, and the index rebuilds when it changes.
2. **Trigram plus query-side prefix alternates.** Trigram cannot match a prefixed word (בתקציב) against its stem (תקציב) by itself. The query adds the stripped forms; the index is unchanged. Cost: slightly more OR terms and a few extra matches, ranked below real ones.
3. **Embedding model.** fastembed does not ship `multilingual-e5-small`, so the default is the closest supported multilingual model, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (same dimension and size class, covers Hebrew). E5 prefixes apply only when `KB_EMBED_MODEL` names an e5 model.
4. **Narrow placeholder-echo guard.** Only a bare `{name}` and the labels of the prompt's own example row are rejected, once, with a retry. A real value that happens to equal an example label passes if the data contains it. Cost: a legitimate row equal to the example labels fails once and is retried.
5. **Router passes optional arguments only when set**, so older test fakes without `response_schema` keep working.
6. **Venture scope inside the handler.** The MCP dispatcher already refused out-of-scope `kb_search` calls; the handler now enforces the scope too, as defence in depth. A limited caller never sees `shared` files.
7. **Provider-name checks outside the adapters are gate violations.** The demo rehearsal preflight accepts any available provider. The provider-key checks in the security scanner, the developer health check, the workspace state, `doctor` and `cli.py status` now ask the registry, and a gate rule (`provider-key-env`) keeps new ones out.
8. **Gate scope.** The gate scans `realize_core/`, `realize_api/`, `cli.py`, `scripts/` and `plugins/` (not itself); the allow-list is the adapters, the alias and configuration tables, and the setup flows. Anything else, `cli.py` included, uses a line pragma.
9. **The live smoke runs one provider at a time**, with the others switched off, so a broken provider cannot hide behind a working one. Sheets and Drive are stubbed; nothing is written to a real sheet. Each row prints the provider and model that answered it.
10. **Claude ignores `response_schema`.** The native Claude adapter accepts the argument for interface parity and does not send it. On Claude, a JSON step relies on the prompt, validation and one retry. Cost: a malformed first reply on Claude costs one extra call.
11. **`LLM_FALLBACK` follows the primary.** It lists the providers tried after `LLM_PRIMARY`, never instead of it. Cost: an operator who used `LLM_FALLBACK` alone to pick the first provider must now also set `LLM_PRIMARY`.
12. **The tool loop defaults to the `standard` tier.** Plain chat with no matched category stays on the cheap `fast` tier, but an agent with tools answers on `standard` unless the message matches a category. Cost: tool turns on small talk use the standard model.
13. **Transcription is a capability, routed through LiteLLM.** OpenAI and any `LITELLM_TRANSCRIPTION_MODEL` use `litellm.atranscription`; Gemini uses an audio chat part. Claude and Ollama cannot transcribe, so an install with only those reports that no transcription-capable provider is configured.

---

## 5. Out of scope for this spec

- Publishing and deploying the release. This document describes the 5.31 release content.
- Per-provider cost dashboards and prompt-cache tuning.
- **Follow-ups (brief item 18):** provider-neutral prompt caching and token streaming. Streaming currently sends the "what I used" trail events live, and the answer arrives whole.
- Fine-tuning which provider is best for which task. The tier table is a default, and the operator changes it.
