# Lite Edition Guide

RealizeOS Lite runs entirely inside Obsidian + Claude Code. No servers, no Docker, no coding required.

## Requirements

- [Obsidian](https://obsidian.md) (free)
- Claude Pro subscription ($20/mo) for Claude Code access

## Setup

1. **Download** the Lite package and unzip it
2. **Open as Obsidian vault**: Obsidian → "Open folder as vault" → select the unzipped folder
3. **Follow `setup-guide.md`** — the in-vault setup wizard walks you through:
   - Filling in `shared/identity.md` (who you are)
   - Completing `shared/venture-worksheet.md` (guided venture builder)
   - Generating `F-foundations/venture-identity.md` and `F-foundations/venture-voice.md`
   - Reviewing agent definitions in `A-agents/`
4. **Start Claude Code** in the vault directory — Claude reads `CLAUDE.md` and becomes your AI team

## Directory Structure

Your vault uses the FABRIC system:

```
systems/my-business-1/
├── F-foundations/    Venture identity and voice rules
├── A-agents/        Agent team definitions
├── B-brain/         Domain knowledge and expertise
├── R-routines/      Skills, workflows, state maps
├── I-insights/      Memory and learning log
└── C-creations/     Your deliverables and outputs
```

## Adding More Ventures

The Lite package includes 3 venture slots (`my-business-1`, `my-business-2`, `my-business-3`). To activate a new venture:

1. Navigate to `systems/my-business-2/`
2. Fill in the `F-foundations/` files with the new venture's identity
3. Update `realize-os.yaml` to include the new system
4. Claude will automatically discover the new agents and skills

## Customizing

- **Add agents**: Create new `.md` files in `A-agents/` — auto-discovered
- **Add skills**: Create new `.yaml` files in `R-routines/skills/` — auto-detected
- **Add knowledge**: Drop `.md` files in `B-brain/` for domain expertise
- **Add methods**: Add reusable SOPs to `shared/methods/`

## Next Steps

- [Core Concepts](concepts.md)
- [Skill Authoring Guide](skill-authoring.md)
