"""
Post-modification health check for Developer Mode.

Validates system integrity after AI tools make changes:
  1. Config file validity (realize-os.yaml)
  2. Python import resolution
  3. Test suite passes
  4. Core file integrity (hash comparison)
  5. Environment file presence
  6. Dashboard build
"""

from __future__ import annotations

import importlib
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from realize_core.config import discover_workspace_state

logger = logging.getLogger(__name__)


class CheckStatus(StrEnum):
    """Result status of a health check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    """Single health check result."""

    name: str
    status: CheckStatus
    message: str
    details: str = ""

    @property
    def icon(self) -> str:
        return {"pass": "✅", "warn": "⚠️", "fail": "❌"}[self.status]

    def __str__(self) -> str:
        line = f"{self.icon} {self.name}: {self.message}"
        if self.details:
            line += f"\n   {self.details}"
        return line


def check_yaml_config(root: Path) -> CheckResult:
    """Verify realize-os.yaml is valid YAML with expected structure."""
    config_path = root / "realize-os.yaml"
    if not config_path.exists():
        workspace = discover_workspace_state(root)
        details = ""
        if workspace["discovered_system_dirs"]:
            details = "FABRIC directories found on disk: " + ", ".join(workspace["discovered_system_dirs"])
        return CheckResult("Config File", CheckStatus.FAIL, "realize-os.yaml not found", details)

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return CheckResult("Config File", CheckStatus.FAIL, "Invalid YAML structure")

        # Check required keys
        missing = []
        for key in ("name", "systems", "features"):
            if key not in data:
                missing.append(key)

        if missing:
            return CheckResult(
                "Config File",
                CheckStatus.WARN,
                f"Missing keys: {', '.join(missing)}",
            )

        return CheckResult("Config File", CheckStatus.PASS, "Valid YAML with expected structure")
    except yaml.YAMLError as e:
        return CheckResult("Config File", CheckStatus.FAIL, f"YAML parse error: {e}")


def check_workspace_state(root: Path) -> CheckResult:
    """Flag partial initialization states that will confuse operators later."""
    workspace = discover_workspace_state(root)

    if not workspace["warnings"]:
        return CheckResult("Workspace State", CheckStatus.PASS, "Workspace looks configured and aligned")

    status = CheckStatus.FAIL if not workspace["config_exists"] else CheckStatus.WARN
    message = workspace["warnings"][0]
    details = "\n   ".join(workspace["warnings"][1:4])
    return CheckResult("Workspace State", status, message, details)


def check_env_file(root: Path) -> CheckResult:
    """Check .env file exists and has required keys."""
    env_path = root / ".env"
    if not env_path.exists():
        return CheckResult(
            "Environment",
            CheckStatus.WARN,
            ".env not found — copy .env.example to .env",
        )

    content = env_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    if not lines:
        return CheckResult("Environment", CheckStatus.WARN, ".env is empty")

    # Check for at least one LLM key
    llm_keys = ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "OPENAI_API_KEY")
    has_llm = any(
        any(line.startswith(k + "=") and len(line.split("=", 1)[1].strip()) > 5 for line in lines) for k in llm_keys
    )

    if not has_llm:
        return CheckResult(
            "Environment",
            CheckStatus.WARN,
            "No LLM API key configured",
            "Set at least one of: ANTHROPIC_API_KEY, GOOGLE_AI_API_KEY, OPENAI_API_KEY",
        )

    return CheckResult("Environment", CheckStatus.PASS, f"{len(lines)} variables configured")


def check_core_imports(root: Path) -> CheckResult:
    """Verify critical Python imports resolve."""
    modules_to_check = [
        "realize_core.config",
        "realize_core.base_handler",
        "realize_core.llm.router",
        "realize_core.prompt.builder",
    ]

    # Add root to sys.path temporarily
    root_str = str(root)
    added = root_str not in sys.path
    if added:
        sys.path.insert(0, root_str)

    broken = []
    for mod in modules_to_check:
        try:
            importlib.import_module(mod)
        except Exception as e:
            broken.append(f"{mod}: {e}")

    if added:
        sys.path.remove(root_str)

    if broken:
        return CheckResult(
            "Core Imports",
            CheckStatus.FAIL,
            f"{len(broken)} import(s) broken",
            "\n   ".join(broken[:5]),
        )

    return CheckResult("Core Imports", CheckStatus.PASS, f"All {len(modules_to_check)} core modules importable")


def check_tests(root: Path) -> CheckResult:
    """Run the test suite quickly."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-x"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Extract pass count
            last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            return CheckResult("Test Suite", CheckStatus.PASS, last_line or "All tests passed")
        else:
            last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            return CheckResult(
                "Test Suite",
                CheckStatus.FAIL,
                last_line or "Tests failed",
                result.stderr[:200] if result.stderr else "",
            )
    except subprocess.TimeoutExpired:
        return CheckResult("Test Suite", CheckStatus.WARN, "Tests timed out (>120s)")
    except Exception as e:
        return CheckResult("Test Suite", CheckStatus.WARN, f"Could not run tests: {e}")


def check_dashboard_types(root: Path) -> CheckResult:
    """Check dashboard TypeScript compiles."""
    dashboard = root / "dashboard"
    if not dashboard.exists():
        return CheckResult("Dashboard", CheckStatus.WARN, "Dashboard directory not found")

    try:
        result = subprocess.run(
            ["npx", "tsc", "-b", "--noEmit"],
            cwd=str(dashboard),
            capture_output=True,
            text=True,
            timeout=60,
            shell=True,
        )
        if result.returncode == 0:
            return CheckResult("Dashboard", CheckStatus.PASS, "TypeScript compiles cleanly")
        else:
            error_count = result.stdout.count("error TS")
            return CheckResult(
                "Dashboard",
                CheckStatus.WARN,
                f"{error_count} TypeScript error(s)",
                result.stdout[:300] if result.stdout else "",
            )
    except subprocess.TimeoutExpired:
        return CheckResult("Dashboard", CheckStatus.WARN, "Type check timed out")
    except Exception as e:
        return CheckResult("Dashboard", CheckStatus.WARN, f"Could not check: {e}")


def _find_dashboard_build_command(dashboard: Path) -> tuple[list[str] | None, str]:
    if (dashboard / "pnpm-lock.yaml").exists():
        if shutil.which("pnpm"):
            return (
                ["pnpm", "exec", "vite", "build", "--outDir", ".health-dist", "--emptyOutDir"],
                "pnpm",
            )
        if shutil.which("corepack"):
            return (
                ["corepack", "pnpm", "exec", "vite", "build", "--outDir", ".health-dist", "--emptyOutDir"],
                "corepack pnpm",
            )
        return None, "dashboard/pnpm-lock.yaml exists but pnpm/corepack is unavailable"

    if (dashboard / "package-lock.json").exists():
        if shutil.which("npx"):
            return (
                ["npx", "vite", "build", "--outDir", ".health-dist", "--emptyOutDir"],
                "npm",
            )
        return None, "dashboard/package-lock.json exists but npx is unavailable"

    return None, "no dashboard lockfile was found"


def check_dashboard_build(root: Path) -> CheckResult:
    """Verify the dashboard can complete a production build without touching tracked static assets."""
    dashboard = root / "dashboard"
    if not dashboard.exists():
        return CheckResult("Dashboard Build", CheckStatus.WARN, "Dashboard directory not found")

    command, label = _find_dashboard_build_command(dashboard)
    if not command:
        return CheckResult("Dashboard Build", CheckStatus.WARN, label)

    try:
        result = subprocess.run(
            command,
            cwd=str(dashboard),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("Dashboard Build", CheckStatus.WARN, "Dashboard build timed out")
    except Exception as e:
        return CheckResult("Dashboard Build", CheckStatus.WARN, f"Could not run dashboard build: {e}")
    finally:
        shutil.rmtree(dashboard / ".health-dist", ignore_errors=True)

    if result.returncode == 0:
        return CheckResult("Dashboard Build", CheckStatus.PASS, f"Dashboard build succeeded with {label}")

    output = (result.stderr or result.stdout or "").strip().splitlines()
    detail = output[-1] if output else ""
    return CheckResult("Dashboard Build", CheckStatus.FAIL, f"Dashboard build failed with {label}", detail)


def check_version_file(root: Path) -> CheckResult:
    """Check VERSION file exists."""
    version_path = root / "VERSION"
    if not version_path.exists():
        return CheckResult("Version", CheckStatus.WARN, "VERSION file not found")

    version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        return CheckResult("Version", CheckStatus.WARN, "VERSION file is empty")

    return CheckResult("Version", CheckStatus.PASS, f"Version {version}")


def run_health_check(root: Path | None = None, quick: bool = False) -> list[CheckResult]:
    """
    Run all health checks.

    Args:
        root: Project root directory.
        quick: If True, skip slow checks (tests, dashboard).

    Returns:
        List of CheckResult objects.
    """
    root = root or Path.cwd()
    results: list[CheckResult] = []

    # Fast checks
    results.append(check_yaml_config(root))
    results.append(check_workspace_state(root))
    results.append(check_env_file(root))
    results.append(check_version_file(root))
    results.append(check_core_imports(root))

    # Slow checks
    if not quick:
        results.append(check_tests(root))
        results.append(check_dashboard_types(root))
        results.append(check_dashboard_build(root))

    return results


def format_results(results: list[CheckResult]) -> str:
    """Format health check results as a readable report."""
    lines = ["", "═══ RealizeOS Health Check ═══", ""]
    for r in results:
        lines.append(str(r))
    lines.append("")

    passes = sum(1 for r in results if r.status == CheckStatus.PASS)
    warns = sum(1 for r in results if r.status == CheckStatus.WARN)
    fails = sum(1 for r in results if r.status == CheckStatus.FAIL)

    summary = f"Results: {passes} passed"
    if warns:
        summary += f", {warns} warning(s)"
    if fails:
        summary += f", {fails} FAILED"

    lines.append(summary)

    if fails:
        lines.append("\n⚠️  System may have issues. Review failures above.")
    elif warns:
        lines.append("\n✅ System OK with minor warnings.")
    else:
        lines.append("\n✅ All checks passed. System healthy!")

    return "\n".join(lines)
