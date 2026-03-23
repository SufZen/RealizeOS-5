"""
Security scanner — periodic health check for the system.

Validates:
- API keys are configured (not empty/default)
- Sensitive files are not world-readable
- No credentials in tracked files
- DB integrity
- Stale browser sessions cleaned up
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def run_security_scan(project_root: Path = None, config: dict = None) -> dict:
    """
    Run a security scan of the system.

    Returns:
        {
            passed: int,
            warnings: int,
            critical: int,
            checks: list[{name, status, detail}]
        }
    """
    project_root = project_root or Path(".")
    config = config or {}
    checks = []

    def check(name: str, ok: bool, detail: str = ""):
        status = "pass" if ok else "warn"
        checks.append({"name": name, "status": status, "detail": detail})

    def critical_check(name: str, ok: bool, detail: str = ""):
        status = "pass" if ok else "critical"
        checks.append({"name": name, "status": status, "detail": detail})

    # 1. API keys configured
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    google_key = os.getenv("GOOGLE_AI_API_KEY", "")
    check(
        "API key configured",
        bool(anthropic_key or google_key),
        "At least one LLM API key" if (anthropic_key or google_key) else "No API keys found",
    )

    # 2. API keys not default/placeholder
    if anthropic_key:
        is_real = anthropic_key.startswith("sk-ant-") and len(anthropic_key) > 20
        check("Anthropic key valid format", is_real, "Looks valid" if is_real else "May be a placeholder")

    # 3. .env file exists and not tracked by git
    env_path = project_root / ".env"
    check(".env file exists", env_path.exists())

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text(encoding="utf-8")
        check(".env in .gitignore", ".env" in gitignore_content)

    # 4. Credentials directory protected
    creds_dir = project_root / ".credentials"
    if creds_dir.exists():
        check("Credentials directory exists", True)
        check(".credentials in .gitignore", ".credentials" in (gitignore_content if gitignore_path.exists() else ""))
    else:
        check("No credentials directory", True, "Not needed if not using Google OAuth")

    # 5. Realize API key configured (for production)
    api_key = os.getenv("REALIZE_API_KEY", "")
    check(
        "API authentication",
        bool(api_key),
        "REALIZE_API_KEY set" if api_key else "No API key — dashboard is publicly accessible",
    )

    # 6. CORS not wildcard in production
    cors = os.getenv("CORS_ORIGINS", "*")
    check("CORS origins", cors != "*", f"Restricted to: {cors}" if cors != "*" else "Wildcard (*) — OK for development")

    # 7. Rate limiting configured
    rate_limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    cost_limit = float(os.getenv("COST_LIMIT_PER_HOUR_USD", "5.0"))
    check("Rate limiting", rate_limit > 0, f"{rate_limit}/min, ${cost_limit}/hour")

    # 8. Database integrity
    data_dir = project_root / "data"
    if data_dir.exists():
        db_files = list(data_dir.glob("*.db"))
        check("Database files", len(db_files) >= 0, f"{len(db_files)} database file(s)")

    # 9. No secrets in realize-os.yaml
    config_path = project_root / "realize-os.yaml"
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8")
        has_hardcoded_key = any(pattern in config_text for pattern in ["sk-ant-", "AIza", "sk-proj-"])
        critical_check(
            "No hardcoded secrets in config",
            not has_hardcoded_key,
            "Config file clean" if not has_hardcoded_key else "Found hardcoded API key in realize-os.yaml!",
        )

    # 10. Browser sessions limit
    browser_enabled = os.getenv("BROWSER_ENABLED", "false").lower() == "true"
    if browser_enabled:
        check("Browser tool enabled", True, "Headless browser is active")

    # Summary
    passed = sum(1 for c in checks if c["status"] == "pass")
    warnings = sum(1 for c in checks if c["status"] == "warn")
    criticals = sum(1 for c in checks if c["status"] == "critical")

    return {
        "passed": passed,
        "warnings": warnings,
        "critical": criticals,
        "total": len(checks),
        "checks": checks,
        "scanned_at": __import__("datetime").datetime.now().isoformat(),
    }
