"""
Seed the Hebrew webinar demo venture (STORY-20).

Creates a venture from the ``real-estate-developer`` template, adds the demo
project documents (``templates/demos/tower-b-he``, clearly labelled demo data,
no real project figures) and configures the venture for Hebrew: ``locale: he``
(the dashboard turns right-to-left) and the template's Hebrew-aware routing.

Usage::

    python scripts/seed_webinar_demo.py            # in the project root
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATE = "real-estate-developer"
DEMO_KEY = "tower-b-demo"
DEMO_NAME = "מגדל B — פרויקט הדגמה"
DEMO_DESCRIPTION = "Webinar demo: a 24-unit development in Barreiro (demo data only)"
DEMO_LOCALE = "he"
#: The demo project is in Barreiro, so the Portugal market pack applies (spec 010).
DEMO_MARKET = "pt"

_ENGINE_ROOT = Path(__file__).resolve().parent.parent
DEMO_DOCS = _ENGINE_ROOT / "templates" / "demos" / "tower-b-he"
TEMPLATE_CONFIG = _ENGINE_ROOT / "templates" / f"{TEMPLATE}.yaml"


def _template_system_settings() -> dict:
    """Routing settings of the template's first system (routing, agent_routing)."""
    import yaml

    data = yaml.safe_load(TEMPLATE_CONFIG.read_text(encoding="utf-8")) or {}
    first = (data.get("systems") or [{}])[0]
    return {k: first[k] for k in ("routing", "agent_routing") if k in first}


def _configure_system(root: Path, key: str) -> None:
    """Set locale and the template's routing on the venture's entry in realize-os.yaml."""
    import yaml

    config_path = root / "realize-os.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for system in config.get("systems", []):
        if system.get("key") == key:
            system["locale"] = DEMO_LOCALE
            system.update(_template_system_settings())
            break
    else:
        raise KeyError(f"Venture '{key}' is not in {config_path}")
    config_path.write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _set_market_pack(venture_dir: Path, market: str) -> None:
    """Make ``market`` the venture's only market pack in packs.yaml (active with features.packs on).

    The template links the Israel pack by default; the demo project is
    elsewhere, so its market replaces the template's rather than joining it
    (a second market pack would put its rules and currency above this one).
    """
    import yaml

    path = venture_dir / "packs.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data = data or {}
    data["market"] = [market]
    data.setdefault("profession", [])
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def seed_webinar_demo(project_root: str | Path, key: str = DEMO_KEY, name: str = DEMO_NAME) -> dict:
    """Create the Hebrew demo venture with its documents.

    Args:
        project_root: Directory holding ``realize-os.yaml`` (created if missing).
        key: Venture key for the demo.
        name: Display name.

    Returns:
        ``{"key", "venture_dir", "documents"}``.

    Raises:
        FileExistsError: The venture already exists.
    """
    from realize_core.scaffold import scaffold_venture

    root = Path(project_root)
    scaffold_venture(root, key, name=name, description=DEMO_DESCRIPTION, template=TEMPLATE)
    venture_dir = root / "systems" / key

    documents = 0
    for source in DEMO_DOCS.rglob("*"):
        if source.is_file():
            target = venture_dir / source.relative_to(DEMO_DOCS)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            documents += 1

    _configure_system(root, key)
    _set_market_pack(venture_dir, DEMO_MARKET)
    logger.info("Seeded demo venture '%s' with %d documents", key, documents)
    return {"key": key, "venture_dir": str(venture_dir), "documents": documents}
