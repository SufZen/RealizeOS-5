"""
AI tool context file generator for Developer Mode.

Generates context/instruction files for supported AI coding tools,
embedding the RealizeOS architecture overview, file protection rules,
and extension-first development guidance.

Supported tools:
  - Claude Desktop / Claude Code CLI  → CLAUDE.md + .claude/settings.local.json
  - Gemini CLI / Google Antigravity   → .gemini/GEMINI.md + .gemini/settings.json
  - VS Code (Copilot)                 → .github/copilot-instructions.md
  - Cursor                            → .cursorrules
  - Windsurf                          → .windsurfrules
  - Codex                             → AGENTS.md
  - Aider                             → .aider.conf.yml
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from realize_core.devmode.protection import FileProtection, ProtectionTier

logger = logging.getLogger(__name__)


def _build_shared_context(protection: FileProtection) -> str:
    """Build shared context text used by all AI tool files."""
    tiers = protection.get_all_tiers()

    protected_list = "\n".join(f"  - {p}" for p in tiers[ProtectionTier.PROTECTED])
    guarded_list = "\n".join(f"  - {p}" for p in tiers[ProtectionTier.GUARDED])
    open_list = "\n".join(f"  - {p}" for p in tiers[ProtectionTier.OPEN])

    return f"""# RealizeOS V5 — AI Development Context

## About This System
RealizeOS is an AI operations engine with a Python backend (FastAPI), React dashboard,
and FABRIC file-based architecture. It uses multi-LLM routing, agent pipelines,
skill detection, and an extension system.

## Architecture
```
realize_core/     — Python engine (prompt builder, LLM router, tools, security, DB)
realize_api/      — FastAPI REST API endpoints
dashboard/        — React 19 + Vite + TypeScript + Tailwind UI
extensions/       — User extensions (auto-discovered at startup)
systems/          — User FABRIC data (agents, routines, knowledge bases)
cli.py            — CLI entry point
realize-os.yaml   — System configuration + feature flags
```

## ⚠️ File Protection Rules (Level: {protection.level})
{protection.level_description}

### 🔴 PROTECTED — Do NOT modify without explicit user approval
{protected_list}

### 🟡 GUARDED — Editable, but auto-backed-up first
{guarded_list}

### 🟢 OPEN — Freely editable
{open_list}

## 🧩 Extension-First Development
**IMPORTANT:** When adding new features, ALWAYS create an extension instead of
modifying core files. Use the scaffolder:

```bash
python cli.py devmode scaffold --type tool --name my-feature
```

This creates a proper extension in `extensions/my-feature/` with manifest,
boilerplate, and tests. RealizeOS auto-discovers extensions at startup.

Extension types: tool, channel, integration, hook

## Critical Rules
- Never break existing functionality (CLI, API, FABRIC)
- New features go behind feature flags in realize-os.yaml
- FABRIC stays file-based — do not migrate to database
- SQLite only — do not add PostgreSQL
- SSE only — do not add WebSocket
- Always run `python cli.py devmode check` after making changes

## Excluded Files (NEVER read or expose)
- .env (contains API keys)
- .credentials/ (OAuth tokens)
- backups/ (user data)
- *.sqlite, *.db (databases)

## After Making Changes
Run the health check to validate your modifications:
```bash
python cli.py devmode check
```
"""


def generate_claude_md(root: Path, protection: FileProtection) -> Path:
    """Generate CLAUDE.md for Claude Desktop / Claude Code CLI."""
    content = _build_shared_context(protection)
    content += """
## Claude-Specific Instructions
- Use the extension system for new features
- Run `python cli.py devmode check` after modifications
- Do not read .env or .credentials/
- Prefer creating files in extensions/ over modifying realize_core/
"""
    path = root / "CLAUDE.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_claude_settings(root: Path, protection: FileProtection) -> Path:
    """Generate .claude/settings.local.json with scoped permissions."""
    settings: dict[str, Any] = {
        "permissions": {
            "allow": [
                "Bash(python cli.py devmode check)",
                "Bash(python cli.py devmode scaffold:*)",
                "Bash(python -m pytest tests/:*)",
                "Bash(npm run build:*)",
                "Bash(python cli.py status)",
                "Bash(python cli.py devmode snapshot:*)",
            ],
            "deny": [
                "Read(//.env)",
                "Read(//.credentials/**)",
                "Write(//realize_core/security/**)",
                "Write(//realize_core/db/**)",
            ],
        }
    }
    path = root / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_gemini_md(root: Path, protection: FileProtection) -> Path:
    """Generate .gemini/GEMINI.md for Gemini CLI / Google Antigravity."""
    content = _build_shared_context(protection)
    content += """
## Gemini-Specific Instructions
- Follow the extension-first approach for all new features
- Use `python cli.py devmode scaffold` for boilerplate
- Run health check after every session
- Do not access .env or credential files
"""
    path = root / ".gemini" / "GEMINI.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_gemini_settings(root: Path, _protection: FileProtection) -> Path:
    """Generate .gemini/settings.json."""
    settings: dict[str, Any] = {
        "context_files": [".gemini/GEMINI.md"],
        "excluded_paths": [".env", ".credentials/", "backups/", "*.sqlite"],
    }
    path = root / ".gemini" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_copilot_instructions(root: Path, protection: FileProtection) -> Path:
    """Generate .github/copilot-instructions.md for VS Code Copilot."""
    content = _build_shared_context(protection)
    content += """
## Copilot-Specific Instructions
- Suggest code completions following existing patterns
- Prefer extensions/ for new features over core modifications
- Follow Python type hints and docstring conventions
"""
    path = root / ".github" / "copilot-instructions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_cursorrules(root: Path, protection: FileProtection) -> Path:
    """Generate .cursorrules for Cursor."""
    content = _build_shared_context(protection)
    path = root / ".cursorrules"
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_windsurfrules(root: Path, protection: FileProtection) -> Path:
    """Generate .windsurfrules for Windsurf."""
    content = _build_shared_context(protection)
    path = root / ".windsurfrules"
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_agents_md(root: Path, protection: FileProtection) -> Path:
    """Generate AGENTS.md for Codex."""
    content = _build_shared_context(protection)
    content += """
## Codex-Specific Instructions
- Create extensions for new features using the scaffold CLI
- All new Python code must have type hints and docstrings
- Run tests after every modification
"""
    path = root / "AGENTS.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


def generate_aider_config(root: Path, _protection: FileProtection) -> Path:
    """Generate .aider.conf.yml for Aider."""
    content = """# Aider configuration for RealizeOS
read:
  - CLAUDE.md
lint-cmd: python -m pytest tests/ -q --tb=no
auto-commits: true
map-tokens: 2048
"""
    path = root / ".aider.conf.yml"
    path.write_text(content, encoding="utf-8")
    logger.info("Generated %s", path)
    return path


# Registry mapping tool keys to generator functions
GENERATORS: dict[str, list] = {
    "claude_desktop": [generate_claude_md, generate_claude_settings],
    "claude_code_cli": [generate_claude_md, generate_claude_settings],
    "gemini_cli": [generate_gemini_md, generate_gemini_settings],
    "antigravity": [generate_gemini_md, generate_gemini_settings],
    "vscode": [generate_copilot_instructions],
    "cursor": [generate_cursorrules],
    "windsurf": [generate_windsurfrules],
    "codex": [generate_agents_md],
    "aider": [generate_aider_config],
}


def generate_all(
    root: Path | None = None,
    level: str = "standard",
    tools: list[str] | None = None,
) -> list[Path]:
    """
    Generate context files for all (or selected) AI tools.

    Args:
        root: Project root directory.
        level: Protection level (strict/standard/relaxed).
        tools: List of tool keys. None = all tools.

    Returns:
        List of generated file paths.
    """
    root = root or Path.cwd()
    protection = FileProtection(level=level, root=root)
    generated: list[Path] = []
    seen_generators: set[int] = set()

    target_tools = tools if tools else list(GENERATORS.keys())

    for tool_key in target_tools:
        generators = GENERATORS.get(tool_key, [])
        for gen_fn in generators:
            # Avoid duplicate generation (claude_desktop + claude_code_cli share generators)
            fn_id = id(gen_fn)
            if fn_id in seen_generators:
                continue
            seen_generators.add(fn_id)
            try:
                path = gen_fn(root, protection)
                generated.append(path)
            except Exception as e:
                logger.error("Failed to generate for %s: %s", tool_key, e)

    logger.info("Generated %d context files for %d tools", len(generated), len(target_tools))
    return generated
