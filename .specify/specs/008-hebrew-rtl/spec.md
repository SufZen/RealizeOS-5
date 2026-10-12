# Feature Specification: Hebrew and Right-to-Left

**Feature Branch**: `feat/story-19-hebrew-rtl`
**Created**: 2026-10-11
**Status**: Implemented (5.7.0)
**Input**: RealizeOS upgrade brief, item 5. A Hebrew venture reads naturally: right-to-left layout,
Hebrew content in chat, approvals and the trail. UI labels stay English for now.

## User Scenarios & Testing

### User Story 1 — A Hebrew venture is right-to-left (P1)

**Acceptance**:
1. **Given** a venture with `locale: he`, **when** it is selected, **then** `<html lang="he" dir="rtl">`
   and the layout mirrors: sidebar on the right, user bubbles at the inline end.
2. **Given** a Hebrew answer with English terms, figures and `[S1]` footnotes, **then** it reads in
   the right order; the trail and approval cards keep Hebrew titles and English paths readable.
3. **Given** the language button, **then** a person can force Hebrew or English (stored per browser).

### Edge cases

- Signing out returns the page to English LTR.
- Timestamps, tool names, durations and file paths are direction-isolated (`<bdi>`).
- The sidebar scrolls on its own on short screens.

## Requirements

- **FR-001** `GET /api/ventures` returns each venture's `locale`.
- **FR-002** `LocaleProvider` (inside `VentureProvider`) sets `<html lang dir>` from the selected
  venture, with a per-browser override; `lib/locale.ts` maps languages to directions.
- **FR-003** Messages and approval fields use `dir="auto"`; the trail follows the page direction
  with mixed pieces isolated.
- **FR-004** Layout classes are logical (`ms-/me-/ps-/pe-/start-/end-/text-start/border-s/...`);
  no physical-direction Tailwind classes remain in the dashboard.

## Success Criteria

- The webinar's Hebrew demo venture renders right-to-left in chat, approvals and the trail, checked
  in a browser.

## Assumptions

- Hebrew UI labels (i18n) come later; content direction is what matters for the demo.
