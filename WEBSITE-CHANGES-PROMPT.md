# Website Changes Prompt — RealizeOS Package Updates

Use this prompt in a separate Claude Code session targeting the RealizeOS website repository. It describes all changes made to the Lite and Full packages that require website alignment.

---

## PROMPT START

You are updating the RealizeOS website to match changes made to both the Lite and Full downloadable packages. Below is every change that affects website content. Go through each section and make the necessary updates.

### 1. Directory Name Change: `my-business` → `my-business-1`

**What changed**: The default venture directory in both Lite and Full packages was renamed from `systems/my-business/` to `systems/my-business-1/`. The Lite package now ships with 3 venture slots: `my-business-1`, `my-business-2`, `my-business-3`.

**Website updates needed**:
- Any references to `systems/my-business/` should become `systems/my-business-1/`
- Venture Wizard export labels must include the correct path prefix: `systems/my-business-1/F-foundations/venture-identity.md` and `systems/my-business-1/F-foundations/venture-voice.md`
- If the website shows file placement instructions for downloaded packages, update all paths
- If the website mentions "your system directory", clarify that the default is `systems/my-business-1/`

### 2. Prompt Assembly: "7-Layer" → "Multi-Layer"

**What changed**: The prompt builder actually assembles 12 layers (identity, preferences, venture, routing, agent, extra context, dynamic KB/RAG, memory, cross-system, session, proactive, channel format). All package documentation now says "multi-layer" instead of "7-layer".

**Website updates needed**:
- Replace all instances of "7-layer" or "7 layer" with "multi-layer" in feature descriptions, pricing pages, comparison tables, and marketing copy
- If the website lists the specific layers, update to the correct 12-layer list:
  1. Identity Layer
  2. Preferences Layer
  3. Venture Layer
  4. Routing Layer
  5. Agent Layer
  6. Extra Context Layer
  7. Dynamic KB Layer (RAG)
  8. Memory Layer
  9. Cross-System Layer
  10. Session Layer
  11. Proactive Layer
  12. Format Layer

### 3. Templates: 8 Total (Not 5)

**What changed**: The Full package includes 8 templates. The website may only list 5.

**Complete template list**:
| Template | Best For |
|----------|----------|
| `consulting` | Solo consultants, advisory firms |
| `agency` | Creative/marketing agencies |
| `portfolio` | Multi-venture operators |
| `saas` | SaaS founders, product teams |
| `ecommerce` | Online stores, D2C ventures |
| `accounting` | Accountants, bookkeepers, tax advisors |
| `coaching` | Business/life coaches, course creators |
| `freelance` | Freelance developers, designers, writers |

**Website updates needed**:
- Update template count from "5" to "8" wherever referenced
- Add the 3 missing templates (accounting, coaching, freelance) to any template listing
- If there's a "choose your template" section, include all 8

### 4. Cross-System Context: Now Implemented

**What changed**: Cross-system context was previously "coming soon" or unimplemented. It is now a working feature. When `cross_system: true` is set in features, agents can see state maps and venture summaries from all configured ventures.

**Website updates needed**:
- Remove any "coming soon" labels from cross-system/multi-venture context features
- Add cross-system context as a Full package feature: "Cross-venture awareness — agents can reference state and venture context from all your businesses"
- The `portfolio` template ships with `cross_system: true` by default

### 5. Venture CLI Commands: New Feature

**What changed**: The Full package now includes CLI commands for venture management:
```bash
python cli.py venture create --key my-venture --name "My Venture"
python cli.py venture delete --key my-venture --confirm my-venture
python cli.py venture list
```

**Website updates needed**:
- Add venture management to the Full package feature list
- If there's a CLI reference section, add the venture commands
- If there's a "getting started" flow for the Full package, mention that users can create additional ventures via CLI

### 6. Download Instructions: No `git clone`

**What changed**: Both packages are paid products downloaded from the website, not cloned from GitHub. All package documentation now uses generic "download and unzip" language.

**Website updates needed**:
- Verify that download/setup instructions do NOT reference `git clone`
- Use language like "Download and unzip" or "Extract the package"
- The Full package quick start should be: download → unzip → `pip install -r requirements.txt` → `python cli.py init --template consulting` → configure `.env` → `python cli.py serve`

### 7. Feature Flags: Now Functional

**What changed**: Feature flags in `realize-os.yaml` (`review_pipeline`, `auto_memory`, `proactive_mode`, `cross_system`) are now connected to the Python engine and actually control behavior.

**Website updates needed**:
- If feature flags are mentioned, they can be described as functional (not decorative)
- List available flags if there's a configuration section:
  - `review_pipeline` — Enable automatic review pipeline for content
  - `auto_memory` — Log learnings after meaningful interactions
  - `proactive_mode` — Enable proactive suggestions and push-back
  - `cross_system` — Share context across all ventures

### 8. Multi-Venture Support in Lite

**What changed**: The Lite package now ships with 3 venture slots (`my-business-1`, `my-business-2`, `my-business-3`), supporting multi-venture use out of the box.

**Website updates needed**:
- If the Lite feature list mentions single-venture only, update to reflect multi-venture support
- Add "3 venture slots included" or "Multi-venture ready" to Lite features
- Clarify that users can customize each venture independently

### 9. Model IDs Updated

**What changed**: Default model IDs updated to latest versions:
- Claude Sonnet: `claude-sonnet-4-6-20250610`
- Claude Opus: `claude-opus-4-6-20250610`

**Website updates needed**:
- If the website references specific model versions, update them
- If there's a "powered by" or "models used" section, ensure it reflects current model names

### 10. Multi-LLM Provider Support

**What changed**: The Full package now has a provider registry that supports multiple LLM providers, not just Claude + Gemini. Supported providers:
- **Anthropic (Claude)** — Sonnet and Opus
- **Google AI (Gemini)** — Gemini Flash
- **OpenAI** — GPT-4o, GPT-4o Mini
- **Ollama** — Any local model (Llama, DeepSeek, etc.)

Providers are auto-discovered at startup. At least one provider is required (not necessarily Claude). The router falls back gracefully across providers.

**Website updates needed**:
- Update the Full package feature list from "Multi-LLM routing (Gemini Flash → Claude Sonnet → Claude Opus)" to "Multi-LLM routing with provider registry (Claude, Gemini, OpenAI, Ollama)"
- If there's a "supported models" section, list all 4 providers
- Do NOT say "Anthropic API key required" — say "at least one LLM provider required"
- Mention Ollama support as a way to run fully local/private

### 11. Documentation Links

**What changed**: Three new documentation files were created in the Full package:
- `docs/lite-guide.md` — Lite setup walkthrough
- `docs/full-guide.md` — Full setup walkthrough with CLI reference
- `docs/configuration.md` — Complete configuration guide

**Website updates needed**:
- If the website links to package documentation, ensure these files are referenced
- If there's a "docs" section, add links to the new guides

## CHECKLIST

After making changes, verify:
- [ ] No references to `systems/my-business/` (should all be `systems/my-business-1/`)
- [ ] No references to "7-layer" (should all be "multi-layer")
- [ ] All 8 templates listed wherever templates are shown
- [ ] Cross-system context described as a working feature (no "coming soon")
- [ ] Venture CLI commands documented
- [ ] No `git clone` in user-facing download instructions
- [ ] Venture Wizard export paths include `systems/my-business-1/F-foundations/` prefix
- [ ] Feature flags described as functional
- [ ] Lite edition shows multi-venture support (3 slots)
- [ ] Multi-LLM described as supporting 4 providers (not just Claude + Gemini)
- [ ] No language implying Claude/Anthropic is the only or required provider for Full edition

## PROMPT END
