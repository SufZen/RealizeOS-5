# Tech Spec: Phase 1 — Test Suite & CI

## Problem

RealizeOS has 5 test files with basic coverage of `config`, `prompt.builder`, `llm.router`, `skills.detector`, and `base_handler`. However, test stubs are incomplete (only happy-path covered), there are no tests for `pipeline/creative.py`, `kb/indexer.py`, or `skills/executor.py`, and there is no CI pipeline. This blocks all downstream phases because the plan gates every phase on "Tests pass."

## Solution

- Flesh out existing test files with edge cases, error paths, and boundary conditions
- Add new test files for creative pipeline lifecycle and KB indexer hybrid scoring
- Set up GitHub Actions CI with pytest + coverage reporting
- Reach 70%+ test coverage on `realize_core/`

## Scope

### IN
- Complete test coverage for: `prompt.builder`, `llm.router`, `skills.detector`, `base_handler`, `config`
- New tests for: `pipeline/creative.py`, `pipeline/session.py`, `kb/indexer.py`, `skills/executor.py`
- GitHub Actions workflow: lint + test on push/PR to main
- Coverage reporting (pytest-cov)
- `conftest.py` with shared fixtures

### OUT (explicitly excluded)
- API route tests (Phase 7+)
- Channel adapter tests (Phase 7)
- Integration tests with real LLM providers (would require API keys in CI)
- Frontend tests
- Performance/load testing

## Technical Approach

- **Key files to modify:**
  - `tests/test_prompt_builder.py` — add edge cases (missing files, empty brand, no agent match)
  - `tests/test_llm_router.py` — add edge cases (unknown task type, empty message, fallback)
  - `tests/test_skill_detector.py` — add edge cases (malformed YAML, missing triggers, empty skills dir)
  - `tests/test_base_handler.py` — add edge cases (empty routing dict, no keywords)
  - `tests/test_config.py` — add edge cases (missing file, invalid YAML, missing required keys)
- **Key files to create:**
  - `tests/conftest.py` — shared fixtures (tmp KB structure, mock configs)
  - `tests/test_creative_pipeline.py` — creative pipeline lifecycle (init, step execution, review gate)
  - `tests/test_kb_indexer.py` — KB indexer (markdown indexing, FTS5 queries, hybrid scoring)
  - `tests/test_skill_executor.py` — v1/v2 skill execution lifecycle
  - `.github/workflows/ci.yml` — GitHub Actions CI
- **Dependencies needed:** `pytest`, `pytest-cov` (add to `requirements-dev.txt`)
- **Database changes:** None
- **API changes:** None

## Acceptance Criteria

- [ ] All existing tests pass
- [ ] `test_prompt_builder.py` covers: missing file graceful fallback, empty brand, agent not found, cache behavior
- [ ] `test_llm_router.py` covers: all task types, unknown task fallback, cost-based selection
- [ ] `test_skill_detector.py` covers: empty skills dir, malformed YAML, v1 vs v2 detection
- [ ] `test_base_handler.py` covers: empty routing, no keyword match, case insensitivity
- [ ] `test_config.py` covers: missing config file defaults, invalid YAML, env var interpolation
- [ ] `test_creative_pipeline.py` covers: pipeline initialization, multi-step execution, gatekeeper review cycle
- [ ] `test_kb_indexer.py` covers: markdown file indexing, FTS5 search results, hybrid scoring with/without vector embeddings
- [ ] `test_skill_executor.py` covers: v1 pipeline execution, v2 step-by-step execution, tool step vs agent step
- [ ] GitHub Actions CI runs pytest on push/PR to `main`
- [ ] Coverage ≥ 70% on `realize_core/` package
- [ ] `conftest.py` has reusable KB and config fixtures

## Risks

- **No local Python detected** — tests need to be run in CI or manually on a device with Python installed. Consider adding a Docker-based test runner.
- **Creative pipeline and KB indexer may have complex internal state** — need to read implementation carefully to design meaningful tests.
- **Some modules may have external dependencies** (API calls, file system) — will need mocking strategy.
