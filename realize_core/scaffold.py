"""
Project scaffolding for RealizeOS.

Creates the docs/dev-process/ directory structure with all templates,
giving users a guided development framework from day one.
"""

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from realize_core.config import get_config_path, is_config_writable

logger = logging.getLogger(__name__)


class ConfigMutationError(RuntimeError):
    """Raised when RealizeOS cannot safely persist realize-os.yaml changes."""


VENTURE_KEY_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

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


def scaffold_venture(
    project_root: str | Path,
    key: str,
    name: str = "",
    description: str = "",
    template: str = "",
) -> dict:
    """
    Create a new venture with full FABRIC directory structure.

    Copies from a template-specific FABRIC directory if available (e.g.,
    templates/real-estate/ for real estate), otherwise falls back to the
    default template at realize_lite/systems/my-business-1/.

    Args:
        project_root: Root directory of the project (where realize-os.yaml lives)
        key: Venture key (e.g., 'my-saas-app'). Used as directory name.
        name: Display name (e.g., 'My SaaS App'). Defaults to key.title().
        description: Optional description for the venture.
        template: Template name (e.g., 'real-estate'). If empty, uses default.

    Returns:
        Dict with 'created' bool, counts, and optional 'error' string.
    """
    root = Path(project_root)
    validate_venture_key(key)
    name = name or key.replace("-", " ").replace("_", " ").title()
    config_path = get_config_path(root)
    if not is_config_writable(config_path):
        raise ConfigMutationError(
            f"Config file is not writable: {config_path}. "
            "Mount realize-os.yaml as writable or set REALIZE_CONFIG to a writable config path."
        )
    venture_dir = root / "systems" / key
    stats = {"created": False, "dirs_created": 0, "files_created": 0}

    if venture_dir.exists():
        raise FileExistsError(f"Venture directory already exists: {venture_dir}")

    # Find the template source — prefer template-specific FABRIC, then default
    template_src = _find_venture_template(template)
    if not template_src:
        raise FileNotFoundError("Venture template not found. Expected realize_lite/systems/my-business-1/")

    # Copy the full FABRIC structure
    try:
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

        if stats["files_created"] == 0:
            raise FileNotFoundError(f"Venture template is empty: {template_src}")

        _customize_venture_template(venture_dir, name)
    except Exception:
        if venture_dir.exists():
            shutil.rmtree(venture_dir)
        raise

    # Update realize-os.yaml to include the new venture
    _add_venture_to_config(root, key, name, description)

    stats["created"] = True
    logger.info(f"Venture '{key}' scaffolded: {stats['dirs_created']} dirs, {stats['files_created']} files")
    return stats


def validate_venture_key(key: str) -> str:
    """Validate a user-chosen venture folder key and return it unchanged."""
    if not key:
        raise ValueError("Venture key is required.")

    if not VENTURE_KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "Invalid venture key. Use a path-safe slug with lowercase letters, numbers, and hyphens "
            "(for example: my-saas, client-work, zen-agency)."
        )

    if key in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"Invalid venture key '{key}'. This name is reserved on Windows.")

    return key


def _customize_venture_template(venture_dir: Path, name: str):
    """Lightly personalize copied starter files without changing their structure."""
    identity_file = venture_dir / "F-foundations" / "venture-identity.md"
    if not identity_file.exists():
        return

    content = identity_file.read_text(encoding="utf-8")
    content = content.replace("[Your Business Name]", name)
    identity_file.write_text(content, encoding="utf-8")


def delete_venture(project_root: str | Path, key: str, confirm_name: str = "") -> bool:
    """
    Delete a venture directory, clean up DB references, and remove from config.

    Deletion may be re-run after a previous partial delete. In that case the
    FABRIC directory can already be gone while the venture is still registered
    in realize-os.yaml or in derived indexes. Treat the missing directory as an
    idempotent cleanup path instead of raising and leaving a ghost venture.

    Args:
        project_root: Root directory of the project.
        key: Venture key to delete.
        confirm_name: Must match key to confirm deletion (safety check).

    Returns:
        True if cleanup completed successfully.
    """
    if confirm_name != key:
        raise ValueError(f"Confirmation name '{confirm_name}' does not match key '{key}'")

    root = Path(project_root)
    venture_dir = root / "systems" / key
    config_path = get_config_path(root)
    if not is_config_writable(config_path):
        raise ConfigMutationError(
            f"Config file is not writable: {config_path}. "
            "Mount realize-os.yaml as writable or set REALIZE_CONFIG to a writable config path."
        )

    # Clean up DB references (sessions, activity) before removing files.
    _cleanup_venture_db_references(key)

    # Remove from realize-os.yaml before deleting files. If config write fails,
    # we prefer to leave the files in place rather than creating a ghost venture
    # that remains registered but has no FABRIC directory.
    _remove_venture_from_config(root, key)

    # Remove directory if present. Missing directories are expected when
    # recovering from a partial delete and should not block registry cleanup.
    if venture_dir.exists():
        shutil.rmtree(venture_dir)
        logger.info(f"Deleted venture directory: {venture_dir}")
    else:
        logger.info(f"Venture directory already absent during delete: {venture_dir}")

    return True


def _cleanup_venture_db_references(venture_key: str):
    """Remove DB records associated with a deleted venture."""
    try:
        from realize_core.memory.store import db_connection

        with db_connection() as conn:
            # Clean up sessions for this venture
            conn.execute("DELETE FROM sessions WHERE system_key = ?", (venture_key,))
            # Clean up conversation history
            try:
                conn.execute(
                    "DELETE FROM conversations WHERE system_key = ?",
                    (venture_key,),
                )
            except Exception:
                pass  # Table may not exist
            # Clean up activity log
            try:
                conn.execute(
                    "DELETE FROM activity_log WHERE venture_key = ?",
                    (venture_key,),
                )
            except Exception:
                pass  # Table may not exist
        logger.info(f"Cleaned up DB references for venture '{venture_key}'")
    except Exception as e:
        logger.warning(f"DB cleanup for venture '{venture_key}' failed: {e}")


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


def _find_venture_template(template: str = "") -> Path | None:
    """
    Find the venture template directory.

    Lookup order:
    1. templates/<template>/ (template-specific FABRIC, e.g., templates/real-estate/)
    2. realize_lite/systems/my-business-1/ (default generic template)
    """
    engine_root = Path(__file__).parent.parent

    # 1. Template-specific FABRIC directory
    if template:
        template_fabric = engine_root / "templates" / template
        if template_fabric.exists() and (template_fabric / "A-agents").exists():
            return template_fabric

    # 2. Default template
    candidates = [
        engine_root / "realize_lite" / "systems" / "my-business-1",
        Path(__file__).parent / "realize_lite" / "systems" / "my-business-1",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _write_yaml_atomic(config_path: Path, config: dict):
    """Persist YAML via same-directory temp file and atomic replace."""
    import yaml

    if not is_config_writable(config_path):
        raise ConfigMutationError(f"Config file is not writable: {config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=config_path.parent,
            delete=False,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
        ) as tmp:
            yaml.dump(config, tmp, default_flow_style=False, sort_keys=False, allow_unicode=True)
            temp_name = tmp.name

        os.replace(temp_name, config_path)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise ConfigMutationError(f"Failed to write config file {config_path}: {exc}") from exc


def _add_venture_to_config(root: Path, key: str, name: str, description: str):
    """Add a venture entry to realize-os.yaml."""
    import yaml

    config_path = get_config_path(root)
    if not config_path.exists():
        # Create a minimal config so the new venture is registered.
        config = {
            "name": "RealizeOS",
            "systems": [],
            "features": {
                "review_pipeline": True,
                "auto_memory": True,
                "proactive_mode": True,
            },
        }
        _write_yaml_atomic(config_path, config)
        logger.info("Created minimal config at %s for new venture '%s'", config_path, key)

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

    _write_yaml_atomic(config_path, config)

    logger.info(f"Added venture '{key}' to {config_path}")


def _remove_venture_from_config(root: Path, key: str):
    """Remove a venture entry from realize-os.yaml."""
    import yaml

    config_path = get_config_path(root)
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    systems = config.get("systems", [])
    config["systems"] = [s for s in systems if s.get("key") != key]

    _write_yaml_atomic(config_path, config)

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
