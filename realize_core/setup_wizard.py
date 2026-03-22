"""
Interactive setup wizard for RealizeOS 5.

Uses only Python stdlib for Phase 1 (prerequisite checks + pip install).
Third-party imports happen only after Phase 1 succeeds.

Usage:
    python cli.py setup              # Interactive wizard
    python cli.py setup --skip-dashboard  # Skip Node/dashboard phase
"""
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# The engine root (where cli.py, requirements.txt, templates/ live)
ENGINE_ROOT = Path(__file__).parent.parent


@dataclass
class SetupState:
    """Tracks wizard progress for resume capability."""
    project_root: str = "."
    phases_done: list = field(default_factory=list)
    # Collected config
    anthropic_key: str = ""
    google_key: str = ""
    template: str = "consulting"
    business_name: str = "My Business"
    business_description: str = ""
    install_dashboard: bool = True

    def save(self, path: Path):
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return None


def _print(marker: str, msg: str):
    """Print a status line."""
    print(f"  [{marker}] {msg}")


def _ask(prompt: str, default: str = "") -> str:
    """Ask user for input with optional default."""
    if default:
        result = input(f"  {prompt} [{default}]: ").strip()
        return result or default
    return input(f"  {prompt}: ").strip()


def _ask_yn(prompt: str, default: bool = True) -> bool:
    """Ask a yes/no question."""
    suffix = "Y/n" if default else "y/N"
    result = input(f"  {prompt} [{suffix}]: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def _ask_secret(prompt: str) -> str:
    """Ask for a secret (hidden input)."""
    try:
        return getpass.getpass(f"  {prompt}: ").strip()
    except EOFError:
        return ""


# ─────────────────────────────────────────────────────────────
# Phase 1: Prerequisites (stdlib only)
# ─────────────────────────────────────────────────────────────

def phase_prerequisites() -> bool:
    """Check Python version and install pip dependencies."""
    print("\n[1/5] Checking prerequisites...")

    # Python version
    v = sys.version_info
    if v < (3, 11):
        _print("!!", f"Python 3.11+ required, found {v.major}.{v.minor}.{v.micro}")
        _print("!!", "Download from https://python.org")
        return False
    _print("OK", f"Python {v.major}.{v.minor}.{v.micro}")

    # pip install
    req_file = ENGINE_ROOT / "requirements.txt"
    if not req_file.exists():
        _print("!!", f"requirements.txt not found at {req_file}")
        return False

    _print("..", "Installing Python dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _print("!!", "pip install failed:")
        print(result.stderr[:500])
        _print("!!", f"Try manually: {sys.executable} -m pip install -r requirements.txt")
        return False
    _print("OK", "Python dependencies installed")

    # Verify key imports
    try:
        import fastapi  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as e:
        _print("!!", f"Import check failed: {e}")
        return False

    return True


# ─────────────────────────────────────────────────────────────
# Phase 2: Configuration (interactive)
# ─────────────────────────────────────────────────────────────

def phase_configuration(state: SetupState) -> bool:
    """Collect configuration from user interactively."""
    print("\n[2/5] Configuration")

    state.business_name = _ask("Business name", "My Business")
    state.business_description = _ask("Short description", "")

    # Template selection
    from realize_core.init import get_available_templates
    templates = get_available_templates()
    if templates:
        print("\n  Available templates:")
        for i, t in enumerate(templates, 1):
            print(f"    {i}. {t['name']:<14} - {t['description']}")
        choice = _ask(f"\n  Select template [1-{len(templates)}]", "1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(templates):
                state.template = templates[idx]["name"]
            else:
                state.template = "consulting"
        except ValueError:
            # Try matching by name
            state.template = choice if any(t["name"] == choice for t in templates) else "consulting"
    print(f"  Template: {state.template}")

    # API keys
    print()
    state.anthropic_key = _ask_secret("Anthropic API key (sk-ant-...)")
    if not state.anthropic_key:
        state.google_key = _ask_secret("Google AI API key (required if no Anthropic key)")
    else:
        state.google_key = _ask_secret("Google AI API key (optional, press Enter to skip)")

    if not state.anthropic_key and not state.google_key:
        _print("!!", "At least one API key is required for LLM functionality")
        if not _ask_yn("Continue without API keys? (server will start but chat won't work)", False):
            return False

    # Dashboard
    state.install_dashboard = _ask_yn("\n  Install and build the dashboard?", True)

    _print("OK", "Configuration collected")
    return True


# ─────────────────────────────────────────────────────────────
# Phase 3: Initialization
# ─────────────────────────────────────────────────────────────

def phase_initialization(state: SetupState) -> bool:
    """Initialize the project using shared init logic."""
    print("\n[3/5] Initializing project...")

    from realize_core.init import initialize_project

    config = {
        "anthropic_api_key": state.anthropic_key,
        "google_ai_api_key": state.google_key,
        "template": state.template,
        "business_name": state.business_name,
        "business_description": state.business_description,
    }

    target = Path(state.project_root)
    result = initialize_project(config, target)

    if result.get("errors"):
        for err in result["errors"]:
            _print("!!", err)
        return False

    if result["env_created"]:
        _print("OK", "Created .env with API keys")
    if result["config_created"]:
        _print("OK", f"Created realize-os.yaml from '{state.template}' template")
    if result["files_copied"]:
        _print("OK", f"Created FABRIC structure ({result['files_copied']} files)")

    return True


# ─────────────────────────────────────────────────────────────
# Phase 4: Verification
# ─────────────────────────────────────────────────────────────

def phase_verification(state: SetupState) -> bool:
    """Verify the installation works."""
    print("\n[4/5] Verifying installation...")

    target = Path(state.project_root)

    # Check .env exists
    env_path = target / ".env"
    if not env_path.exists():
        _print("!!", ".env file not found")
        return False

    # Check config loads
    try:
        os.chdir(str(target))
        from realize_core.config import load_config
        config = load_config()
        systems = config.get("systems", [])
        _print("OK", f"Config loads ({len(systems)} system(s) configured)")
    except Exception as e:
        _print("!!", f"Config error: {e}")
        return False

    # Check server module imports
    try:
        from realize_api.main import app  # noqa: F401
        _print("OK", "Server module imports successfully")
    except Exception as e:
        _print("!!", f"Server import error: {e}")
        # Non-fatal — server can still work if deps are installed later

    return True


# ─────────────────────────────────────────────────────────────
# Phase 5: Dashboard (optional)
# ─────────────────────────────────────────────────────────────

def phase_dashboard(state: SetupState) -> bool:
    """Optionally install and build the React dashboard."""
    print("\n[5/5] Dashboard setup")

    if not state.install_dashboard:
        _print("--", "Skipped (user choice)")
        return True

    dashboard_dir = ENGINE_ROOT / "dashboard"
    if not dashboard_dir.exists():
        _print("!!", f"Dashboard directory not found at {dashboard_dir}")
        return False

    # Check Node.js
    node = shutil.which("node")
    if not node:
        _print("!!", "Node.js not found")
        _print("..", "Install from https://nodejs.org (LTS recommended)")
        _print("--", "Skipping dashboard (backend still works without it)")
        return True
    node_version = subprocess.run([node, "--version"], capture_output=True, text=True)
    _print("OK", f"Node.js {node_version.stdout.strip()}")

    # Check/install pnpm
    pnpm = shutil.which("pnpm")
    if not pnpm:
        npm = shutil.which("npm")
        if npm:
            _print("..", "Installing pnpm via npm...")
            subprocess.run([npm, "install", "-g", "pnpm"], capture_output=True)
            pnpm = shutil.which("pnpm")
        if not pnpm:
            _print("!!", "pnpm not found and could not be installed")
            _print("..", "Install manually: npm install -g pnpm")
            _print("--", "Skipping dashboard")
            return True
    _print("OK", "pnpm available")

    # Install dependencies
    _print("..", "Installing dashboard dependencies...")
    result = subprocess.run(
        [pnpm, "install"],
        cwd=str(dashboard_dir),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _print("!!", "pnpm install failed")
        _print("..", "Try manually: cd dashboard && pnpm install")
        return True  # Non-fatal

    # Build for production
    _print("..", "Building dashboard for production...")
    result = subprocess.run(
        [pnpm, "build"],
        cwd=str(dashboard_dir),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _print("!!", "Dashboard build failed")
        _print("..", "Try dev mode: cd dashboard && pnpm dev")
        return True  # Non-fatal

    static_dir = ENGINE_ROOT / "static"
    if static_dir.exists():
        file_count = sum(1 for _ in static_dir.rglob("*") if _.is_file())
        _print("OK", f"Dashboard built ({file_count} files in static/)")
    else:
        _print("OK", "Dashboard build completed")

    return True


# ─────────────────────────────────────────────────────────────
# Doctor command
# ─────────────────────────────────────────────────────────────

def run_doctor(project_root: Path):
    """Diagnose an existing RealizeOS installation."""
    print("\n  RealizeOS Doctor\n")
    issues = 0

    # Python
    v = sys.version_info
    _print("OK" if v >= (3, 11) else "!!", f"Python {v.major}.{v.minor}.{v.micro}")

    # Required packages
    for pkg in ["yaml", "fastapi", "uvicorn", "httpx", "anthropic"]:
        try:
            __import__(pkg)
            _print("OK", f"{pkg} installed")
        except ImportError:
            _print("!!", f"{pkg} NOT installed")
            issues += 1

    # .env
    env_path = project_root / ".env"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        has_anthropic = "ANTHROPIC_API_KEY=" in content and content.split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
        has_google = "GOOGLE_AI_API_KEY=" in content and content.split("GOOGLE_AI_API_KEY=")[1].split("\n")[0].strip()
        if has_anthropic or has_google:
            _print("OK", ".env with API key(s)")
        else:
            _print("!!", ".env exists but no API keys configured")
            issues += 1
    else:
        _print("!!", ".env not found")
        issues += 1

    # Config
    config_path = project_root / "realize-os.yaml"
    if config_path.exists():
        _print("OK", "realize-os.yaml found")
    else:
        _print("!!", "realize-os.yaml not found")
        issues += 1

    # Systems/ventures
    systems_dir = project_root / "systems"
    if systems_dir.exists():
        ventures = [d.name for d in systems_dir.iterdir() if d.is_dir()]
        _print("OK", f"{len(ventures)} venture(s): {', '.join(ventures) or 'none'}")
    else:
        _print("--", "No systems/ directory (run setup first)")

    # Dashboard
    static_dir = project_root / "static"
    if static_dir.exists() and any(static_dir.rglob("*.html")):
        _print("OK", "Dashboard built (static/ exists)")
        # Check that server will serve these files
        try:
            from realize_api.main import app as _app
            route_paths = [r.path for r in _app.routes if hasattr(r, 'path')]
            if "/{full_path:path}" in route_paths:
                _print("OK", "Dashboard serving configured")
            else:
                _print("!!", "Dashboard built but server not configured to serve it")
                issues += 1
        except Exception:
            pass
    else:
        _print("--", "Dashboard not built (run: cd dashboard && pnpm build)")

    # Node/pnpm
    node = shutil.which("node")
    pnpm = shutil.which("pnpm")
    _print("OK" if node else "--", f"Node.js: {'found' if node else 'not found'}")
    _print("OK" if pnpm else "--", f"pnpm: {'found' if pnpm else 'not found'}")

    # Server import
    try:
        from realize_api.main import app  # noqa: F401
        _print("OK", f"Server module loads ({len(app.routes)} routes)")
    except Exception as e:
        _print("!!", f"Server import error: {e}")
        issues += 1

    print()
    if issues == 0:
        print("  All checks passed. Run: python cli.py serve")
    else:
        print(f"  {issues} issue(s) found. Run: python cli.py setup")


# ─────────────────────────────────────────────────────────────
# Main wizard entry point
# ─────────────────────────────────────────────────────────────

def run_wizard(project_root: Path, skip_dashboard: bool = False):
    """Run the interactive setup wizard."""
    state_file = project_root / ".realize-setup.json"

    print()
    print("  ================================================")
    print("       RealizeOS 5 — Setup Wizard")
    print(f"       {platform.system()} | Python {sys.version_info.major}.{sys.version_info.minor}")
    print("  ================================================")

    # Check for previous state
    state = SetupState.load(state_file)
    if state and state.phases_done:
        print(f"\n  Previous setup found (completed: {', '.join(state.phases_done)})")
        if _ask_yn("Resume from where you left off?", True):
            pass  # Keep loaded state
        else:
            state = None

    if not state:
        state = SetupState(project_root=str(project_root))

    if skip_dashboard:
        state.install_dashboard = False

    # Phase 1: Prerequisites
    if "prerequisites" not in state.phases_done:
        if not phase_prerequisites():
            print("\n  Setup stopped at Phase 1. Fix the issues above and re-run.")
            state.save(state_file)
            return False
        state.phases_done.append("prerequisites")
        state.save(state_file)

    # Phase 2: Configuration
    if "configuration" not in state.phases_done:
        if not phase_configuration(state):
            print("\n  Setup stopped at Phase 2. Re-run to try again.")
            state.save(state_file)
            return False
        state.phases_done.append("configuration")
        state.save(state_file)

    # Phase 3: Initialization
    if "initialization" not in state.phases_done:
        if not phase_initialization(state):
            print("\n  Setup stopped at Phase 3. Fix the issues above and re-run.")
            state.save(state_file)
            return False
        state.phases_done.append("initialization")
        state.save(state_file)

    # Phase 4: Verification
    if "verification" not in state.phases_done:
        if not phase_verification(state):
            _print("!!", "Verification had issues, but setup can continue")
        state.phases_done.append("verification")
        state.save(state_file)

    # Phase 5: Dashboard
    if "dashboard" not in state.phases_done:
        phase_dashboard(state)
        state.phases_done.append("dashboard")
        state.save(state_file)

    # Done!
    print()
    print("  ================================================")
    print("  Setup complete! Start RealizeOS:")
    print()
    print("  Option 1 (no terminal needed):")
    print("    Double-click start-realizeos.bat (Windows)")
    print("    Double-click start-realizeos.command (macOS)")
    print()
    print("  Option 2 (terminal):")
    print("    python cli.py serve")
    print()
    print("  Then open http://localhost:8080")
    print()
    print("  Tip: Create a desktop shortcut to start-realizeos.bat")
    print("       for one-click launch!")
    print("  ================================================")
    print()

    # Clean up state file on success
    try:
        state_file.unlink(missing_ok=True)
    except Exception:
        pass

    return True
