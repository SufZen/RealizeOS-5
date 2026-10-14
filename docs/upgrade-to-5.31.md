# Upgrade to RealizeOS 5.31

This guide describes the **5.31 release content**: every feature works on every LLM provider. It is for servers on **5.30.0**. Nothing here says 5.31 is published or deployed; follow it when you take the release.

## Before you start

1. **Back up.** In the dashboard, **Settings → Storage & Backup → Export** (or `POST /api/storage/export`). Also keep a copy of `realize-os.yaml`, `users.yaml` and `.env`; the export leaves out secrets on purpose.
2. **Note your version.** `GET /api/status` (signed in) or `realize-os version` shows what's running.
3. **Plan for a longer first start.** The search indexes rebuild once (see below) and the embedding model is downloaded on first use. On a big knowledge base, expect the first start to take noticeably longer than usual.

## Upgrade

- **Docker:** set `REALIZE_VERSION` to the 5.31 tag (or pull `latest`) and recreate the container: `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d`. The image build downloads the embedding model when the build has network access; otherwise it downloads on first indexing (or set `KB_EMBED_MODEL=none` to run fully offline).
- **pip:** `pip install -U realize-os`, then restart the service. Two new dependencies, `fastembed` (local embeddings) and `pypdf` (PDF text for providers that cannot read PDFs), are installed with it.
- **From source / Windows installer:** `git pull` and reinstall the requirements (`pip install -r requirements.txt`), or run `Update-RealizeOS.bat`, then restart.

There are no new database migrations. The search indexes upgrade themselves at startup.

## What changes for you

### Search indexes rebuild automatically (trigram)

The knowledge-base index (`kb_index.db`), the memory store (`memory.db`) and the Synapse index (`synapse.db`) now use an FTS5 **trigram** tokenizer, so Hebrew and other non-English text match properly (a Hebrew word with a prefix letter, such as בתקציב, finds תקציב). On first start each index notices that it uses the old tokenizer and rebuilds itself. You do nothing, and no stored memory or entity is lost: memories are re-indexed from their table, and Synapse text is copied across.

The tokenizer depends on the SQLite your Python uses:

| SQLite | Tokenizer |
|---|---|
| 3.45 or later | `trigram remove_diacritics 1` |
| 3.34 to 3.44 (the Docker image is here) | `trigram` |
| older | `unicode61` (weaker Hebrew matching) |

If the SQLite version later changes, the index rebuilds again. To rebuild by hand: `realize-os kb reindex` or `POST /api/kb/reindex` (it needs the same permission as `/settings/reindex`).

Venture folders whose `system_dir` is outside `systems/` are now indexed too, and a file's venture is found by its folder path, so a venture named `a` no longer picks up files from `ab`.

### Embedding model download

Knowledge-base search now has a semantic part, and it uses a multilingual model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (about **0.22 GB**), run locally by `fastembed`. The old default was an English-only model, so every stored vector is recomputed once, during the first index run after the upgrade.

- **Download.** It happens on first use and is cached (`FASTEMBED_CACHE_PATH`; the Docker image sets `/app/models/fastembed` and tries to download the model while building, which only works when the build has network access).
- **Offline or blocked.** If the model cannot be loaded, a warning is logged and search stays keyword-only. Nothing fails. For an air-gapped host, copy the model cache into `FASTEMBED_CACHE_PATH` before starting, or turn embeddings off.
- **Change or disable it.** `KB_EMBED_MODEL=<fastembed model name>` picks another model (changing it clears the stored vectors and re-embeds); `KB_EMBED_MODEL=none` turns embeddings off (so do an empty value, `off`, `0` and `false`; leave the variable **unset** for the default).

### New settings (all optional)

| Setting | Default | What it does |
|---|---|---|
| `LLM_PRIMARY` | first available provider | Which provider is tried first: `anthropic`, `gemini`, `openai`, `ollama` or `litellm` |
| `LLM_FALLBACK` | `LLM_PRIMARY`, then Claude, Gemini, OpenAI, Ollama, LiteLLM | Providers tried after `LLM_PRIMARY`, in order, e.g. `gemini,openai,ollama`. It never replaces the primary, and when it is set no other providers are tried |
| `LLM_MODEL_FAST` / `LLM_MODEL_STANDARD` / `LLM_MODEL_DEEP` | each provider's own model | Pin a task tier to a LiteLLM model string, e.g. `openai/gpt-4o` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server. **`OLLAMA_HOST` still works as an alias** when `OLLAMA_BASE_URL` is empty |
| `OLLAMA_MODEL` | `llama3.1:8b` | The Ollama model tag. Tool use and vision are detected from Ollama's `/api/show` |
| `LITELLM_MODEL`, `LITELLM_API_BASE` | unset | Any other provider LiteLLM supports, and an optional gateway URL for it |
| `GEMINI_FLASH_MODEL`, `GEMINI_PRO_MODEL` | `gemini-2.5-flash` / `gemini-2.5-pro` | Gemini model ids |
| `ANTHROPIC_WORKSPACE_ID` | unset | Set it for **workspace-scoped Anthropic keys**; it is sent as the `anthropic-workspace-id` header |
| `KB_EMBED_MODEL` | unset = the multilingual model above | Embedding model; empty, `none`, `off`, `0` or `false` = keyword search only |

All of these can also be changed in **Settings → LLM Routing** without a restart, and the onboarding wizard asks for the primary provider. See [configuration.md](configuration.md#llm-routing) for examples per provider (Gemini only, OpenAI only, Ollama only, Claude, a LiteLLM proxy).

You do not have to set anything. An existing install with the same keys keeps working: with no `LLM_PRIMARY`, the first available provider is used, in the same Claude, Gemini, OpenAI, Ollama order as before.

### Behaviour you'll notice

- **Any one provider is enough.** A server with only a Gemini key, only an OpenAI key, or only a local Ollama now runs agent tools, skills, vision and search. The setup guides no longer say an Anthropic or Google key is required.
- **The agent tells you when it has no tools.** If an agent has tools but no available provider can run them, it says it has no live data in that turn and the "what I used" trail shows a notice (`tools_unavailable`, or `tools_error` if the loop failed). Before, it quietly answered from the model alone. If you see the notice, add a tool-capable provider.
- **Skills can pin a model.** Skills and steps accept `tier:` (`fast`, `standard`, `deep`) and `model:` (a LiteLLM model string). Steps that feed JSON to a tool get structured output, validated with one retry. An unresolved `{placeholder}` now fails the step instead of reaching the model. See [skill-authoring.md](skill-authoring.md).
- **`/api/status` reports providers by what works.** The `llm` field lists registry providers (`claude`, `gemini`, `openai`, `ollama`, `litellm`) that are usable, instead of listing which environment keys exist. The MCP `realize_status` tool does the same.
- **Routing endpoint.** `GET /api/llm/routing` now returns tiers, the effective primary and fallback chain, and the raw settings; `PUT /api/llm/routing` changes them. `PUT` needs `system:manage` and is closed to venture-limited callers.
- **Vision and PDF analysis work on any vision-capable provider**, not only Claude and Gemini. A PDF goes to a provider that takes PDFs directly; others get the extracted text.
- **MCP `kb_search` is scoped to the caller.** A caller limited to some ventures only sees those ventures' documents, and `shared` files are not returned to it.
- **Token estimates for Hebrew and Arabic are higher** (one token per 1.5 characters instead of 3.5, which was the estimate for all text), so long Hebrew prompts are trimmed a little earlier than before and no longer overrun the model.
- **A short Hebrew question** (three or more characters) now triggers the knowledge-base lookup; it needed 20 before.
- **Dashboard.** The "Recommended" badge on one provider is gone. Settings has an editable LLM Routing form (English and Hebrew).
- **Demo rehearsal.** The preflight accepts any available LLM provider, not only Anthropic.

### For contributors

- **Provider-neutral CI check.** `python scripts/check_provider_neutral.py` runs in CI and fails when code outside the provider adapters calls a provider client or tests for a provider name. Run it before you push. If a line must name one (a wire-format id, say), end it with `# provider-neutral: ok <reason>`; the reason is required.
- **Cross-provider tests.** New tests use the `fake_llm` fixture, which runs each scenario on all four adapter shapes (`tests/fakes/llm.py`). Never call a real API from a test.
- **Live smoke test.** `python scripts/provider_smoke.py --provider <claude|gemini|openai|ollama>` runs the webinar storyline against one real provider in a temporary project. It spends real tokens, so run it by hand or on a schedule, not in pull-request CI, and **never against the demo install** (it refuses `D:/realization-demo`). `--dry-run` makes no LLM call.
- The CI test job sets `GOOGLE_AI_API_KEY` to a fake value, and the tests set `KB_EMBED_MODEL=none` so nothing downloads a model.

## After the upgrade

1. `GET /api/health` shows `ok`, and `GET /api/status` shows the new version and your providers under `llm`.
2. Ask a question in Hebrew that your knowledge base can answer. The answer should cite a source in the trail.
3. Open **Settings → LLM Routing**. Check that the primary provider and the three tier models are what you expect. A model id the provider no longer serves is flagged there.
4. If you only use a local Ollama, check the chat trail once for a `tools_unavailable` notice. If the notice appears, the model you chose does not report tool support; pick one that does.
5. Optionally, run the live smoke test against your provider (see above).

## Rolling back

Restore the 5.30 image or package and the backup you took. There are no new migrations, so the database opens in 5.30.

- **Search indexes.** The 5.30 code does not know about the trigram tables or the new embedding model. The knowledge-base index is derived from your files: delete `kb_index.db` before starting 5.30 and it rebuilds from the files (otherwise 5.30 would compare its own query vectors with vectors from the multilingual model). `memory.db` and `synapse.db` still open; the older version may rank short words differently. If you need exactly the old behaviour, restore those two files from your pre-upgrade backup.
- **Settings.** The new variables are ignored by 5.30. `OLLAMA_HOST` is the name 5.30 reads, so keep it if you set `OLLAMA_BASE_URL` only for 5.31.
