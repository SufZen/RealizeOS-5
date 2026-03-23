"""
Project scaffolding for RealizeOS.

Creates the docs/dev-process/ directory structure with all templates,
giving users a guided development framework from day one.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Templates that get copied during init
TEMPLATES_DIR = Path(__file__).parent.parent / "docs" / "dev-process" / "templates"

# Directory structure to create
DEV_PROCESS_STRUCTURE = {
    "docs/dev-process": {
        "files": ["_README.md"],
        "subdirs": {
            "active": {
                "files": [
                    "current-focus.md",
                    "session-log.md",
                    "project-context.md",
                    "sprint-status.yaml",
                ],
            },
            "plans": {
                "files": ["_template.md"],
                "subdirs": {
                    "stories": {"files": []},
                },
            },
            "decisions": {
                "files": ["_template.md"],
            },
            "reference": {
                "files": [],
            },
            "templates": {
                "files": [],  # Copied from source templates
            },
        },
    },
}

# Template file mapping: target filename → source template
TEMPLATE_MAP = {
    "docs/dev-process/active/current-focus.md": "current-focus-template.md",
    "docs/dev-process/active/session-log.md": "session-log-template.md",
    "docs/dev-process/active/project-context.md": "project-context-template.md",
    "docs/dev-process/active/sprint-status.yaml": "sprint-status-template.yaml",
    "docs/dev-process/plans/_template.md": "plan-template.md",
    "docs/dev-process/decisions/_template.md": "adr-template.md",
}

# README content (inline to avoid dependency on existing files)
README_CONTENT = """\
# Development Process

> A structured framework for building and evolving your RealizeOS system.

## Quick Start

1. **Read** `active/project-context.md` — your project's constitution
2. **Check** `active/current-focus.md` — what's being worked on now
3. **Log** `active/session-log.md` — record what you did each session

## Directory Structure

```
docs/dev-process/
├── _README.md              ← You are here
├── active/                 ← Current state (always up to date)
│   ├── project-context.md  ← Project constitution
│   ├── current-focus.md    ← Active work streams
│   ├── session-log.md      ← Session history
│   └── sprint-status.yaml  ← Story tracking
├── plans/                  ← Development plans
│   ├── _template.md        ← Plan template
│   └── stories/            ← Individual story files
├── decisions/              ← Architecture Decision Records
│   └── _template.md        ← ADR template
├── reference/              ← Analysis docs, research
└── templates/              ← All templates for reference
```

## Session Protocol

### Starting a Session
1. Read `active/current-focus.md` to understand what's in progress
2. Check `active/session-log.md` for context from the last session
3. Review `active/sprint-status.yaml` for your current stories

### Ending a Session
1. Update `active/session-log.md` with what you did
2. Update `active/current-focus.md` if the status changed
3. Update `active/sprint-status.yaml` if stories progressed
4. Leave a clear handoff note for the next session

### Switching Devices
Use the session log and current focus as your "handoff document"
between devices and tools. Always write as if someone else will
pick up your work tomorrow.
"""


def scaffold_dev_process(project_root: str | Path, force: bool = False) -> dict:
    """
    Create the docs/dev-process/ directory structure with templates.

    Args:
        project_root: Root directory of the project
        force: If True, overwrite existing files

    Returns:
        Dict with counts of created dirs, files, skipped items
    """
    root = Path(project_root)
    stats = {"dirs_created": 0, "files_created": 0, "skipped": 0}

    # Create directory structure
    dirs_to_create = [
        root / "docs" / "dev-process",
        root / "docs" / "dev-process" / "active",
        root / "docs" / "dev-process" / "plans",
        root / "docs" / "dev-process" / "plans" / "stories",
        root / "docs" / "dev-process" / "decisions",
        root / "docs" / "dev-process" / "reference",
        root / "docs" / "dev-process" / "templates",
    ]

    for dir_path in dirs_to_create:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            stats["dirs_created"] += 1
            logger.info(f"Created directory: {dir_path}")

    # Write README
    readme_path = root / "docs" / "dev-process" / "_README.md"
    if not readme_path.exists() or force:
        readme_path.write_text(README_CONTENT, encoding="utf-8")
        stats["files_created"] += 1
    else:
        stats["skipped"] += 1

    # Copy templates from source
    templates_src = _find_templates_dir()
    if templates_src and templates_src.exists():
        templates_dest = root / "docs" / "dev-process" / "templates"
        for template_file in templates_src.glob("*.md"):
            dest = templates_dest / template_file.name
            if not dest.exists() or force:
                shutil.copy2(template_file, dest)
                stats["files_created"] += 1
            else:
                stats["skipped"] += 1

        for template_file in templates_src.glob("*.yaml"):
            dest = templates_dest / template_file.name
            if not dest.exists() or force:
                shutil.copy2(template_file, dest)
                stats["files_created"] += 1
            else:
                stats["skipped"] += 1

    # Create active files from templates
    for target_rel, template_name in TEMPLATE_MAP.items():
        target_path = root / target_rel
        if not target_path.exists() or force:
            template_content = _read_template(template_name)
            if template_content:
                target_path.write_text(template_content, encoding="utf-8")
                stats["files_created"] += 1
                logger.info(f"Created from template: {target_path}")
            else:
                logger.warning(f"Template not found: {template_name}")
        else:
            stats["skipped"] += 1

    logger.info(
        f"Dev process scaffold complete: "
        f"{stats['dirs_created']} dirs, {stats['files_created']} files created, "
        f"{stats['skipped']} skipped"
    )
    return stats


def scaffold_venture(project_root: str | Path, key: str, name: str = "", description: str = "") -> dict:
    """
    Create a new venture with full FABRIC directory structure.

    Copies the template from realize_lite/systems/my-business-1/ to give users
    a complete starting point with agents, skills, and knowledge base files.

    Args:
        project_root: Root directory of the project (where realize-os.yaml lives)
        key: Venture key (e.g., 'my-saas-app'). Used as directory name.
        name: Display name (e.g., 'My SaaS App'). Defaults to key.title().
        description: Optional description for the venture.

    Returns:
        Dict with counts of created dirs and files.
    """
    root = Path(project_root)
    name = name or key.replace("-", " ").replace("_", " ").title()
    venture_dir = root / "systems" / key
    stats = {"dirs_created": 0, "files_created": 0}

    if venture_dir.exists():
        raise FileExistsError(f"Venture directory already exists: {venture_dir}")

    # Find the template source (realize_lite/systems/my-business-1/)
    template_src = _find_venture_template()
    if not template_src:
        raise FileNotFoundError("Venture template not found. Expected realize_lite/systems/my-business-1/")

    # Copy the full FABRIC structure
    for item in template_src.rglob("*"):
        relative = item.relative_to(template_src)
        dest = venture_dir / relative
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            stats["dirs_created"] += 1
        elif item.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            stats["files_created"] += 1

    # Update realize-os.yaml to include the new venture
    _add_venture_to_config(root, key, name, description)

    logger.info(f"Venture '{key}' scaffolded: {stats['dirs_created']} dirs, {stats['files_created']} files")
    return stats


def delete_venture(project_root: str | Path, key: str, confirm_name: str = "") -> bool:
    """
    Delete a venture directory and remove it from realize-os.yaml.

    Args:
        project_root: Root directory of the project.
        key: Venture key to delete.
        confirm_name: Must match key to confirm deletion (safety check).

    Returns:
        True if deleted successfully.
    """
    if confirm_name != key:
        raise ValueError(f"Confirmation name '{confirm_name}' does not match key '{key}'")

    root = Path(project_root)
    venture_dir = root / "systems" / key

    if not venture_dir.exists():
        raise FileNotFoundError(f"Venture directory not found: {venture_dir}")

    # Remove directory
    shutil.rmtree(venture_dir)
    logger.info(f"Deleted venture directory: {venture_dir}")

    # Remove from realize-os.yaml
    _remove_venture_from_config(root, key)

    return True


def list_ventures(project_root: str | Path) -> list[dict]:
    """
    List all ventures configured in realize-os.yaml.

    Returns:
        List of dicts with key, name, directory, and exists (bool).
    """
    import yaml

    root = Path(project_root)
    config_path = root / "realize-os.yaml"

    if not config_path.exists():
        return []

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    ventures = []
    for sys_conf in config.get("systems", []):
        key = sys_conf.get("key", "")
        directory = sys_conf.get("directory", f"systems/{key}")
        ventures.append(
            {
                "key": key,
                "name": sys_conf.get("name", key),
                "directory": directory,
                "exists": (root / directory).exists(),
            }
        )

    return ventures


def _find_venture_template() -> Path | None:
    """Find the venture template directory (realize_lite/systems/my-business-1/)."""
    candidates = [
        Path(__file__).parent.parent / "realize_lite" / "systems" / "my-business-1",
        Path(__file__).parent / "realize_lite" / "systems" / "my-business-1",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _add_venture_to_config(root: Path, key: str, name: str, description: str):
    """Add a venture entry to realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    systems = config.setdefault("systems", [])

    # Check if key already exists
    for sys_conf in systems:
        if sys_conf.get("key") == key:
            logger.info(f"Venture '{key}' already in config, skipping")
            return

    new_system = {
        "key": key,
        "name": name,
        "directory": f"systems/{key}",
        "routing": {
            "content": ["writer", "reviewer"],
            "strategy": ["analyst", "orchestrator"],
            "general": ["orchestrator"],
        },
        "agent_routing": {
            "writer": ["write", "draft", "post", "blog", "content"],
            "analyst": ["analyze", "research", "data", "market"],
            "reviewer": ["review", "check", "quality", "approve"],
            "orchestrator": ["plan", "help", "think", "prioritize"],
        },
    }
    if description:
        new_system["description"] = description

    systems.append(new_system)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info(f"Added venture '{key}' to {config_path}")


def _remove_venture_from_config(root: Path, key: str):
    """Remove a venture entry from realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    systems = config.get("systems", [])
    config["systems"] = [s for s in systems if s.get("key") != key]

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info(f"Removed venture '{key}' from {config_path}")


def _find_templates_dir() -> Path | None:
    """Find the templates directory, checking multiple possible locations."""
    # Check relative to this module (installed package)
    candidates = [
        TEMPLATES_DIR,
        Path(__file__).parent / "templates",
        Path(__file__).parent.parent / "docs" / "dev-process" / "templates",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_template(template_name: str) -> str | None:
    """Read a template file by name."""
    templates_dir = _find_templates_dir()
    if not templates_dir:
        return None

    template_path = templates_dir / template_name
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return None
