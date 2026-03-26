# RealizeOS V5 — Post-Launch Roadmap

> Generated from the comprehensive codebase audit (2026-03-27)

---

## V5.1 — Cost Tracking (F9)

**Priority:** Low (user-specified)  
**Effort:** 1 sprint  
**Status:** Deferred from V5 improvement plan

### Scope

Basic per-session token counting already partially exists in the LLM router.
V5.1 would surface this data in the dashboard.

### Stories

| ID | Title | Description | Effort |
|----|-------|-------------|--------|
| ROS5-29 | Token Counter Service | Aggregate token usage per session/agent/venture from routing_decisions table | 2h |
| ROS5-30 | Cost Dashboard Widget | Dashboard widget showing daily/weekly/monthly token costs | 3h |
| ROS5-31 | Cost API Endpoint | `GET /api/costs` — aggregate cost data with date range filtering | 2h |
| ROS5-32 | Per-Model Cost Config | YAML configuration for cost-per-token by provider/model | 1h |

### Prerequisites

- `routing_decisions` table already exists (migration 002)
- Router already logs provider + model selection
- No budget enforcement needed (per user decision)

---

## V5.2 — Community Plugin Registry (F8)

**Priority:** Lower  
**Effort:** 2 sprints  
**Status:** Only local import/export done (ROS5-27/28)

### Scope

Extend the plugin system (ROS5-25/26) with a community sharing mechanism.

### Stories

| ID | Title | Description | Effort |
|----|-------|-------------|--------|
| ROS5-33 | Plugin Manifest Standard | Define `plugin.yaml` manifest schema (name, version, dependencies, permissions) | 2h |
| ROS5-34 | Plugin Marketplace API | Server-side endpoint for listing/searching available plugins | 4h |
| ROS5-35 | Plugin Install CLI | `python cli.py plugin install <name>` — download and install from registry | 3h |
| ROS5-36 | Plugin Dashboard Page | Browse, install, and manage plugins from the dashboard | 4h |
| ROS5-37 | Venture Template Gallery | Browse and clone venture templates from community | 4h |

### Prerequisites

- Plugin discovery (ROS5-25) ✅ Done
- Tool plugin interface (ROS5-26) ✅ Done
- Venture export/import (ROS5-27/28) ✅ Done

---

## V5.3 — Utility Module Cleanup

**Priority:** Low  
**Effort:** 1-2 hours  
**Status:** Identified during audit

### Actions

Review each utility module in `realize_core/utils/` and related packages:

1. **Identify single-use utilities** — If a function is only called from one location, inline it
2. **Consolidate related utilities** — Merge small utility modules with overlapping concerns
3. **Remove dead helpers** — Functions that are defined but never imported

### Candidate Modules to Review

| Module | Location | Assessment |
|--------|----------|------------|
| `realize_core/tools/automation.py` | Tools | Check if used outside tests |
| `realize_core/tools/doc_generator.py` | Tools | Check if wired into any workflow |
| `realize_core/tools/gating.py` | Tools | Check if used by approval system |
| `realize_core/tools/telephony.py` | Tools | Check if wired or experimental |
| `realize_core/tools/voice.py` | Tools | Check if wired or experimental |

---

## Routing Engine Consolidation (Future)

**Priority:** Medium (when ready for a breaking change)  
**Effort:** 1 sprint  

The codebase has two routing modules:
- `realize_core/llm/router.py` — Active, used by 6+ modules  
- `realize_core/llm/routing_engine.py` — Advanced but unwired (YAML-driven strategies)

### Recommended Approach

1. Extract the YAML strategy loading from `routing_engine.py`
2. Integrate strategy selection into `router.py`'s `select_model()` function
3. Migrate callers gradually (behind feature flag)
4. Remove `routing_engine.py` once all callers are migrated

This would give the production router the benefits of YAML-driven configuration
without a risky wholesale replacement.
