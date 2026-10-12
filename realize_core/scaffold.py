"""
Project scaffolding for RealizeOS.

Creates the docs/dev-process/ directory structure with all templates,
giving users a guided development framework from day one.
"""

import logging
import os
import re
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

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
    venture_dir = root / "systems" / key
    stats = {"created": False, "dirs_created": 0, "files_created": 0}

    if venture_dir.exists():
        raise FileExistsError(f"Venture directory already exists: {venture_dir}")
    _require_writable_config(root)

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

        # Register in realize-os.yaml inside the rollback block, so a failed
        # config write doesn't leave an orphan directory behind.
        _add_venture_to_config(root, key, name, description)
    except Exception:
        if venture_dir.exists():
            shutil.rmtree(venture_dir)
        raise

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


def find_venture_dir(kb_path: Path | str, venture_key: str) -> Path | None:
    """Locate an existing venture directory without building a path from input.

    ``venture_key`` often comes straight from a query string or request body.
    Instead of joining it into a path (which allows ``..`` traversal), it is
    MATCHED against the real directory names under ``systems/`` (v5.5.0+)
    and then the legacy ``ventures/`` root, and the matching filesystem entry
    is returned. Returns ``None`` when nothing matches.
    """
    if not venture_key:
        return None
    for root_name in ("systems", "ventures"):
        root = Path(kb_path) / root_name
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name == venture_key:
                return child
    return None


def _customize_venture_template(venture_dir: Path, name: str):
    """Lightly personalize copied starter files without changing their structure."""
    identity_file = venture_dir / "F-foundations" / "venture-identity.md"
    if not identity_file.exists():
        return

    content = identity_file.read_text(encoding="utf-8")
    content = content.replace("[Your Business Name]", name)
    identity_file.write_text(content, encoding="utf-8")


class VentureConfigReadOnlyError(OSError):
    """realize-os.yaml cannot be written (for example a read-only Docker mount)."""


def config_writable(project_root: str | Path) -> bool:
    """Return True when realize-os.yaml (or its folder, if it doesn't exist yet) is writable.

    Venture create and delete edit this file, so the API and dashboard use this
    to refuse or hide those actions instead of failing half-way.
    """
    root = Path(project_root)
    config_path = root / "realize-os.yaml"
    target = config_path if config_path.exists() else root
    return os.access(target, os.W_OK)


def _require_writable_config(root: Path) -> None:
    """Raise VentureConfigReadOnlyError when realize-os.yaml can't be edited."""
    if not config_writable(root):
        raise VentureConfigReadOnlyError(
            f"{root / 'realize-os.yaml'} is read-only, so ventures can't be created or deleted here. "
            "Mount it read-write or edit it on the host."
        )


def _resolve_venture_dir(root: Path, key: str, sys_conf: dict | None) -> Path | None:
    """Return the venture's directory, read from its config entry, or None if it has none on disk.

    Uses the configured ``directory`` (which can differ from the key, e.g.
    ``systems/realization.co.il``) and refuses anything that isn't directly
    inside ``systems/`` or ``ventures/``, so a bad entry can never delete the project.
    """
    if sys_conf and sys_conf.get("directory"):
        candidate = (root / str(sys_conf["directory"])).resolve()
    else:
        found = find_venture_dir(root, key)
        if found is None:
            return None
        candidate = found.resolve()

    allowed_roots = [(root / name).resolve() for name in ("systems", "ventures")]
    if not any(candidate.parent == allowed for allowed in allowed_roots):
        raise ValueError(f"Refusing to delete '{candidate}': it is not a folder directly under systems/ or ventures/.")
    if not candidate.is_dir():
        return None
    return candidate


def delete_venture(project_root: str | Path, key: str, confirm_name: str = "") -> dict:
    """
    Delete a venture: its config entry, its DB references and its directory.

    The irreversible steps come last. The directory is first renamed aside, then
    the config is rewritten; if the config write fails the directory is renamed
    back and nothing has changed. A venture that is only in the config (its
    directory is already gone) is removed from the config with a warning.

    Args:
        project_root: Root directory of the project (where realize-os.yaml lives).
        key: Venture key to delete.
        confirm_name: Must match key to confirm deletion (safety check).

    Returns:
        Dict with ``deleted`` (True), ``directory`` (str or None) and ``warnings`` (list).

    Raises:
        ValueError: confirmation mismatch or an unsafe or shared configured directory.
        FileNotFoundError: the venture is neither configured nor on disk.
        VentureConfigReadOnlyError: realize-os.yaml can't be written.
        OSError: the directory couldn't be moved or the config couldn't be written.
    """
    if confirm_name != key:
        raise ValueError(f"Confirmation name '{confirm_name}' does not match key '{key}'")

    root = Path(project_root)
    config = _load_config_file(root)
    systems = _config_systems(config)
    sys_conf = next((s for s in systems if s.get("key") == key), None)
    venture_dir = _resolve_venture_dir(root, key, sys_conf)

    if sys_conf is None and venture_dir is None:
        raise FileNotFoundError(f"Venture '{key}' is not configured and has no directory")

    if venture_dir is not None:
        shared = [
            s.get("key")
            for s in systems
            if s.get("key") != key and s.get("directory") and (root / str(s["directory"])).resolve() == venture_dir
        ]
        if shared:
            raise ValueError(f"Directory {venture_dir} is also used by venture(s) {shared}; not deleting it.")

    if sys_conf is not None:
        _require_writable_config(root)

    warnings: list[str] = []

    # 1. Move the directory aside (reversible).
    staged: Path | None = None
    if venture_dir is not None:
        staged = venture_dir.with_name(f".deleting-{venture_dir.name}-{int(time.time())}")
        venture_dir.rename(staged)
    else:
        warnings.append(f"Venture '{key}' had no directory on disk; removed it from the config only.")
        logger.warning("Venture '%s' has no directory; removing config entry only", key)

    # 2. Commit the config change; undo the move if it fails.
    if sys_conf is not None:
        try:
            _remove_venture_from_config(root, key)
        except OSError:
            if staged is not None and venture_dir is not None:
                staged.rename(venture_dir)
            raise

    # 3. Irreversible clean-up. A failure here leaves stale data, not a broken venture.
    _cleanup_venture_db_references(key)
    if staged is not None:
        try:
            shutil.rmtree(staged)
            logger.info("Deleted venture directory: %s", venture_dir)
        except OSError as e:
            warnings.append(f"Removed the venture, but could not delete {staged}: {e}")
            logger.warning("Venture '%s' removed but staged directory %s remains: %s", key, staged, e)

    return {"deleted": True, "directory": str(venture_dir) if venture_dir else None, "warnings": warnings}


def _cleanup_venture_db_references(venture_key: str):
    """Remove DB records associated with a deleted venture."""
    import sqlite3

    try:
        from realize_core.memory.store import db_connection

        with db_connection() as conn:
            for statement in (
                "DELETE FROM sessions WHERE system_key = ?",
                # Conversation rows carry the venture key in bot_name.
                "DELETE FROM conversations WHERE bot_name = ?",
            ):
                try:
                    conn.execute(statement, (venture_key,))
                except sqlite3.OperationalError as e:
                    logger.debug("Venture cleanup skipped (%s): %s", statement, e)
        logger.info(f"Cleaned up DB references for venture '{venture_key}'")
    except (sqlite3.Error, OSError, ImportError) as e:
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


def _add_venture_to_config(root: Path, key: str, name: str, description: str):
    """Add a venture entry to realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        # Create a minimal config so the new venture is registered
        import yaml

        config = {
            "name": "RealizeOS",
            "systems": [],
            "features": {
                "review_pipeline": True,
                "auto_memory": True,
                "proactive_mode": True,
            },
        }
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
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

    _write_config_text(config_path, yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True))

    logger.info(f"Added venture '{key}' to {config_path}")


def _remove_venture_from_config(root: Path, key: str):
    """Remove a venture entry from realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        return

    config = _load_config_file(root)
    systems = config.get("systems", []) or []
    config["systems"] = [s for s in systems if s.get("key") != key]

    _write_config_text(config_path, yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True))
    logger.info(f"Removed venture '{key}' from {config_path}")


def _config_systems(config: dict) -> list[dict]:
    """Return the ``systems:`` list entries that are well-formed dicts (others are ignored)."""
    systems = config.get("systems") or []
    if not isinstance(systems, list):
        return []
    return [s for s in systems if isinstance(s, dict)]


def _load_config_file(root: Path) -> dict:
    """Read realize-os.yaml as a dict (empty when missing)."""
    import yaml

    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_config_text(config_path: Path, text: str) -> None:
    """Replace realize-os.yaml with ``text`` without leaving a half-written file.

    Writes a temp file next to it and renames it over the original. A single
    file bind-mounted into a container can't be renamed over (EBUSY/EXDEV) and
    its folder may be read-only; then it falls back to rewriting the file in
    place, which still only happens once the new text is fully built.
    """
    tmp_path = config_path.with_name(f".{config_path.name}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, config_path)
        return
    except OSError as e:
        logger.debug("Atomic replace of %s failed (%s); writing in place", config_path, e)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove temp file %s", tmp_path)
    config_path.write_text(text, encoding="utf-8")


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
