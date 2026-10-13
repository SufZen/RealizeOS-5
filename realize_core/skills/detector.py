"""
Skills System: Auto-triggered contextual workflows.

Skills can be defined as:
1. YAML v1 (trigger -> pipeline) — simple agent sequence
2. YAML v2 (trigger -> multi-step workflow with tools, conditions, human-in-the-loop)
3. SKILL.md  (YAML frontmatter + markdown instructions) — V5 format
4. Hardcoded fallback in _DEFAULT_SKILLS (reliability when YAML missing)

The system auto-detects schema version: if a skill has a 'steps' key, it's v2.
SKILL.md files are identified by the ``_format: 'skill_md'`` key.
Use reload_skills() to pick up new YAML / SKILL.md files without restart.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Loaded skills cache: {system_key: [skill_dict, ...]}
_loaded_skills: dict[str, list[dict]] = {}
_skills_loaded = False

# Whether load_skills adds each venture's pack skills (features.packs, spec 010).
# Off by default: skill loading is then exactly what it was before packs.
_pack_cascade = False

# The ventures' folders by configured key (``systems[].directory`` in realize-os.yaml),
# remembered so a later reload (e.g. after a library install) keeps the same mapping.
_venture_dirs: dict[str, Path] | None = None


def configure_pack_cascade(enabled: bool) -> None:
    """Turn the pack skill cascade on or off for later :func:`load_skills` calls.

    The app calls this with ``features.packs`` whenever its config is applied
    (:func:`realize_core.config_runtime.sync_skill_cascade`).
    """
    global _pack_cascade
    _pack_cascade = bool(enabled)


def pack_cascade_enabled() -> bool:
    """True when :func:`load_skills` adds the ventures' pack skills."""
    return _pack_cascade


# Generic fallback skills — ensures basic functionality even without YAML files
_DEFAULT_SKILLS: dict[str, list[dict]] = {
    "_default": [
        {
            "name": "content_pipeline",
            "triggers": [
                "write a post",
                "create content",
                "draft article",
                "blog post",
                "newsletter",
                "social media post",
                "write email",
                "write copy",
            ],
            "pipeline": ["writer", "reviewer"],
            "task_type": "content",
            "description": "Content creation with quality review",
        },
        {
            "name": "research_workflow",
            "triggers": [
                "research",
                "analyze",
                "compare",
                "investigate",
                "market analysis",
                "competitive analysis",
                "due diligence",
            ],
            "pipeline": ["analyst"],
            "task_type": "research",
            "description": "Research and analysis workflow",
        },
        {
            "name": "strategy_session",
            "triggers": [
                "strategic analysis",
                "business model",
                "positioning",
                "market opportunity",
                "growth strategy",
            ],
            "pipeline": ["analyst", "reviewer"],
            "task_type": "strategy",
            "description": "Strategic analysis with review",
        },
    ],
}


def _load_yaml_skills(skills_dir) -> dict[str, list[dict]]:
    """
    Load skills from YAML files organized by system directory.

    Expected structure:
        skills_dir/
            system_key_1/
                skill_a.yaml
                skill_b.yaml
            system_key_2/
                skill_c.yaml
            shared/
                skill_d.yaml
    """
    skills_by_system: dict[str, list[dict]] = {}
    skills_dir = Path(skills_dir)

    if not skills_dir.exists():
        logger.warning(f"Skills directory not found: {skills_dir}")
        return skills_by_system

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed. Using fallback skills only.")
        return skills_by_system

    for system_dir in skills_dir.iterdir():
        if not system_dir.is_dir():
            continue
        system_key = system_dir.name
        skills_by_system[system_key] = []

        for yaml_file in system_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    skill = yaml.safe_load(f)
                if skill and isinstance(skill, dict) and "name" in skill:
                    # Auto-detect v1 vs v2
                    if "steps" in skill:
                        skill["_version"] = 2
                    else:
                        skill["_version"] = 1
                    skill["_source"] = str(yaml_file)
                    skills_by_system[system_key].append(skill)
                    logger.debug(f"Loaded skill: {skill['name']} from {yaml_file}")
            except Exception as e:
                logger.warning(f"Failed to load skill from {yaml_file}: {e}")

    return skills_by_system


def _load_md_skills(skills_dir) -> dict[str, list[dict]]:
    """
    Load skills from SKILL.md files organised by system directory.

    Scans for ``*.md`` files with valid YAML frontmatter containing
    a ``name`` field.  Each parsed definition is converted to a
    skill dict via ``to_skill_dict()``.
    """
    skills_by_system: dict[str, list[dict]] = {}
    skills_dir = Path(skills_dir)

    if not skills_dir.exists():
        return skills_by_system

    try:
        from realize_core.skills.md_loader import scan_skill_md_files
    except ImportError:
        logger.debug("md_loader not available — SKILL.md loading skipped")
        return skills_by_system

    for system_dir in skills_dir.iterdir():
        if not system_dir.is_dir():
            continue
        system_key = system_dir.name
        definitions = scan_skill_md_files(system_dir, recursive=True)
        if definitions:
            skills_by_system.setdefault(system_key, []).extend(defn.to_skill_dict() for defn in definitions)

    return skills_by_system


def _skill_dirs(kb_path: Path) -> list[tuple[str, Path]]:
    """``(venture key, its R-routines/skills folder)`` for every venture.

    Uses the configured key-to-folder mapping when one was given
    (:func:`load_skills` ``ventures``), so a venture ``acme`` in
    ``systems/acme-office`` finds its skills; otherwise each folder under
    ``systems/`` is keyed by its name, as before.

    A venture keyed like a shared or global owner (``shared``) is left out
    with a warning: its skills would otherwise be handed to every venture.
    """
    if _venture_dirs is not None:
        pairs = [(key, Path(folder) / "R-routines" / "skills") for key, folder in sorted(_venture_dirs.items())]
    else:
        pairs = [(d.parent.parent.name, d) for d in sorted(kb_path.glob("systems/*/R-routines/skills"))]
    for key in sorted({key for key, _folder in pairs if key in GLOBAL_SKILL_OWNERS}):
        logger.warning("Skills of venture '%s' not loaded: that key is reserved for shared skills", key)
    return [(key, folder) for key, folder in pairs if key not in GLOBAL_SKILL_OWNERS]


def load_skills(skills_dir=None, kb_path=None, packs: bool | None = None, ventures: dict | None = None):
    """
    Load all skills from YAML files + defaults.

    Args:
        skills_dir: Path to skills directory (str or Path). If None, auto-detect from config.
        kb_path: Knowledge base path (str or Path) for finding system-specific skills in R-routines/.
        packs: Also add each venture's pack skills (spec 010): a venture's own
            skill wins over a pack skill with the same id or name. None uses
            the setting from :func:`configure_pack_cascade` (off by default).
        ventures: The ventures' folders by configured key. Remembered for later
            reloads; None keeps the last mapping (or keys folders by name).
    """
    global _loaded_skills, _skills_loaded, _venture_dirs

    if ventures is not None:
        _venture_dirs = {str(k): Path(v) for k, v in ventures.items()}

    # Load from dedicated skills directory
    if skills_dir:
        yaml_skills = _load_yaml_skills(Path(skills_dir))
        _loaded_skills.update(yaml_skills)

        # V5: also scan for SKILL.md files in the same directory
        md_skills = _load_md_skills(Path(skills_dir))
        for sys_key, md_list in md_skills.items():
            _loaded_skills.setdefault(sys_key, []).extend(md_list)

    # Also load from each system's R-routines/skills/ directory
    if kb_path:
        kb_path = Path(kb_path)
        for system_key, system_dir in _skill_dirs(kb_path):
            if system_dir.is_dir():
                try:
                    import yaml

                    for yaml_file in system_dir.glob("*.yaml"):
                        try:
                            with open(yaml_file, encoding="utf-8") as f:
                                skill = yaml.safe_load(f)
                            if skill and isinstance(skill, dict) and "name" in skill:
                                skill["_version"] = 2 if "steps" in skill else 1
                                skill["_source"] = str(yaml_file)
                                _loaded_skills.setdefault(system_key, []).append(skill)
                        except Exception as e:
                            logger.warning(f"Failed to load skill {yaml_file}: {e}")
                except ImportError:
                    pass

                # V5: also scan for SKILL.md files in R-routines
                try:
                    from realize_core.skills.md_loader import scan_skill_md_files

                    md_defs = scan_skill_md_files(system_dir, recursive=True)
                    for defn in md_defs:
                        _loaded_skills.setdefault(system_key, []).append(defn.to_skill_dict())
                except ImportError:
                    pass

    if kb_path and (_pack_cascade if packs is None else packs):
        from realize_core.packs.skills import load_venture_pack_skills

        added = load_venture_pack_skills(
            Path(kb_path), _loaded_skills, ventures=_venture_dirs, reserved=GLOBAL_SKILL_OWNERS
        )
        logger.info("Loaded %d skill(s) from profession and market packs", added)

    _skills_loaded = True
    total = sum(len(v) for v in _loaded_skills.values())
    logger.info(f"Loaded {total} skills across {len(_loaded_skills)} systems")


def reload_skills(skills_dir=None, kb_path=None, packs: bool | None = None, ventures: dict | None = None):
    """Hot-reload skills from YAML files (and, with ``packs``, from the ventures' packs).

    Skills created, changed or deleted through the API (``/api/workflows``)
    are applied again on top, so a settings reload doesn't undo them; they
    last until the server restarts (:func:`_reapply_runtime_changes`).
    """
    global _loaded_skills, _skills_loaded
    _loaded_skills = {}
    _skills_loaded = False
    load_skills(skills_dir=skills_dir, kb_path=kb_path, packs=packs, ventures=ventures)
    _reapply_runtime_changes()


def detect_skill(message: str, system_key: str = None) -> dict | None:
    """
    Detect if a message triggers a skill (keyword matching only).

    For semantic fallback, use ``detect_skill_v2`` which is async.

    Args:
        message: User's message text.
        system_key: Which system to check skills for.

    Returns:
        Matching skill dict, or None if no skill matches.
    """
    msg_lower = message.lower()

    # Get candidate skills: system-specific + shared + defaults
    candidates = _get_candidates(system_key)

    # Score each skill
    best_skill = None
    best_score = 0

    for skill in candidates:
        score = _score_skill_keywords(skill, msg_lower)
        if score > best_score:
            best_score = score
            best_skill = skill

    if best_skill and best_score > 0:
        logger.info(f"Detected skill: {best_skill['name']} (score={best_score}) for system={system_key}")
        return best_skill

    return None


async def detect_skill_v2(
    message: str,
    system_key: str = None,
    semantic_fallback: bool = True,
    semantic_threshold: float = 0.6,
) -> dict | None:
    """
    V5 skill detection with optional semantic fallback.

    First attempts keyword matching.  If no match is found and
    ``semantic_fallback`` is ``True``, asks an LLM to semantically
    match the message against all available skills.

    Args:
        message: User's message text.
        system_key: Which system to check skills for.
        semantic_fallback: Enable LLM-based semantic matching.
        semantic_threshold: Minimum score for semantic matches.

    Returns:
        Matching skill dict, or ``None``.
    """
    # Try keyword matching first
    keyword_result = detect_skill(message, system_key)
    if keyword_result is not None:
        return keyword_result

    if not semantic_fallback:
        return None

    # Semantic fallback
    try:
        from realize_core.skills.semantic import semantic_match
    except ImportError:
        logger.debug("semantic module not available — skipping fallback")
        return None

    candidates = _get_candidates(system_key)
    if not candidates:
        return None

    skill_summaries = [
        {
            "key": s.get("name", ""),
            "description": s.get("description", s.get("task_type", "")),
        }
        for s in candidates
        if s.get("name")
    ]

    result = await semantic_match(
        message=message,
        skill_summaries=skill_summaries,
        threshold=semantic_threshold,
    )

    if result and result.is_match:
        # Find the skill dict that matches the key
        for s in candidates:
            if s.get("name") == result.skill_key:
                logger.info(f"Semantic match: {result.skill_key} (score={result.score:.2f}) for system={system_key}")
                return s

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_candidates(system_key: str | None) -> list[dict]:
    """Gather candidate skills for a given system key."""
    candidates = []
    if system_key and system_key in _loaded_skills:
        candidates.extend(_loaded_skills[system_key])
    if "shared" in _loaded_skills:
        candidates.extend(_loaded_skills["shared"])

    # Fall back to defaults if no YAML/MD skills loaded for this system
    if not candidates:
        candidates = _DEFAULT_SKILLS.get(system_key, _DEFAULT_SKILLS.get("_default", []))
    return candidates


def get_skills_for_system(system_key: str) -> list[dict]:
    """Skills available to one venture: its own, the shared ones, else the defaults.

    The same candidates skill detection uses. The venture skills endpoint and
    the MCP ``list_skills`` tool import this (QA 5.14 K-1: it was missing, so
    both reported "Skills unavailable").
    """
    return list(_get_candidates(system_key))


def get_all_skills() -> list[dict]:
    """Return all loaded skills across all systems as a flat list.

    Each entry's ``system_key`` is the system the skill was loaded under (its
    owner), which is also what skill detection uses; a ``system_key`` written
    inside the skill's own definition never overrides it.
    """
    all_skills = []
    for sys_key, skills in _loaded_skills.items():
        for skill in skills:
            all_skills.append({**skill, "system_key": sys_key})
    # Include defaults if nothing loaded
    if not all_skills:
        for sys_key, skills in _DEFAULT_SKILLS.items():
            for skill in skills:
                all_skills.append({**skill, "system_key": sys_key})
    return all_skills


#: Skill owners that are not ventures: the firm's shared skills (every venture
#: gets them, as skill detection does), built-ins and skills registered without one.
GLOBAL_SKILL_OWNERS = frozenset({"", "_default", "_runtime", "shared"})

#: Order in which shared and global owners are searched after a venture's own skills.
_GLOBAL_LOOKUP_ORDER = ("shared", "", "_runtime", "_default")


def _named(skills: list[dict], name: str) -> dict | None:
    return next((skill for skill in skills if skill.get("name") == name), None)


def find_shared_skill(name: str) -> tuple[str, dict] | None:
    """A shared or global skill by name: shared, registered without a venture, built-in."""
    for owner in _GLOBAL_LOOKUP_ORDER:
        skill = _named(_loaded_skills.get(owner, []), name)
        if skill is not None:
            return owner, skill
    for owner, skills in _DEFAULT_SKILLS.items():
        skill = _named(skills, name)
        if skill is not None:
            return owner, skill
    return None


def ventures_with_skill(name: str) -> list[str]:
    """The ventures (not shared or global owners) that have their own skill called ``name``, sorted."""
    return sorted(
        owner
        for owner, skills in _loaded_skills.items()
        if owner not in GLOBAL_SKILL_OWNERS and _named(skills, name) is not None
    )


def find_skill(name: str, system_key: str | None = None) -> tuple[str, dict] | None:
    """Look up a skill by name with its owner (same skill as :func:`get_skill_by_name`).

    The owner is the system key the skill was loaded under. Skills loaded from
    a venture's YAML don't carry it in their dict, so access checks must use
    this owner, never ``skill.get("system_key")``.

    Every venture has its own copy of a pack skill (with its own
    ``variables``, such as its sheet ids), and two ventures may each have a
    skill with the same name, so a run must say which venture it is for:

    - with ``system_key``: that venture's own skill, else a shared or global
      one (:data:`GLOBAL_SKILL_OWNERS`); never another venture's;
    - without one: only a shared or global skill, never a venture's. A caller
      that wants a venture's skill names the venture
      (:func:`ventures_with_skill` says which ventures have one).
    """
    if system_key:
        skill = _named(_loaded_skills.get(system_key, []), name)
        if skill is not None:
            return system_key, skill
    return find_shared_skill(name)


def get_skill_by_name(name: str, system_key: str | None = None) -> dict | None:
    """Look up a skill by name for a venture (see :func:`find_skill`)."""
    found = find_skill(name, system_key)
    return found[1] if found else None


# ---------------------------------------------------------------------------
# Skills created or changed through the API (kept across reloads until restart)
# ---------------------------------------------------------------------------

#: Skills registered at runtime (``POST /api/workflows``), by ``(owner, name)``.
_runtime_skills: dict[tuple[str, str], dict] = {}
#: API changes (``PUT /api/workflows/{name}``) to skills loaded from files, by ``(owner, name)``.
_runtime_edits: dict[tuple[str, str], dict] = {}
#: File skills deleted through the API (``DELETE /api/workflows/{name}``), by ``(owner, name)``.
_runtime_removed: set[tuple[str, str]] = set()


def _reapply_runtime_changes() -> None:
    """Apply the API's changes again after a reload: they were the user's last word, until restart.

    A file skill deleted through the API stays deleted, changes are laid over
    the reloaded file skill, and a skill created through the API replaces a
    file skill with the same name in the same venture (it was the user's
    explicit, later action). All of it lasts until the server restarts.
    """
    for owner, name in _runtime_removed:
        skills = _loaded_skills.get(owner)
        if skills:
            skills[:] = [s for s in skills if s.get("name") != name]
    for (owner, name), updates in _runtime_edits.items():
        skill = _named(_loaded_skills.get(owner, []), name)
        if skill is not None:
            skill.update(updates)
    for (owner, name), skill in _runtime_skills.items():
        skills = _loaded_skills.setdefault(owner, [])
        skills[:] = [s for s in skills if s.get("name") != name]
        skills.append(skill)


def _owned(name: str, system_key: str | None) -> tuple[str, dict] | None:
    """The skill ``name`` of exactly ``system_key`` (any loaded owner), or a shared or global one."""
    if system_key is not None:
        skill = _named(_loaded_skills.get(system_key, []), name)
        return (system_key, skill) if skill is not None else None
    found = find_shared_skill(name)
    return found if found is not None and found[0] in _loaded_skills else None


def register_skill(skill_data: dict) -> None:
    """Register a new skill at runtime (in memory only).

    It is kept across :func:`reload_skills` (a settings reload) until the
    server restarts.
    """
    system_key = skill_data.get("system_key", "_runtime")
    key = (system_key, str(skill_data.get("name") or ""))
    _runtime_skills[key] = skill_data
    _runtime_removed.discard(key)
    _runtime_edits.pop(key, None)
    _loaded_skills.setdefault(system_key, []).append(skill_data)
    logger.info("Registered runtime skill '%s' in system '%s'", skill_data.get("name"), system_key)


def update_skill(name: str, updates: dict, system_key: str | None = None) -> bool:
    """Update a skill's fields. Returns True if found and updated.

    ``system_key`` is the owner whose skill to change; without it only a
    shared or global skill is changed, never a venture's. The change is kept
    across :func:`reload_skills` until the server restarts.
    """
    found = _owned(name, system_key)
    if found is None:
        return False
    owner, skill = found
    skill.update(updates)
    if (owner, name) not in _runtime_skills:
        _runtime_edits.setdefault((owner, name), {}).update(updates)
    logger.info("Updated skill '%s' in system '%s': %s", name, owner, list(updates.keys()))
    return True


def unregister_skill(name: str, system_key: str | None = None) -> bool:
    """Remove a skill. Returns True if found and removed.

    ``system_key`` is the owner whose skill to remove; without it only a
    shared or global skill is removed, never a venture's. A file skill removed
    this way stays removed across :func:`reload_skills` until the server restarts.
    """
    found = _owned(name, system_key)
    if found is None:
        return False
    owner, skill = found
    skills = _loaded_skills[owner]
    skills[:] = [s for s in skills if s is not skill]
    _runtime_edits.pop((owner, name), None)
    if _runtime_skills.pop((owner, name), None) is None:
        _runtime_removed.add((owner, name))
    logger.info("Unregistered skill '%s' from system '%s'", name, owner)
    return True


def _score_skill_keywords(skill: dict, msg_lower: str) -> int:
    """Score a skill against a lowered message using keyword matching."""
    score = 0
    triggers = skill.get("triggers", [])
    negative_triggers = skill.get("negative_triggers", [])

    # Check negative triggers first
    if any(neg.lower() in msg_lower for neg in negative_triggers):
        score -= 15

    # Score positive triggers
    for trigger in triggers:
        trigger_lower = trigger.lower()
        if trigger_lower in msg_lower:
            score += 10  # Substring match
        else:
            # Check if all words in the trigger appear in the message
            words = trigger_lower.split()
            if len(words) > 1 and all(w in msg_lower for w in words):
                score += 5

    return score
