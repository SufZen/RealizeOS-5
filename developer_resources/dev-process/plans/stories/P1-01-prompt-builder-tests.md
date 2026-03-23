# Story: Complete test stubs for prompt builder

## Epic: Phase 1 — Test Suite & CI
## Priority: P0
## Status: in-progress

## Description

Expand `tests/test_prompt_builder.py` with edge-case coverage. The existing test file has 5 happy-path tests. Need to add tests for: missing files, empty brand, agent not found, cache behavior, channel format selection, truncation, session layer, proactive instructions, and warm_cache.

## Acceptance Criteria

- [ ] Test missing identity file → prompt still builds (graceful fallback)
- [ ] Test missing brand files → prompt still builds
- [ ] Test agent not found in config → returns empty, no crash
- [ ] Test cache behavior: read once, cache hit on second call
- [ ] Test clear_cache() invalidates entries
- [ ] Test channel format: telegram, api, slack, unknown channel
- [ ] Test truncation: file > max_chars gets truncated marker
- [ ] Test session layer with mock session object
- [ ] Test proactive instructions include push-back protocol
- [ ] Test agent-specific proactive text (writer vs analyst)

## Technical Notes

- `_read_kb_file()` returns "" on FileNotFoundError — test this graceful degradation
- `_file_cache` is tested via `clear_cache()` and repeated reads
- Channel format instructions are in `CHANNEL_FORMAT_INSTRUCTIONS` dict
- Session layer expects an object with `.task_type`, `.stage`, `.brief`, `.pipeline`, `.pipeline_index` attributes
- All tests use `tmp_path` fixture for isolated KB structure

## Dependencies

- None (first story in sprint)

## Files Affected

- `tests/test_prompt_builder.py` — expand with edge cases
- `tests/conftest.py` — create shared fixtures
