"""
Skills System: Auto-triggered contextual workflows.

Skills can be defined as:
1. YAML v1 (trigger -> pipeline) — simple agent sequence
2. YAML v2 (trigger -> multi-step workflow with tools, conditions, human-in-the-loop)
3. Hardcoded fallback in _DEFAULT_SKILLS (reliability when YAML missing)

The system auto-detects schema version: if a skill has a 'steps' key, it's v2.
Use reload_skills() to pick up new YAML files without restart.
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
    Detect if a message triggers a skill.

    Args:
        message: User's message text.
        system_key: Which system to check skills for.

    Returns:
        Matching skill dict, or None if no skill matches.
    """
    msg_lower = message.lower()

    # Get candidate skills: system-specific + shared + defaults
    candidates = []
    if system_key and system_key in _loaded_skills:
        candidates.extend(_loaded_skills[system_key])
    if "shared" in _loaded_skills:
        candidates.extend(_loaded_skills["shared"])

    # Fall back to defaults if no YAML skills loaded for this system
    if not candidates:
        candidates = _DEFAULT_SKILLS.get(system_key, _DEFAULT_SKILLS.get("_default", []))

    # Score each skill
    best_skill = None
    best_score = 0

    for skill in candidates:
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

        if score > best_score:
            best_score = score
            best_skill = skill

    if best_skill and best_score > 0:
        logger.info(f"Detected skill: {best_skill['name']} (score={best_score}) for system={system_key}")
        return best_skill

    return None
