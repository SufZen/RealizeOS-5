"""
Structured operational audit for RealizeOS.

The audit is organized around user-facing building blocks rather than folders so
operators can run focused review sessions with a consistent output format.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from realize_core.config import discover_workspace_state, load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankedFix:
    title: str
    risk: str
    effort: str


@dataclass(frozen=True)
class AuditBlockDefinition:
    key: str
    name: str
    purpose: str
    dependency_map: list[str]
    likely_hidden_bugs: list[str]
    top_fixes: list[RankedFix]
    regression_checks: list[str]
    done_criteria: list[str]


@dataclass
class AuditBlockReport:
    key: str
    name: str
    purpose: str
    dependency_map: list[str]
    current_failures: list[str]
    likely_hidden_bugs: list[str]
    top_fixes: list[dict[str, str]]
    regression_checks: list[str]
    done_criteria: list[str]


@dataclass
class AuditReport:
    summary: dict[str, object]
    audit_sequence: list[str]
    public_contracts: list[str]
    blocks: list[AuditBlockReport] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "summary": self.summary,
                "audit_sequence": self.audit_sequence,
                "public_contracts": self.public_contracts,
                "blocks": [asdict(block) for block in self.blocks],
            },
            indent=2,
        )


AUDIT_SEQUENCE = [
    "Deployment, Configuration, and Startup Foundation",
    "Security, Governance, and Trust Controls",
    "Data, Knowledge, Memory, and Storage",
    "Core Orchestration and Workflow Runtime",
    "LLM Routing and Agent Intelligence",
    "Tools, Integrations, Extensions, and Plugins",
    "API and Channel Surface",
    "Operator Experience: Dashboard and CLI",
]

PUBLIC_CONTRACTS = [
    "REST API routes and their response/error shapes",
    "SSE activity stream behavior",
    "CLI commands and setup/status flows",
    "FABRIC directory contract under systems/",
    "Extension/plugin entry-point contract",
    "Dashboard-to-API client contract",
]

BLOCK_DEFINITIONS: list[AuditBlockDefinition] = [
    AuditBlockDefinition(
        key="foundation",
        name="Deployment, Configuration, and Startup Foundation",
        purpose="Make the product boot predictably and expose setup problems before runtime failures cascade.",
        dependency_map=[
            ".env and realize-os.yaml",
            "Dockerfile and docker-compose",
            "Dashboard package manager and build pipeline",
            "FastAPI startup lifecycle and health checks",
        ],
        likely_hidden_bugs=[
            "Config file missing or drifting from on-disk FABRIC systems",
            "Native frontend dependencies broken after a lockfile or OS mismatch",
            "Container mounts or data paths pointing at the wrong directories",
            "Startup warnings masked by successful process launch",
        ],
        top_fixes=[
            RankedFix("Validate config presence and workspace state before serve/status flows", "high", "low"),
            RankedFix("Run dashboard lint and build with the repo's actual package manager in CI", "high", "medium"),
            RankedFix("Promote cold-start diagnostics into a first-class audit command", "medium", "medium"),
        ],
        regression_checks=[
            "Cold boot with missing config and empty .env",
            "Clean boot with one configured venture and one provider",
            "Dashboard lint plus build on a clean install",
            "Health check output for partially initialized workspaces",
        ],
        done_criteria=[
            "Startup failures are explicit and actionable",
            "Configured systems match the FABRIC directories that exist on disk",
            "Dashboard build verification runs in CI without mutating tracked assets",
        ],
    ),
    AuditBlockDefinition(
        key="security",
        name="Security, Governance, and Trust Controls",
        purpose="Keep unsafe actions blocked, auditable, and easy to reason about.",
        dependency_map=[
            "Security middleware stack",
            "JWT, RBAC, approvals, trust ladder",
            "Audit logging and secret redaction",
            "Security scanner outputs",
        ],
        likely_hidden_bugs=[
            "Routes that accidentally bypass permission checks",
            "Missing audit events for denied or partially executed actions",
            "Secrets leaking through error serialization",
            "Approval logic applied inconsistently across tools and workflows",
        ],
        top_fixes=[
            RankedFix("Keep deny-by-default permission coverage on sensitive routes", "high", "medium"),
            RankedFix("Assert secret redaction in error and audit paths", "high", "medium"),
            RankedFix("Add approval-path regression tests for approve/reject/retry flows", "medium", "medium"),
        ],
        regression_checks=[
            "Route-level auth matrix for admin and security endpoints",
            "Audit log entries for blocked or denied actions",
            "Approval-required tool flow with approve and reject outcomes",
            "Security scanner output remains available via API and CLI",
        ],
        done_criteria=[
            "Sensitive routes require the expected role or permission",
            "Denied and approved actions both leave an audit trail",
            "Error responses and logs redact secrets consistently",
        ],
    ),
    AuditBlockDefinition(
        key="data",
        name="Data, Knowledge, Memory, and Storage",
        purpose="Keep knowledge, memory, and persistence trustworthy so higher layers are debugging real state.",
        dependency_map=[
            "SQLite databases and migrations",
            "KB indexing and FABRIC directory loading",
            "Memory storage and pruning",
            "Storage sync and ingestion paths",
        ],
        likely_hidden_bugs=[
            "Stale KB indexes after file moves or partial rebuilds",
            "Duplicate or over-pruned memory entries",
            "SQLite locking under concurrent activity",
            "Encoding failures on non-UTF-8 or oversized content",
        ],
        top_fixes=[
            RankedFix("Keep WAL, timeout, and pruning checks covered in automated tests", "high", "low"),
            RankedFix("Add recovery-oriented checks for rebuild and migration flows", "medium", "medium"),
            RankedFix("Surface stale-index and storage-sync warnings in audits", "medium", "medium"),
        ],
        regression_checks=[
            "Venture CRUD plus KB rebuild and re-read",
            "SQLite lock and restart recovery scenario",
            "Mixed encoding and oversized file indexing",
            "Memory duplicate detection and pruning boundaries",
        ],
        done_criteria=[
            "Databases migrate cleanly and recover after restart",
            "Indexed knowledge matches the files on disk",
            "Memory retention rules are stable under repeated runs",
        ],
    ),
    AuditBlockDefinition(
        key="runtime",
        name="Core Orchestration and Workflow Runtime",
        purpose="Make the request-to-action pipeline observable, idempotent, and resistant to partial failure.",
        dependency_map=[
            "Base handler and prompt assembly",
            "Workflow and pipeline engines",
            "Scheduler, lifecycle, and heartbeat",
            "Activity bus and operational database",
        ],
        likely_hidden_bugs=[
            "Circular or retry-heavy workflows that fail noisily",
            "Partial state commits after tool or provider failures",
            "Duplicate scheduled work after restart",
            "Errors swallowed before they reach operator-visible surfaces",
        ],
        top_fixes=[
            RankedFix("Preserve end-to-end traceability from request to persisted activity", "high", "medium"),
            RankedFix("Test idempotency around scheduled and retried work", "high", "medium"),
            RankedFix("Audit error propagation across handler, workflow, and activity layers", "medium", "medium"),
        ],
        regression_checks=[
            "Chat request end-to-end through routing, prompt build, and response",
            "Workflow/pipeline execution with retry and failure edges",
            "Scheduler restart without duplicate jobs",
            "Activity log coverage for normal and failed runs",
        ],
        done_criteria=[
            "Operator-visible traces exist for successful and failed runs",
            "Retries are bounded and do not duplicate durable side effects",
            "Workflow failures stop in known states with actionable diagnostics",
        ],
    ),
    AuditBlockDefinition(
        key="llm",
        name="LLM Routing and Agent Intelligence",
        purpose="Keep model selection, persona behavior, and tool use aligned with the task and system policy.",
        dependency_map=[
            "Provider discovery and routing engine",
            "Agent persona, guardrails, and handoffs",
            "Prompt builder and context assembly",
            "Eval harness and fallbacks",
        ],
        likely_hidden_bugs=[
            "Provider discovery succeeding differently in local and deployed setups",
            "Wrong routing tier for a task because capability metadata drifts",
            "Prompt budget pressure dropping critical context",
            "Agents attempting tools they should not see",
        ],
        top_fixes=[
            RankedFix("Run routing and fallback audits with provider outage scenarios", "high", "medium"),
            RankedFix("Keep agent/tool gating tests close to persona changes", "high", "low"),
            RankedFix("Track prompt assembly size and missing-context regressions", "medium", "medium"),
        ],
        regression_checks=[
            "Provider outage, timeout, and fallback behavior",
            "Agent handoff and guardrail suites",
            "Routing decision goldens for simple/content/complex tasks",
            "Tool gating for allowed and denied actions",
        ],
        done_criteria=[
            "At least one provider is discoverable in the target environment",
            "Routing and fallbacks are deterministic under failure",
            "Agents respect persona and tool boundaries",
        ],
    ),
    AuditBlockDefinition(
        key="tools",
        name="Tools, Integrations, Extensions, and Plugins",
        purpose="Make external connectors fail safely and predictably without corrupting the core workflow.",
        dependency_map=[
            "Tool registry and gating",
            "Browser, web, messaging, Google, Stripe, and MCP integrations",
            "Extension loader and legacy plugins",
            "Credential and quota configuration",
        ],
        likely_hidden_bugs=[
            "Connector credentials expiring while the system still claims the tool is available",
            "Extension load-order or import issues only showing up at runtime",
            "Timeouts or partial successes without rollback or operator notice",
            "Webhook or browser sessions persisting in bad states after failure",
        ],
        top_fixes=[
            RankedFix("Add connector health checks that distinguish configured from actually usable", "high", "medium"),
            RankedFix("Audit timeout and retry behavior across tool boundaries", "high", "medium"),
            RankedFix("Keep extension and plugin compatibility checks in CI and smoke tests", "medium", "medium"),
        ],
        regression_checks=[
            "Connector auth expiry and rate-limit handling",
            "Extension load and plugin import smoke tests",
            "Browser and web-tool cleanup after failure",
            "Messaging or approval tool audit trail coverage",
        ],
        done_criteria=[
            "Configured tools report usable vs unavailable state clearly",
            "Connector failures leave consistent logs and no silent partial completion",
            "Extensions and plugins load in a reproducible order",
        ],
    ),
    AuditBlockDefinition(
        key="api",
        name="API and Channel Surface",
        purpose="Keep machine-facing contracts stable so dashboards, bots, and other clients see predictable behavior.",
        dependency_map=[
            "FastAPI routes and dependencies",
            "Structured error handlers",
            "SSE activity stream",
            "Channel adapters and webhooks",
        ],
        likely_hidden_bugs=[
            "Schema drift between backend routes and frontend expectations",
            "Inconsistent HTTP status codes across related endpoints",
            "SSE reconnect loops or duplicate events after disconnect",
            "Webhook replay or duplicate processing",
        ],
        top_fixes=[
            RankedFix("Treat route payloads and error shapes as versioned contracts", "high", "medium"),
            RankedFix("Exercise SSE disconnect and reconnect paths explicitly", "medium", "medium"),
            RankedFix("Keep replay-safe webhook handling under automated tests", "medium", "medium"),
        ],
        regression_checks=[
            "API route tests for happy path and validation failures",
            "SSE disconnect and reconnect handling",
            "Webhook duplicate delivery handling",
            "Dashboard API client compatibility checks",
        ],
        done_criteria=[
            "Routes return stable shapes for success and failure",
            "SSE streams tolerate disconnects without duplicating events",
            "Channel adapters can reject malformed requests safely",
        ],
    ),
    AuditBlockDefinition(
        key="operator",
        name="Operator Experience: Dashboard and CLI",
        purpose="Make the human operating the system see the right status, the right errors, and the next safe action.",
        dependency_map=[
            "Dashboard pages, hooks, and API client",
            "CLI status/setup/doctor flows",
            "Docs and onboarding surfaces",
            "Frontend build and package manager tooling",
        ],
        likely_hidden_bugs=[
            "Route crashes or blank states when APIs return partial data",
            "Frontend build drift hidden by successful linting",
            "Stale cached data after retries or background refreshes",
            "CLI status showing a clean state while the workspace is only partially initialized",
        ],
        top_fixes=[
            RankedFix("Expose partial-init warnings directly in CLI and audit output", "high", "low"),
            RankedFix("Verify dashboard build separately from lint and type checks", "high", "medium"),
            RankedFix("Document the operator audit flow with consistent per-block outputs", "medium", "low"),
        ],
        regression_checks=[
            "Dashboard load with API errors, empty states, and stale data",
            "CLI status and audit on missing-config workspaces",
            "Onboarding/setup documentation matches actual commands",
            "Frontend lint and build under the lockfile package manager",
        ],
        done_criteria=[
            "Operators can tell the difference between healthy, partial, and broken states quickly",
            "Dashboard build reliability is enforced outside local memory or tribal knowledge",
            "Audit sessions follow a repeatable structure across blocks",
        ],
    ),
]


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _check_dashboard_build(root: Path) -> dict[str, str | bool]:
    dashboard = root / "dashboard"
    if not dashboard.exists():
        return {"ok": False, "message": "Dashboard directory is missing."}

    if (dashboard / "pnpm-lock.yaml").exists():
        if _command_exists("pnpm"):
            command = ["pnpm", "exec", "vite", "build", "--outDir", ".audit-dist", "--emptyOutDir"]
            label = "pnpm"
        elif _command_exists("corepack"):
            command = ["corepack", "pnpm", "exec", "vite", "build", "--outDir", ".audit-dist", "--emptyOutDir"]
            label = "corepack pnpm"
        else:
            return {
                "ok": False,
                "message": "dashboard/pnpm-lock.yaml exists but neither pnpm nor corepack is available on PATH.",
            }
    elif (dashboard / "package-lock.json").exists():
        if not _command_exists("npx"):
            return {"ok": False, "message": "dashboard/package-lock.json exists but npx is not available on PATH."}
        command = ["npx", "vite", "build", "--outDir", ".audit-dist", "--emptyOutDir"]
        label = "npm"
    else:
        return {
            "ok": False,
            "message": "No dashboard lockfile found; build reproducibility is not guaranteed.",
        }

    try:
        result = subprocess.run(
            command,
            cwd=str(dashboard),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "message": f"Dashboard build probe could not run with {label}: {exc}"}
    finally:
        shutil.rmtree(dashboard / ".audit-dist", ignore_errors=True)

    if result.returncode == 0:
        return {"ok": True, "message": f"Dashboard build succeeded with {label}."}

    output = (result.stderr or result.stdout or "").strip().splitlines()
    detail = output[-1] if output else "Unknown dashboard build error."
    return {"ok": False, "message": f"Dashboard build failed with {label}: {detail}"}


def _find_frontend_tests(root: Path) -> bool:
    dashboard_src = root / "dashboard" / "src"
    if not dashboard_src.exists():
        return False
    patterns = ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx")
    return any(any(dashboard_src.rglob(pattern)) for pattern in patterns)


def _base_summary(root: Path, workspace: dict, quick: bool) -> dict[str, object]:
    return {
        "root": str(root),
        "quick": quick,
        "configured_systems": workspace["configured_system_keys"],
        "discovered_system_dirs": workspace["discovered_system_dirs"],
        "partial_initialization": workspace["partially_initialized"],
        "provider_configured": workspace["has_provider"],
        "recommended_next_block": AUDIT_SEQUENCE[0],
    }


def _current_failures_for_block(
    definition: AuditBlockDefinition,
    root: Path,
    workspace: dict,
    config: dict,
    dashboard_build: dict[str, str | bool] | None,
    has_frontend_tests: bool,
) -> list[str]:
    findings: list[str] = []

    if definition.key == "foundation":
        if not workspace["config_exists"]:
            findings.append(
                "Missing realize-os.yaml, so startup falls back to defaults instead of a declared workspace."
            )
        if workspace["unconfigured_system_dirs"]:
            findings.append(
                "FABRIC systems exist on disk but are not registered in realize-os.yaml: "
                + ", ".join(workspace["unconfigured_system_dirs"])
            )
        if not workspace["has_provider"]:
            findings.append("No LLM provider API key is configured, so agent routing cannot be validated end-to-end.")
        if dashboard_build and not dashboard_build["ok"]:
            findings.append(str(dashboard_build["message"]))

    elif definition.key == "security":
        if not os.getenv("REALIZE_API_KEY") and os.getenv("REALIZE_JWT_ENABLED", "").lower() not in (
            "true",
            "1",
            "yes",
        ):
            findings.append(
                "Neither REALIZE_API_KEY nor JWT auth is enabled, so local runs default to a low-friction trust model."
            )
        try:
            from realize_core.security.scanner import run_security_scan

            scan = run_security_scan(root)
            if scan.get("critical", 0):
                findings.append(f"Security scanner reports {scan['critical']} critical issue(s).")
            elif scan.get("warnings", 0):
                findings.append(f"Security scanner reports {scan['warnings']} warning(s).")
        except Exception as exc:
            findings.append(f"Security scanner could not run cleanly during audit: {exc}")

    elif definition.key == "data":
        if not workspace["configured_system_count"] and workspace["discovered_system_dirs"]:
            findings.append(
                "Knowledge directories exist, but none are active in config, so KB and memory behavior cannot be trusted for live usage."
            )
        if not workspace["has_runtime_databases"]:
            findings.append(
                "Runtime databases are not present yet, so restart/migration recovery has not been exercised in this workspace."
            )

    elif definition.key == "runtime":
        if workspace["configured_system_count"] == 0:
            findings.append(
                "No configured systems are loaded, so core orchestration cannot be exercised against a real venture."
            )
        if not config.get("features", {}).get("proactive_mode", True):
            findings.append(
                "Proactive mode is disabled, which changes scheduler and lifecycle behavior from the default runtime path."
            )

    elif definition.key == "llm":
        if not workspace["has_provider"]:
            findings.append(
                "No providers are configured, so routing, fallback, and agent-quality checks are currently theoretical only."
            )

    elif definition.key == "tools":
        if not os.getenv("BRAVE_API_KEY"):
            findings.append(
                "Web search is not configured, so web-tool audit coverage will miss live credential and quota behavior."
            )
        if os.getenv("BROWSER_ENABLED", "").lower() not in ("true", "1", "yes"):
            findings.append(
                "Browser tooling is disabled by environment, so browser automation paths need explicit enablement before live audit."
            )

    elif definition.key == "api":
        if workspace["configured_system_count"] == 0:
            findings.append(
                "API contracts are test-covered, but this workspace has no active systems loaded through config."
            )

    elif definition.key == "operator":
        if dashboard_build and not dashboard_build["ok"]:
            findings.append(str(dashboard_build["message"]))
        if not has_frontend_tests:
            findings.append("No dedicated dashboard test files were found under dashboard/src.")
        if workspace["partially_initialized"]:
            findings.append(
                "CLI/operator surfaces need to communicate partial initialization clearly in this workspace."
            )

    return findings or [
        "No blocking issue detected from static audit signals; validate this block against a live configured instance."
    ]


def build_audit_report(root: Path | None = None, quick: bool = False) -> AuditReport:
    root = (root or Path.cwd()).resolve()
    config = load_config(root / "realize-os.yaml")
    workspace = discover_workspace_state(root=root, config=config)
    dashboard_build = None if quick else _check_dashboard_build(root)
    has_frontend_tests = _find_frontend_tests(root)

    blocks = []
    for definition in BLOCK_DEFINITIONS:
        blocks.append(
            AuditBlockReport(
                key=definition.key,
                name=definition.name,
                purpose=definition.purpose,
                dependency_map=definition.dependency_map,
                current_failures=_current_failures_for_block(
                    definition=definition,
                    root=root,
                    workspace=workspace,
                    config=config,
                    dashboard_build=dashboard_build,
                    has_frontend_tests=has_frontend_tests,
                ),
                likely_hidden_bugs=definition.likely_hidden_bugs,
                top_fixes=[asdict(fix) for fix in definition.top_fixes],
                regression_checks=definition.regression_checks,
                done_criteria=definition.done_criteria,
            )
        )

    return AuditReport(
        summary=_base_summary(root=root, workspace=workspace, quick=quick),
        audit_sequence=AUDIT_SEQUENCE,
        public_contracts=PUBLIC_CONTRACTS,
        blocks=blocks,
    )


def format_audit_report(report: AuditReport) -> str:
    lines = ["RealizeOS Audit", "=" * 40, ""]
    summary = report.summary
    lines.append(f"Root: {summary['root']}")
    lines.append(f"Configured systems: {len(summary['configured_systems'])}")
    lines.append(f"Discovered FABRIC dirs: {len(summary['discovered_system_dirs'])}")
    lines.append(f"Provider configured: {'yes' if summary['provider_configured'] else 'no'}")
    lines.append(f"Partially initialized: {'yes' if summary['partial_initialization'] else 'no'}")
    if summary["configured_systems"]:
        lines.append("Active systems: " + ", ".join(summary["configured_systems"]))
    if summary["discovered_system_dirs"]:
        lines.append("On-disk systems: " + ", ".join(summary["discovered_system_dirs"]))

    lines.extend(["", "Recommended Sequence:"])
    for index, name in enumerate(report.audit_sequence, start=1):
        lines.append(f"  {index}. {name}")

    lines.extend(["", "Public Contracts:"])
    for contract in report.public_contracts:
        lines.append(f"  - {contract}")

    for index, block in enumerate(report.blocks, start=1):
        lines.extend(["", f"{index}. {block.name}", f"   Purpose: {block.purpose}"])
        lines.append("   Dependency map:")
        for item in block.dependency_map:
            lines.append(f"     - {item}")
        lines.append("   Current failures and likely breakpoints:")
        for item in block.current_failures:
            lines.append(f"     - {item}")
        lines.append("   Hidden bugs to probe:")
        for item in block.likely_hidden_bugs:
            lines.append(f"     - {item}")
        lines.append("   Top fixes:")
        for fix in block.top_fixes:
            lines.append(f"     - {fix['title']} [risk: {fix['risk']}, effort: {fix['effort']}]")
        lines.append("   Regression checks to add:")
        for item in block.regression_checks:
            lines.append(f"     - {item}")
        lines.append("   Done criteria:")
        for item in block.done_criteria:
            lines.append(f"     - {item}")

    return "\n".join(lines)
