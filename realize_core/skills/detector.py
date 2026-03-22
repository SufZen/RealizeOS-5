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


# Generic fallback skills — ensures basic functionality even without YAML files
_DEFAULT_SKILLS: dict[str, list[dict]] = {
    "_default": [
        {
            "name": "content_pipeline",
            "triggers": [
                "write a post", "create content", "draft article",
                "blog post", "newsletter", "social media post",
                "write email", "write copy",
            ],
            "pipeline": ["writer", "reviewer"],
            "task_type": "content",
            "description": "Content creation with quality review",
        },
        {
            "name": "research_workflow",
            "triggers": [
                "research", "analyze", "compare", "investigate",
                "market analysis", "competitive analysis", "due diligence",
            ],
            "pipeline": ["analyst"],
            "task_type": "research",
            "description": "Research and analysis workflow",
        },
        {
            "name": "strategy_session",
            "triggers": [
                "strategic analysis", "business model", "positioning",
                "market opportunity", "growth strategy",
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
                with open(yaml_file) as f:
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
            skills_by_system.setdefault(system_key, []).extend(
                defn.to_skill_dict() for defn in definitions
            )

    return skills_by_system


def load_skills(skills_dir=None, kb_path=None):
    """
    Load all skills from YAML files + defaults.

    Args:
        skills_dir: Path to skills directory (str or Path). If None, auto-detect from config.
        kb_path: Knowledge base path (str or Path) for finding system-specific skills in R-routines/.
    """
    global _loaded_skills, _skills_loaded

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
        for system_dir in kb_path.glob("systems/*/R-routines/skills"):
            if system_dir.exists():
                system_key = system_dir.parent.parent.name
                try:
                    import yaml
                    for yaml_file in system_dir.glob("*.yaml"):
                        try:
                            with open(yaml_file) as f:
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
                        _loaded_skills.setdefault(system_key, []).append(
                            defn.to_skill_dict()
                        )
                except ImportError:
                    pass

    _skills_loaded = True
    total = sum(len(v) for v in _loaded_skills.values())
    logger.info(f"Loaded {total} skills across {len(_loaded_skills)} systems")


def reload_skills(skills_dir=None, kb_path=None):
    """Hot-reload skills from YAML files."""
    global _loaded_skills, _skills_loaded
    _loaded_skills = {}
    _skills_loaded = False
    load_skills(skills_dir=skills_dir, kb_path=kb_path)


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
                logger.info(
                    f"Semantic match: {result.skill_key} "
                    f"(score={result.score:.2f}) for system={system_key}"
                )
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
        candidates = _DEFAULT_SKILLS.get(
            system_key, _DEFAULT_SKILLS.get("_default", [])
        )
    return candidates


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
