"""
Prepare and check a live rehearsal of the Hebrew webinar demo (STORY-20).

Two steps, both run from the project root after ``seed_webinar_demo``:

- :func:`set_demo_ids` writes the Google Sheet id and the tender document's
  Drive id into the demo venture's skills (their ``variables:`` block).
- :func:`preflight` checks, read-only, everything the live storyline needs:
  feature flags, an available LLM provider, Google access to every tab and the tender
  document, the Hebrew messages triggering the right skills, and a presenter
  account limited to the demo venture. Nothing is written to Google.

Usage::

    python scripts/rehearse_webinar_demo.py set-ids --sheet <id> --tender-doc <id>
    python scripts/rehearse_webinar_demo.py check
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from realize_core.demo_seed import DEMO_KEY

logger = logging.getLogger(__name__)

PLACEHOLDER = "REPLACE_WITH_"
REQUIRED_FEATURES = ("agent_tools", "enforce_gates", "cite_sources")

# The live storyline: message → the skill it must trigger (None: answered by an agent).
STORYLINE: tuple[tuple[str, str, str | None], ...] = (
    ("Tender", "תבנה רשימת דרישות מתיק המכרז", "tender_requirements_register"),
    ("Payment", "קיבלנו דרישת תשלום 4: 360,000 € על סיום השלד", "payment_milestone_check"),
    ("Investors", "תכין דוח רבעוני למשקיעים", "investor_report"),
    ("Live question", "כמה נשאר לנו נטו בתקציב?", None),
)

# Variables that take the project sheet id, and the one that takes the tender document id.
_SHEET_VARIABLES = ("register_sheet_id", "milestones_sheet_id", "payments_sheet_id", "budget_sheet_id")
_DOC_VARIABLES = ("tender_doc_id",)


@dataclass
class Check:
    """One preflight result."""

    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


def _skills_dir(root: Path, key: str) -> Path:
    return root / "systems" / key / "R-routines" / "skills"


def _skill_settings(root: Path, key: str) -> Path:
    """The firm's settings for pack skills (used when the venture links the developer pack)."""
    return root / "systems" / key / "F-foundations" / "overrides" / "skill-settings.yaml"


def _id_files(root: Path, key: str) -> list[Path]:
    """Where the demo's Google ids live.

    The venture's own skill files when it has them (created with packs off),
    else the firm's ``skill-settings.yaml`` for the developer pack's skills
    (created with ``features.packs`` on: the skills are linked, not copied).
    """
    own = sorted(_skills_dir(root, key).glob("*.yaml"))
    if own:
        return own
    settings = _skill_settings(root, key)
    return [settings] if settings.is_file() else []


def set_demo_ids(project_root: str | Path, sheet_id: str, tender_doc_id: str, key: str = DEMO_KEY) -> list[str]:
    """Write the Google ids into the demo venture's skill variables.

    Only the ``*_sheet_id`` and ``tender_doc_id`` lines are changed; comments
    and everything else in the files stay as they are.

    Args:
        project_root: Directory holding ``realize-os.yaml``.
        sheet_id: The project Google Sheet (tabs Requirements, Milestones, Payments, Summary).
        tender_doc_id: The tender document in Google Drive.
        key: Demo venture key.

    Returns:
        The skill files that changed.

    Raises:
        FileNotFoundError: The demo venture has no skills folder (seed it first).
        ValueError: An id is empty or contains characters that can't be a Google id.
    """
    for label, value in (("sheet id", sheet_id), ("tender document id", tender_doc_id)):
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", value or ""):
            raise ValueError(f"The {label} doesn't look like a Google id: {value!r}")

    root = Path(project_root)
    files = _id_files(root, key)
    if not files:
        raise FileNotFoundError(f"No skills in {_skills_dir(root, key)}; run scripts/seed_webinar_demo.py first")

    values = dict.fromkeys(_SHEET_VARIABLES, sheet_id) | dict.fromkeys(_DOC_VARIABLES, tender_doc_id)
    changed: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        updated = text
        for name, value in values.items():
            updated = re.sub(rf'^(\s*{name}:\s*)"[^"\n]*"', rf'\g<1>"{value}"', updated, flags=re.MULTILINE)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path.name)
    logger.info("Set demo ids in %d skill files", len(changed))
    return changed


def _check_config(root: Path, key: str) -> list[Check]:
    from realize_core.config import get_features, load_config

    config = load_config(root / "realize-os.yaml")
    systems = {s.get("key"): s for s in config.get("systems", [])}
    checks = [
        Check(
            "Demo venture exists",
            key in systems,
            f"'{key}' in realize-os.yaml" if key in systems else f"'{key}' not found",
            "python scripts/seed_webinar_demo.py",
        )
    ]
    if key in systems:
        locale = systems[key].get("locale")
        checks.append(Check("Hebrew locale", locale == "he", f"locale: {locale}", f"set locale: he on '{key}'"))
    features = get_features(config)
    off = [name for name in REQUIRED_FEATURES if not features.get(name)]
    checks.append(
        Check(
            "Feature flags",
            not off,
            "agent_tools, enforce_gates, cite_sources on" if not off else f"off: {', '.join(off)}",
            "set them to true under features: in realize-os.yaml",
        )
    )
    return checks


def _check_llm_provider() -> Check:
    """Any one available LLM provider is enough (an API key, a local Ollama server, LiteLLM)."""
    from realize_core.llm.registry import get_registry

    available = get_registry().list_available()
    return Check(
        "LLM provider",
        bool(available),
        f"available: {', '.join(available)}" if available else "no LLM provider available",
        "configure any one provider in .env (an API key, OLLAMA_BASE_URL or LITELLM_MODEL; see .env.example)",
    )


def _check_ids(root: Path, key: str) -> Check:
    files = _id_files(root, key)
    pending = [p.name for p in files if PLACEHOLDER in p.read_text(encoding="utf-8")]
    return Check(
        "Google ids set in skills",
        bool(files) and not pending,
        "all set" if not pending else f"placeholders left in {', '.join(sorted(pending))}",
        "python scripts/rehearse_webinar_demo.py set-ids --sheet <id> --tender-doc <id>",
    )


def _packs_on(root: Path) -> bool:
    from realize_core.config import get_features, load_config

    return bool(get_features(load_config(root / "realize-os.yaml")).get("packs"))


def _check_storyline(root: Path, key: str) -> list[Check]:
    from realize_core.skills.detector import detect_skill, reload_skills

    # With packs on, the venture's skills may come from the developer pack.
    reload_skills(kb_path=root, packs=_packs_on(root) or None)
    checks = []
    for case, message, expected in STORYLINE:
        skill = detect_skill(message, key)
        found = skill["name"] if skill else None
        checks.append(
            Check(
                f"Storyline: {case}",
                found == expected,
                f"triggers {found or 'no skill (agent answers)'}",
                f"expected {expected or 'no skill'}; check the skill triggers",
            )
        )
    return checks


def _check_presenter(key: str) -> Check:
    from realize_core.security.users import list_users

    presenters = [u for u in list_users() if u.role == "operator" and u.ventures == (key,)]
    return Check(
        "Presenter account",
        bool(presenters),
        f"{presenters[0].email} (operator, {key} only)" if presenters else "no operator limited to the demo venture",
        f"add a user with role: operator and ventures: [{key}] to users.yaml",
    )


def _skill_variables(root: Path, key: str) -> dict[str, str]:
    import yaml

    variables: dict[str, str] = {}
    own = list(_skills_dir(root, key).glob("*.yaml"))
    if not own:
        # Linked developer pack: the loaded skills carry the pack's defaults
        # with the firm's ids from skill-settings.yaml on top.
        from realize_core.skills.detector import get_skills_for_system

        for skill in get_skills_for_system(key):
            variables.update({k: str(v) for k, v in (skill.get("variables") or {}).items()})
        return variables
    for path in own:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        variables.update({k: str(v) for k, v in (data.get("variables") or {}).items()})
    return variables


async def _check_google(root: Path, key: str) -> list[Check]:
    from realize_core.tools.google_auth import has_stored_credentials
    from realize_core.tools.tool_registry import get_tool_registry

    if not has_stored_credentials():
        return [
            Check(
                "Google sign-in",
                False,
                "no stored Google token",
                "python scripts/google_signin.py (signed in as the demo Google account)",
            )
        ]
    registry = get_tool_registry()
    if registry.get_tool_for_action("sheets_read") is None:
        registry.auto_discover()

    variables = _skill_variables(root, key)
    reads = [
        (
            "Tab: Milestones",
            "sheets_read",
            {"spreadsheet_id": variables.get("milestones_sheet_id"), "range": variables.get("milestones_range")},
        ),
        (
            "Tab: Payments",
            "sheets_read",
            {"spreadsheet_id": variables.get("payments_sheet_id"), "range": variables.get("payments_range")},
        ),
        (
            "Tab: Requirements",
            "sheets_read",
            {"spreadsheet_id": variables.get("register_sheet_id"), "range": variables.get("register_range")},
        ),
        (
            "Tab: Summary",
            "sheets_read",
            {"spreadsheet_id": variables.get("budget_sheet_id"), "range": variables.get("budget_range")},
        ),
        ("Tender document", "drive_read_content", {"file_id": variables.get("tender_doc_id")}),
    ]
    checks = []
    for name, action, params in reads:
        if any(not v or PLACEHOLDER in v for v in params.values()):
            checks.append(Check(name, False, "id not set", "set the ids first (set-ids)"))
            continue
        result = await registry.execute(action, params)
        output = (result.output or "").strip()
        unreadable = "Cannot read content of this file type" in output
        ok = result.success and bool(output) and not unreadable
        checks.append(
            Check(
                name,
                ok,
                f"read {len(output)} characters"
                if ok
                else (
                    "unsupported file type; upload a Google Doc or .txt"
                    if unreadable
                    else (result.error or "empty")[:200]
                ),
                "check the tab name and that the demo Google account can open the file",
            )
        )
    return checks


async def preflight(project_root: str | Path, key: str = DEMO_KEY) -> list[Check]:
    """Check, read-only, everything the live demo needs.

    Args:
        project_root: Directory holding ``realize-os.yaml``.
        key: Demo venture key.

    Returns:
        One :class:`Check` per item, in the order a presenter fixes them.
    """
    root = Path(project_root)
    checks = _check_config(root, key)
    if not checks[0].ok:
        return checks
    checks.append(_check_llm_provider())
    checks.append(_check_ids(root, key))
    checks.extend(_check_storyline(root, key))
    checks.append(_check_presenter(key))
    checks.extend(await _check_google(root, key))
    return checks
