# RealizeOS Lite

> **Status:** Preserved for backward compatibility. Not actively developed in V5.

## What Is This?

RealizeOS Lite is a **standalone, server-independent** version of RealizeOS designed
for users who want AI-assisted operation management without running the full FastAPI
server and dashboard.

## Relationship to Main Codebase

| Feature | RealizeOS Full (V5) | RealizeOS Lite |
|---------|---------------------|----------------|
| Architecture | FastAPI server + React dashboard | CLI-only, no server |
| Dependencies | Python 3.12+, Node.js 20+ | Python 3.12+ only |
| Dashboard | ✅ Full web dashboard | ❌ Not available |
| FABRIC | ✅ Full KB + index | ✅ File-based only |
| LLM Routing | ✅ Multi-provider with fallback | ✅ Basic routing |
| Scheduling | ✅ APScheduler heartbeats | ❌ Manual only |

## Directory Structure

```
realize_lite/
├── CLAUDE.md           # AI assistant context for Lite mode
├── realize-os.yaml     # Lite-specific configuration
├── setup-guide.md      # Standalone setup instructions
├── shared/             # Shared templates and resources
│   ├── identity.md
│   ├── methods/
│   ├── user-preferences.md
│   └── venture-worksheet.md
└── systems/            # Venture data (gitignored)
```

## Future Plans

The Lite tier is **deferred** beyond V5 launch (per improvement plan F8/F9 priorities).
Future options include:
- Static HTML export of dashboard data
- Standalone Electron wrapper
- Extraction to separate `realizeos-lite` repository

## For Contributors

Do **not** modify files in this directory unless specifically working on Lite-tier
features. All active development should target the main `realize_core/` and
`realize_api/` directories.
