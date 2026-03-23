# Phase 2 — Provider-Agnostic LLM Layer: Architecture

## Problem

RealizeOS has two hardcoded LLM clients (`claude_client.py`, `gemini_client.py`) with:
- Tightly coupled SDK imports (`anthropic`, `google.genai`)
- Duplicated patterns (lazy client init, error handling, usage logging)
- No clean way to add new providers (OpenAI, DeepSeek, Grok, Ollama, etc.)
- Router directly imports specific client functions by name

## Solution

Introduce a **provider abstraction layer** that:
1. Defines a `BaseLLMProvider` interface all providers implement
2. Wraps existing Claude and Gemini clients behind that interface
3. Creates a `ProviderRegistry` that loads available providers from config
4. Updates the router to resolve providers through the registry

## Architecture

```
┌──────────────────────────────────────────────┐
│                    Router                     │
│  classify_task() → select_model() → call()   │
│              ↓ uses registry ↓               │
├──────────────────────────────────────────────┤
│              ProviderRegistry                │
│  register() / get() / resolve_model()        │
│  Loaded from config.MODELS + providers.yaml  │
├──────────────────────────────────────────────┤
│            BaseLLMProvider (ABC)              │
│  complete() / complete_with_tools()          │
│  supports_vision() / supports_tools()        │
├──────┬───────┬───────┬──────┬───────────────┤
│Claude│Gemini │OpenAI │Ollama│  ... future   │
│      │       │(stub) │(stub)│   providers   │
└──────┴───────┴───────┴──────┴───────────────┘
```

## Key Decisions

1. **Providers wrap existing clients** — don't rewrite them, wrap them
2. **Registry is a singleton** populated at startup from config
3. **Model strings map to providers** — e.g., `"claude_sonnet"` → `ClaudeProvider`
4. **Capability flags** — providers declare what they support (text, vision, tools)
5. **Graceful degradation** — if a provider's SDK isn't installed, it logs a warning and is excluded from registry
6. **Backward compatibility** — existing `call_claude()`, `call_gemini()` functions remain working

## File Layout

```
realize_core/llm/
├── __init__.py           (unchanged)
├── base_provider.py      (NEW — ABC + dataclasses)
├── providers/
│   ├── __init__.py       (NEW)
│   ├── claude_provider.py  (NEW — wraps claude_client)
│   ├── gemini_provider.py  (NEW — wraps gemini_client)
│   ├── openai_provider.py  (NEW — stub for future)
│   └── ollama_provider.py  (NEW — stub for future)
├── registry.py           (NEW — ProviderRegistry)
├── claude_client.py      (UNCHANGED — backward compat)
├── gemini_client.py      (UNCHANGED — backward compat)
└── router.py             (MODIFIED — use registry)
```
