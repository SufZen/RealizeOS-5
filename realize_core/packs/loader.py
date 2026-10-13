"""Load profession, market and firm packs from disk (spec 010 §4).

Packs are content only. Loading is tolerant: a problem becomes a warning on
the pack (logged once, with the file's path), and a broken file never stops
the rest of the pack from loading. A pack that can't be loaded at all is
skipped with a warning and never stops another pack from loading (audit N06).

Packs come from up to two folders (:func:`pack_roots`), highest priority
first:

1. ``REALIZE_PACKS_PATH``, an optional writable folder for the firm's own or
   modified packs (a mounted volume in Docker). A pack here replaces a shipped
   pack with the same kind and id.
2. The packs that ship with RealizeOS (``packs/``). In the production image
   this folder is read-only.

Every pack loaded here gets the verification state that approvals recorded
under ``DATA_PATH`` laid over it (:mod:`realize_core.packs.state`), so
approvals never have to write into pack folders (audit N04).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from realize_core.packs.models import Pack, RuleCard

logger = logging.getLogger(__name__)

PACK_KINDS = ("profession", "market")

#: Environment variable naming the optional writable pack folder.
PACKS_PATH_ENV = "REALIZE_PACKS_PATH"

#: Errors a malformed pack file can raise while it is read or indexed. A pack
#: that raises one of these is skipped with a warning instead of stopping the
#: other packs (audit N06).
LOAD_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
    yaml.YAMLError,
)

#: Pack and card ids that may name a folder: no separators, no ``..``.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_warned: set[str] = set()
_warned_lock = threading.Lock()


def warn_once(message: str, *args: Any) -> None:
    """Log a warning the first time this exact message appears, then only at debug level.

    Packs are loaded again whenever a file changes, so a broken file would
    otherwise repeat the same warning on every rebuild.
    """
    text = message % args if args else message
    with _warned_lock:
        first = text not in _warned
        _warned.add(text)
    if first:
        logger.warning("%s", text)
    else:
        logger.debug("%s", text)


def default_packs_root() -> Path:
    """The packs that ship with RealizeOS (the repository's ``packs/`` folder)."""
    return Path(__file__).resolve().parent.parent.parent / "packs"


def custom_packs_root() -> Path | None:
    """The writable folder for the firm's own or modified packs (``REALIZE_PACKS_PATH``), or None."""
    raw = os.getenv(PACKS_PATH_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        warn_once("%s=%s is not a folder; only the shipped packs are used", PACKS_PATH_ENV, root)
        return None
    return root


def pack_roots(packs_root: Path | None = None) -> list[Path]:
    """Folders packs are loaded from, highest priority first.

    An explicit ``packs_root`` is used alone. Otherwise the custom folder
    (``REALIZE_PACKS_PATH``), when set, comes before the shipped packs.
    """
    if packs_root is not None:
        return [Path(packs_root)]
    roots: list[Path] = []
    custom = custom_packs_root()
    if custom is not None:
        roots.append(custom)
    shipped = default_packs_root()
    if custom is None or Path(shipped).resolve() != custom:
        roots.append(shipped)
    return roots


def is_safe_id(value: Any) -> bool:
    """True for a pack or card id that can't step outside a folder."""
    return isinstance(value, str) and bool(_SAFE_ID.match(value)) and ".." not in value


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _inside(path: Path, root: Path, warnings: list[str]) -> bool:
    """True when ``path`` really lives in the pack folder ``root``.

    A link that points outside the pack (``A-agents/x.md -> /etc/...``) is
    skipped with a warning, so pack content can only come from the pack.
    """
    try:
        inside = path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError) as exc:  # RuntimeError: a symlink loop
        warnings.append(f"{_rel(path, root)}: cannot resolve ({exc}); skipped")
        return False
    if not inside:
        warnings.append(f"{_rel(path, root)}: points outside the pack folder; skipped")
    return inside


def _read_yaml(path: Path, warnings: list[str], root: Path | None = None) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:  # ValueError covers undecodable bytes
        name = _rel(path, root) if root else path.name
        warnings.append(f"{name}: cannot read ({exc})")
        return None


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4 :].lstrip("\n")


def is_scalar(value: Any) -> bool:
    """A non-empty text, number or date (not a list, a mapping or a boolean).

    YAML reads an unquoted ``2026-10-13`` as a date, not as text, so a date is
    a scalar too; :func:`scalar_text` turns it back into ISO text.
    """
    if isinstance(value, date):  # datetime is a date too
        return True
    return isinstance(value, (str, int, float)) and not isinstance(value, bool) and bool(str(value).strip())


def scalar_text(value: Any) -> str:
    """A scalar as text: dates and timestamps as ISO text (``2026-10-13``), anything else with ``str``."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _date_text(value: Any) -> str:
    """A date field as ``YYYY-MM-DD`` text; a timestamp keeps only its date."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return scalar_text(value)


def _level(value: Any, name: str, warnings: list[str]) -> int | None:
    """A verification level from 0 to 4, or None when it is missing or unusable."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        warnings.append(f"{name}: verification level '{value}' is not a whole number; ignored")
        return None
    return max(0, min(4, value))


def _str_list(value: Any, name: str, warnings: list[str]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        warnings.append(f"pack.yaml: {name} must be a list; ignored")
        return []
    return [scalar_text(v) for v in value if is_scalar(v)]


def _mapping(value: Any, name: str, warnings: list[str]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(f"{name} must be a mapping; ignored")
        return {}
    return {str(k): v for k, v in value.items()}


def _clean_applies_to(value: Any, name: str, warnings: list[str]) -> dict[str, Any]:
    """``applies_to`` as a mapping whose ``kinds`` is a list of text."""
    applies_to = _mapping(value, f"{name}: applies_to", warnings)
    kinds = applies_to.get("kinds")
    if kinds is None:
        return applies_to
    if isinstance(kinds, str):
        kinds = [kinds]
    if not isinstance(kinds, list):
        warnings.append(f"{name}: applies_to.kinds must be a list; ignored")
        applies_to.pop("kinds")
        return applies_to
    applies_to["kinds"] = [scalar_text(k) for k in kinds if is_scalar(k)]
    return applies_to


def load_rule_card(path: Path, warnings: list[str], root: Path | None = None) -> RuleCard | None:
    """Parse one rule card. Cards without ``id``, ``statement``, ``source`` and ``as_of`` are skipped."""
    name = _rel(path, root) if root else path.name
    try:
        meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        warnings.append(f"{name}: cannot read rule card ({exc})")
        return None
    missing = [k for k in ("id", "statement", "source", "as_of") if not is_scalar(meta.get(k))]
    if missing:
        warnings.append(f"{name}: rule card skipped, missing {', '.join(missing)}")
        return None
    try:
        level = int(meta.get("verification", 1))
    except (TypeError, ValueError):
        level = 1
    verified_by = meta.get("verified_by")
    reviewed_at = meta.get("reviewed_at")
    return RuleCard(
        id=scalar_text(meta["id"]),
        statement=scalar_text(meta["statement"]),
        source=scalar_text(meta["source"]),
        as_of=_date_text(meta["as_of"]),
        body=body,
        applies_to=_clean_applies_to(meta.get("applies_to"), name, warnings),
        review_by=_date_text(meta["review_by"]) if is_scalar(meta.get("review_by")) else None,
        verification=max(0, min(4, level)),
        verified_by=scalar_text(verified_by) if is_scalar(verified_by) else None,
        reviewed_at=_date_text(reviewed_at) if is_scalar(reviewed_at) else None,
        path=path,
    )


def _load_glossary(pack: Pack, root: Path) -> None:
    w = pack.warnings
    for gfile in sorted((root / "glossary").glob("*.yaml")):
        name = _rel(gfile, root)
        if not _inside(gfile, root, w):
            continue
        entries = _read_yaml(gfile, w, root) or []
        if not isinstance(entries, list):
            w.append(f"{name}: glossary must be a list")
            continue
        for entry in entries:
            if not (isinstance(entry, dict) and is_scalar(entry.get("term")) and is_scalar(entry.get("family"))):
                w.append(f"{name}: glossary entry needs term and family")
                continue
            clean = {
                **entry,
                "term": scalar_text(entry["term"]),
                "family": scalar_text(entry["family"]),
                "language": gfile.stem,
            }
            kind = entry.get("kind")
            if kind is not None and not is_scalar(kind):
                w.append(f"{name}: glossary entry '{clean['term']}' has a kind that isn't text; ignored")
                clean.pop("kind")
            elif kind is not None:
                clean["kind"] = scalar_text(kind)
            pack.terms[clean["term"].casefold()] = clean


def _load_content(pack: Pack, root: Path) -> None:
    """Index the pack folders that share one layout across packs and firm overrides.

    Every file is checked for the shape it must have before any field is
    read: a file with the wrong shape becomes a warning, not an exception.
    """
    w = pack.warnings
    if (root / "glossary").is_dir():
        _load_glossary(pack, root)
    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for rfile in sorted(rules_dir.glob("*.md")):
            if not _inside(rfile, root, w):
                continue
            card = load_rule_card(rfile, w, root)
            if card:
                pack.rules[card.id] = card
    docs_dir = root / "documents"
    if docs_dir.is_dir():
        for dfile in sorted(p for p in docs_dir.iterdir() if p.is_file()):
            if _inside(dfile, root, w):
                pack.documents[dfile.stem] = dfile
    skills_dir = root / "R-routines" / "skills"
    if skills_dir.is_dir():
        for sfile in sorted(skills_dir.glob("*.yaml")):
            if not _inside(sfile, root, w):
                continue
            data = _read_yaml(sfile, w, root)
            if data is not None and not isinstance(data, dict):
                w.append(f"{_rel(sfile, root)}: a skill must be a mapping; skipped")
                continue
            data = data or {}
            skill_id = data.get("id") if is_scalar(data.get("id")) else None
            skill_id = skill_id or (data.get("name") if is_scalar(data.get("name")) else None) or sfile.stem
            pack.skills[scalar_text(skill_id)] = sfile
    _load_agents(pack, root)
    _load_skill_settings(pack, root)
    trust_file = root / "trust.yaml"
    if trust_file.is_file() and _inside(trust_file, root, w):
        data = _read_yaml(trust_file, w, root)
        if isinstance(data, dict):
            pack.trust.update({str(k): scalar_text(v) for k, v in data.items() if is_scalar(v)})
        elif data is not None:
            w.append("trust.yaml: must be a mapping of action to trust level; ignored")
    measures_file = root / "measures.yaml"
    if measures_file.is_file() and _inside(measures_file, root, w):
        data = _read_yaml(measures_file, w, root)
        if data is not None and not isinstance(data, list):
            w.append("measures.yaml: must be a list; ignored")
        for m in data if isinstance(data, list) else []:
            if isinstance(m, dict) and is_scalar(m.get("id")):
                pack.measures[scalar_text(m["id"])] = m
            else:
                w.append("measures.yaml: a measure needs an id; skipped")
    schemas_dir = root / "schemas"
    if schemas_dir.is_dir():
        for jfile in sorted(schemas_dir.glob("*.json")):
            if not _inside(jfile, root, w):
                continue
            try:
                schema = json.loads(jfile.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:  # JSONDecodeError and undecodable bytes are ValueErrors
                w.append(f"{_rel(jfile, root)}: invalid schema ({exc})")
                continue
            if isinstance(schema, dict):
                pack.schemas[jfile.stem] = schema
            else:
                w.append(f"{_rel(jfile, root)}: a schema must be a JSON object; skipped")


def agent_key(path: Path) -> str:
    """The agent key for an agent file, the same rule as venture ``A-agents/`` (stem, ``-`` → ``_``)."""
    return path.stem.replace("-", "_")


def _load_agents(pack: Pack, root: Path) -> None:
    """Index ``A-agents/*.md``; ``_``-prefixed files are notes, except the routing guide ``_README.md``."""
    w = pack.warnings
    agents_dir = root / "A-agents"
    if not agents_dir.is_dir():
        return
    for afile in sorted(agents_dir.glob("*.md")):
        if not afile.is_file() or not _inside(afile, root, w):
            continue
        if afile.name == "_README.md":
            pack.agents_readme = afile
        elif not afile.name.startswith("_"):
            pack.agents[agent_key(afile)] = afile


def _text_list(value: Any) -> list[str] | None:
    """A list of non-empty texts, or None when ``value`` isn't a list of scalars."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(is_scalar(v) for v in value):
        return None
    return [scalar_text(v) for v in value]


def _load_skill_settings(pack: Pack, root: Path) -> None:
    """Read ``skill-settings.yaml``: per skill id, extra ``triggers`` and ``variables``.

    Only the shape is checked here. Which layers may set ``variables`` is
    decided where the settings are applied (the firm layer only).
    """
    w = pack.warnings
    path = root / "skill-settings.yaml"
    if not path.is_file() or not _inside(path, root, w):
        return
    data = _read_yaml(path, w, root)
    if data is None:
        return
    if not isinstance(data, dict):
        w.append("skill-settings.yaml: must be a mapping of skill id to settings; ignored")
        return
    for skill_id, settings in data.items():
        if not isinstance(settings, dict):
            w.append(f"skill-settings.yaml: settings for '{skill_id}' must be a mapping; skipped")
            continue
        clean: dict[str, Any] = {}
        if "triggers" in settings:
            triggers = _text_list(settings["triggers"])
            if triggers is None:
                w.append(f"skill-settings.yaml: triggers for '{skill_id}' must be a list of text; ignored")
            else:
                clean["triggers"] = triggers
        if "variables" in settings:
            variables = settings["variables"]
            if isinstance(variables, dict) and all(is_scalar(v) for v in variables.values()):
                clean["variables"] = {str(k): scalar_text(v) for k, v in variables.items()}
            else:
                w.append(f"skill-settings.yaml: variables for '{skill_id}' must map names to text; ignored")
        unknown = sorted(set(settings) - {"triggers", "variables"})
        if unknown:
            w.append(f"skill-settings.yaml: '{skill_id}' can only set triggers and variables; ignored {unknown}")
        if clean:
            pack.skill_settings[str(skill_id)] = clean


def load_pack(root: Path, *, apply_state: bool = True) -> Pack | None:
    """Load a pack folder with a ``pack.yaml`` manifest. Returns None if unusable.

    Args:
        root: The pack's folder.
        apply_state: Lay the approval-recorded verification state over the
            pack (the default; see :mod:`realize_core.packs.state`). False
            gives the levels written in the pack's own files.
    """
    root = Path(root)
    manifest_path = root / "pack.yaml"
    warnings: list[str] = []
    manifest = _read_yaml(manifest_path, warnings, root) if manifest_path.is_file() else None
    if not isinstance(manifest, dict):
        reason = f" ({warnings[0]})" if warnings else ""
        warn_once("Pack at %s has no usable pack.yaml%s", root, reason)
        return None
    kind = manifest.get("kind")
    if kind not in PACK_KINDS or not is_scalar(manifest.get("id")) or not is_scalar(manifest.get("version")):
        warn_once("Pack at %s needs id, version and kind (one of %s) in pack.yaml", root, ", ".join(PACK_KINDS))
        return None
    verification = manifest.get("verification")
    verification = dict(verification) if isinstance(verification, dict) else {}
    pack = Pack(
        id=scalar_text(manifest["id"]),
        kind=kind,
        version=scalar_text(manifest["version"]),
        root=root,
        title=scalar_text(manifest["title"]) if is_scalar(manifest.get("title")) else "",
        languages=_str_list(manifest.get("languages"), "languages", warnings),
        defaults=_mapping(manifest.get("defaults"), "pack.yaml: defaults", warnings),
        verification_level=_level(verification.get("level"), "pack.yaml", warnings),
        verification=verification,
        limits=_str_list(manifest.get("limits"), "limits", warnings),
        requires=_mapping(manifest.get("requires"), "pack.yaml: requires", warnings),
        warnings=warnings,
    )
    _load_content(pack, root)
    if apply_state:
        from realize_core.packs import state

        state.apply_state(pack)
    for msg in pack.warnings:
        warn_once("Pack %s/%s at %s: %s", pack.kind, pack.ref, root, msg)
    return pack


def _load_isolated(pack_dir: Path) -> Pack | None:
    """:func:`load_pack`, but a pack that can't be loaded is skipped with a warning (audit N06)."""
    try:
        return load_pack(pack_dir)
    except LOAD_ERRORS as exc:
        warn_once(
            "Pack at %s skipped: it can't be loaded (%s: %s). Fix or remove that folder.",
            pack_dir,
            type(exc).__name__,
            exc,
        )
        return None


def load_firm_layer(venture_dir: Path) -> Pack:
    """Load the firm layer from ``F-foundations/overrides/`` (spec 010 §9.2).

    A broken override folder gives an empty firm layer with a warning; it
    never stops the venture's other layers.
    """
    root = Path(venture_dir) / "F-foundations" / "overrides"
    pack = Pack(id="firm", kind="firm", version="local", root=root)
    if not root.is_dir():
        return pack
    try:
        defaults_file = root / "defaults.yaml"
        if defaults_file.is_file():
            data = _read_yaml(defaults_file, pack.warnings, root)
            pack.defaults = _mapping(data, "defaults.yaml", pack.warnings)
        disable_file = root / "disable.yaml"
        if disable_file.is_file():
            data = _read_yaml(disable_file, pack.warnings, root) or []
            if isinstance(data, list):
                pack.disabled = {scalar_text(x) for x in data if is_scalar(x)}
            else:
                pack.warnings.append("disable.yaml: must be a list of ids; ignored")
        _load_content(pack, root)
    except LOAD_ERRORS as exc:
        warn_once("Firm overrides at %s skipped (%s: %s)", root, type(exc).__name__, exc)
        return Pack(id="firm", kind="firm", version="local", root=root, warnings=[str(exc)])
    for msg in pack.warnings:
        warn_once("Firm overrides at %s: %s", root, msg)
    return pack


def _kind_dirs(root: Path, kind: str) -> list[Path]:
    kind_dir = root / kind
    try:
        return sorted(p for p in kind_dir.iterdir() if p.is_dir()) if kind_dir.is_dir() else []
    except OSError as exc:
        warn_once("Cannot list packs in %s (%s)", kind_dir, exc)
        return []


def _is_custom_root(root: Path, packs_root: Path | None) -> bool:
    """True for the ``REALIZE_PACKS_PATH`` folder (never when an explicit ``packs_root`` is used)."""
    if packs_root is not None:
        return False
    custom = custom_packs_root()
    return custom is not None and Path(root) == custom


def _read_manifest(pack_dir: Path) -> tuple[dict[str, Any] | None, str]:
    """A folder's ``pack.yaml`` and, when it can't be used, why (reads the manifest only)."""
    manifest = pack_dir / "pack.yaml"
    if not manifest.is_file():
        return None, "no pack.yaml"
    problems: list[str] = []
    data = _read_yaml(manifest, problems, pack_dir)
    if problems:
        return None, problems[0]
    if not isinstance(data, dict):
        return None, "pack.yaml is not a mapping"
    if data.get("kind") not in PACK_KINDS or not is_scalar(data.get("id")) or not is_scalar(data.get("version")):
        return None, f"pack.yaml needs id, version and kind (one of {', '.join(PACK_KINDS)})"
    return data, ""


def _warn_broken_custom(pack_dir: Path, kind: str, pack_id: str, reason: str) -> None:
    """Say that a broken custom pack switched its id off instead of falling back to the shipped one.

    The id, folder and reason (which can quote the broken file) are shown escaped: this reaches a terminal.
    """
    from realize_core.utils.text import escape_nonprintable

    warn_once(
        "Custom pack %s/%s at %s can't be used (%s). It is switched off, and the shipped pack with the "
        "same id is NOT used in its place, so its stricter settings (such as trust.yaml) can't silently "
        "revert to the shipped ones. Fix or remove that folder.",
        kind,
        escape_nonprintable(pack_id),
        escape_nonprintable(pack_dir),
        escape_nonprintable(reason),
    )


def discover_packs(packs_root: Path | None = None) -> dict[tuple[str, str], Pack]:
    """All packs under ``<root>/<kind>/<id>/`` for every pack root, keyed by ``(kind, id)``.

    A pack in a higher-priority root replaces the same kind and id from a
    lower one. A pack that can't be loaded is skipped; the others still load.
    A pack in ``REALIZE_PACKS_PATH`` that can't be loaded also takes the
    shipped pack with the same kind and id out (fail closed, with a warning).
    """
    found: dict[tuple[str, str], Pack] = {}
    for root in reversed(pack_roots(packs_root)):
        custom = _is_custom_root(root, packs_root)
        for kind in PACK_KINDS:
            for pack_dir in _kind_dirs(root, kind):
                pack = _load_isolated(pack_dir)
                if pack is None:
                    if custom:
                        data, reason = _read_manifest(pack_dir)
                        pack_id = scalar_text(data["id"]) if data else pack_dir.name
                        pack_kind = data["kind"] if data else kind
                        _warn_broken_custom(pack_dir, pack_kind, pack_id, reason or "it can't be loaded")
                        found.pop((pack_kind, pack_id), None)
                    continue
                key = (pack.kind, pack.id)
                previous = found.get(key)
                if previous is not None and previous.root.parent.parent != pack.root.parent.parent:
                    logger.info("Pack %s/%s at %s replaces the one at %s", pack.kind, pack.id, pack.root, previous.root)
                found[key] = pack
    return found


def _manifest_names(pack_dir: Path, kind: str, pack_id: str) -> bool:
    """True when the folder's ``pack.yaml`` declares this kind and id (reads the manifest only)."""
    data, _reason = _read_manifest(pack_dir)
    return data is not None and data.get("kind") == kind and scalar_text(data.get("id")) == pack_id


def find_pack(kind: str, pack_id: str, packs_root: Path | None = None) -> Pack | None:
    """Load one installed pack by kind and id, or None when it isn't installed.

    Only that pack is loaded, so a broken pack nobody uses can't get in the
    way (audit N06). The folder named after the id is tried first; any other
    folder whose manifest declares the id is found too.

    A pack in ``REALIZE_PACKS_PATH`` that exists but is broken (its folder is
    named after the id and its ``pack.yaml`` can't be used, or it declares the
    id but can't be loaded) gives None with a warning naming its folder: the
    shipped pack with the same id is not used in its place (fail closed).
    """
    if kind not in PACK_KINDS or not isinstance(pack_id, str) or not pack_id:
        return None
    for root in pack_roots(packs_root):
        custom = _is_custom_root(root, packs_root)
        dirs = _kind_dirs(root, kind)
        named = [d for d in dirs if is_safe_id(pack_id) and d.name == pack_id]
        for pack_dir in [*named, *(d for d in dirs if d.name != pack_id)]:
            if not _manifest_names(pack_dir, kind, pack_id):
                if custom and pack_dir.name == pack_id:
                    data, reason = _read_manifest(pack_dir)
                    if data is None:
                        _warn_broken_custom(pack_dir, kind, pack_id, reason)
                        return None
                continue
            pack = _load_isolated(pack_dir)
            if pack is not None and pack.kind == kind and pack.id == pack_id:
                return pack
            if custom:
                _warn_broken_custom(pack_dir, kind, pack_id, "it can't be loaded")
                return None
    return None


def read_venture_packs(venture_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Read ``packs.yaml`` at the venture root: ``{"profession": [...], "market": [...]}``."""
    path = Path(venture_dir) / "packs.yaml"
    out: dict[str, list[dict[str, str]]] = {"profession": [], "market": []}
    if not path.is_file():
        return out
    warnings: list[str] = []
    data = _read_yaml(path, warnings) or {}
    if not isinstance(data, dict):
        warnings.append("must be a mapping with profession and market lists")
        data = {}
    for kind in PACK_KINDS:
        entries = data.get(kind) or []
        if isinstance(entries, (str, dict)):
            entries = [entries]
        if not isinstance(entries, list):
            warnings.append(f"{kind} must be a list of pack ids")
            continue
        for entry in entries:
            if is_scalar(entry):
                out[kind].append({"id": scalar_text(entry), "version": ""})
            elif isinstance(entry, dict) and is_scalar(entry.get("id")):
                version = entry.get("version")
                out[kind].append(
                    {"id": scalar_text(entry["id"]), "version": scalar_text(version) if is_scalar(version) else ""}
                )
            else:
                warnings.append(f"{kind}: entry {entry!r} needs an id")
    for msg in warnings:
        warn_once("%s: %s", path, msg)
    return out
