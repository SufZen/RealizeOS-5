"""
Project initialization: shared logic for creating a RealizeOS project.

Used by both `cli.py init --setup` and `cli.py setup` (the wizard).
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_GITIGNORE_CONTENT = """\
# Secrets
.env
setup.yaml
.realize-setup.json

# Data
data/
*.db

# Python
__pycache__/
*.pyc
.venv/
venv/

# OS
.DS_Store
Thumbs.db

# Credentials
.credentials/
"""

# Where the engine code lives (for finding templates, realize_lite, etc.)
_ENGINE_ROOT = Path(__file__).parent.parent


def get_available_templates() -> list[dict]:
    """List available templates with names and descriptions."""
    templates_dir = _ENGINE_ROOT / "templates"
    if not templates_dir.exists():
        return []

    templates = []
    for f in sorted(templates_dir.glob("*.yaml")):
        if f.stem.startswith("_"):
            continue
        # Read first comment line as description
        desc = ""
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("#") and not line.startswith("# ---"):
                    desc = line.lstrip("# ").strip()
                    break
        except Exception:
            pass
        templates.append({"name": f.stem, "description": desc or f.stem.title()})
    return templates


def initialize_project(config: dict, target_dir: Path) -> dict:
    """
    Initialize a RealizeOS project from a configuration dict.

    Args:
        config: Dict with keys: anthropic_api_key, google_ai_api_key,
                template, business_name, business_description, etc.
        target_dir: Where to create the project.

    Returns:
        Dict with status: {"env_created", "config_created", "files_copied", "errors"}
    """
    result = {"env_created": False, "config_created": False, "files_copied": 0, "errors": []}

    anthropic_key = config.get("anthropic_api_key", "")
    google_key = config.get("google_ai_api_key", "")
    template_name = config.get("template", "consulting")
    business_name = config.get("business_name", "My Business")
    business_desc = config.get("business_description", "")
    realize_port = config.get("realize_port", "8080")
    realize_api_key = config.get("realize_api_key", "")
    openai_key = config.get("openai_api_key", "")
    telegram_token = config.get("telegram_bot_token", "")
    brave_key = config.get("brave_api_key", "")

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate .env
    env_dest = target_dir / ".env"
    if not env_dest.exists():
        env_lines = [
            "# RealizeOS Environment — auto-generated",
            f"ANTHROPIC_API_KEY={anthropic_key}",
            f"GOOGLE_AI_API_KEY={google_key}",
            "",
            "REALIZE_HOST=127.0.0.1",
            f"REALIZE_PORT={realize_port}",
            f"REALIZE_API_KEY={realize_api_key}",
            "CORS_ORIGINS=*",
            "",
            "KB_PATH=.",
            "DATA_PATH=./data",
            "REALIZE_CONFIG=realize-os.yaml",
            "",
            "BROWSER_ENABLED=false",
            "MCP_ENABLED=false",
            "",
            "RATE_LIMIT_PER_MINUTE=30",
            "COST_LIMIT_PER_HOUR_USD=5.00",
        ]
        if openai_key:
            env_lines.append(f"OPENAI_API_KEY={openai_key}")
        if telegram_token:
            env_lines.append(f"TELEGRAM_BOT_TOKEN={telegram_token}")
        if brave_key:
            env_lines.append(f"BRAVE_API_KEY={brave_key}")

        # Add V5 feature flags
        env_lines.extend([
            "",
            "# RealizeOS 5 Features",
            "REALIZE_FEATURES_ACTIVITY_LOG=true",
            "REALIZE_FEATURES_AGENT_LIFECYCLE=true",
        ])

        env_dest.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        result["env_created"] = True

    # 2. Copy template -> realize-os.yaml
    templates_dir = _ENGINE_ROOT / "templates"
    template_file = templates_dir / f"{template_name}.yaml"
    if not template_file.exists():
        result["errors"].append(f"Template '{template_name}' not found")
        return result

    config_dest = target_dir / "realize-os.yaml"
    if not config_dest.exists():
        content = template_file.read_text(encoding="utf-8")
        content = content.replace("My Consulting Practice", business_name)
        content = content.replace("Consulting Practice", business_name)
        config_dest.write_text(content, encoding="utf-8")
        result["config_created"] = True

    # 3. Copy FABRIC structure from realize_lite
    lite_src = _ENGINE_ROOT / "realize_lite"
    if lite_src.exists():
        for item in lite_src.rglob("*"):
            if item.is_file() and ".obsidian" not in str(item):
                relative = item.relative_to(lite_src)
                dest = target_dir / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(item, dest)
                    result["files_copied"] += 1

    # 4. Pre-populate venture-identity.md
    for brand_file in target_dir.rglob("venture-identity.md"):
        try:
            content = brand_file.read_text(encoding="utf-8")
            changed = False
            content_lower = content.lower()
            if "my business" in content_lower or "your business" in content_lower:
                content = content.replace("My Business", business_name)
                content = content.replace("my business", business_name)
                content = content.replace("Your Business", business_name)
                content = content.replace("your business", business_name)
                changed = True
            if business_desc and "# Venture Identity" in content:
                content = content.replace(
                    "# Venture Identity",
                    f"# Venture Identity\n\n> {business_desc}",
                )
                changed = True
            if changed:
                brand_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    # 5. Create .gitignore
    gitignore_dest = target_dir / ".gitignore"
    if not gitignore_dest.exists():
        gitignore_dest.write_text(_GITIGNORE_CONTENT, encoding="utf-8")

    # 6. Copy .env.example
    env_example_src = _ENGINE_ROOT / ".env.example"
    env_example_dest = target_dir / ".env.example"
    if env_example_src.exists() and not env_example_dest.exists():
        shutil.copy2(env_example_src, env_example_dest)

    return result
