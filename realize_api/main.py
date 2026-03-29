"""
RealizeOS API Server — FastAPI application.

Provides REST endpoints for chat, system management, and health checks.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from realize_api.error_handlers import register_error_handlers
from realize_api.middleware import APIKeyMiddleware
from realize_api.routes import (
    activity,
    agents_v2,
    approvals,
    auth,
    chat,
    dashboard,
    devmode,
    evolution,
    extensions,
    health,
    integrations,
    routing,
    security,
    settings,
    settings_llm,
    settings_memory,
    settings_reports,
    settings_security,
    settings_skills,
    settings_tools,
    settings_trust,
    setup,
    storage_settings,
    systems,
    venture_agents,
    venture_kb,
    venture_shared,
    ventures,
    webhooks,
    workflows,
)
from realize_api.security_middleware import (
    AuditMiddleware,
    InjectionGuardMiddleware,
    JWTAuthMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    # Startup
    logger.info("RealizeOS API starting up...")

    from realize_core.config import build_systems_dict, load_config

    config = load_config()
    app.state.config = config
    app.state.systems = build_systems_dict(config)
    app.state.kb_path = Path(config.get("kb_path", "."))
    app.state.shared_config = config.get(
        "shared",
        {
            "identity": "shared/identity.md",
            "preferences": "shared/user-preferences.md",
        },
    )

    # Initialize memory store
    from realize_core.memory.store import init_db

    init_db()

    # Initialize operational database (activity, agent states, approvals)
    try:
        from realize_core.db.migrations import run_migrations

        run_migrations()
        logger.info("Operational database initialized")
    except Exception as e:
        logger.warning(f"Operational DB initialization skipped: {e}")

    # Initialize KB index
    try:
        from realize_core.kb.indexer import index_kb_files

        index_kb_files(str(app.state.kb_path))
        logger.info("KB index initialized")
    except Exception as e:
        logger.warning(f"KB indexing skipped: {e}")

    # Warm prompt cache
    try:
        from realize_core.prompt.builder import warm_cache

        warm_cache(app.state.kb_path, app.state.systems, app.state.shared_config)
    except Exception as e:
        logger.debug(f"Cache warming skipped: {e}")

    # Initialize MCP if enabled
    if config.get("features", {}).get("mcp"):
        try:
            from realize_core.tools.mcp import initialize_mcp

            await initialize_mcp()
        except Exception as e:
            logger.warning(f"MCP initialization skipped: {e}")

    # Start heartbeat scheduler
    try:
        from realize_core.scheduler.heartbeat import start_scheduler

        scheduler_config = {
            "features": config.get("features", {}),
            "kb_path": app.state.kb_path,
            "shared_config": app.state.shared_config,
        }
        # Add per-system configs for heartbeat routing
        for sys_key, sys_conf in app.state.systems.items():
            scheduler_config[f"system_config:{sys_key}"] = sys_conf
        await start_scheduler(scheduler_config)
    except Exception as e:
        logger.warning(f"Heartbeat scheduler skipped: {e}")

    # Run security scan at startup
    try:
        from realize_core.security.scanner import run_security_scan

        scan = run_security_scan(Path("."))
        if scan.get("critical", 0) > 0:
            logger.error(
                "SECURITY SCAN: %d critical issue(s) found at startup!",
                scan["critical"],
            )
            for check in scan.get("checks", []):
                if check["status"] == "critical":
                    logger.error("  ✗ %s — %s", check["name"], check.get("detail", ""))
        elif scan.get("warnings", 0) > 0:
            logger.warning(
                "SECURITY SCAN: %d warning(s) — %d passed",
                scan["warnings"],
                scan["passed"],
            )
        else:
            logger.info("SECURITY SCAN: All %d checks passed ✓", scan["passed"])
    except Exception as e:
        logger.debug(f"Security scan skipped: {e}")

    # Initialize RBAC with custom roles (if YAML exists)
    try:
        from realize_core.security.rbac import get_rbac_manager

        rbac = get_rbac_manager()
        roles_path = Path(config.get("kb_path", ".")) / "roles.yaml"
        if roles_path.exists():
            count = rbac.load_from_yaml(roles_path)
            logger.info("Loaded %d custom RBAC roles", count)
    except Exception as e:
        logger.debug(f"RBAC initialization skipped: {e}")

    # Initialize audit logger with persistent log directory
    try:
        from realize_core.security.audit import get_audit_logger

        data_path = os.environ.get("DATA_PATH", "data")
        os.environ.setdefault("REALIZE_AUDIT_LOG_DIR", str(Path(data_path) / "audit"))
        audit = get_audit_logger()
        logger.info("Audit logger initialized (log: %s)", audit.log_file or "memory-only")
    except Exception as e:
        logger.debug(f"Audit logger init skipped: {e}")

    logger.info(f"RealizeOS API ready — {len(app.state.systems)} system(s) loaded")
    yield

    # Shutdown
    logger.info("RealizeOS API shutting down...")
    try:
        from realize_core.scheduler.heartbeat import stop_scheduler

        await stop_scheduler()
    except Exception as exc:
        logger.debug("Scheduler stop failed: %s", exc)
    try:
        from realize_core.tools.web import close_http_client

        await close_http_client()
    except Exception as exc:
        logger.debug("HTTP client cleanup failed: %s", exc)
    try:
        from realize_core.tools.browser import cleanup_all_sessions

        await cleanup_all_sessions()
    except Exception as exc:
        logger.debug("Browser session cleanup failed: %s", exc)
    try:
        from realize_core.tools.mcp import shutdown_mcp

        await shutdown_mcp()
    except Exception as exc:
        logger.debug("MCP shutdown failed: %s", exc)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from realize_core.utils.rate_limiter import build_rate_limiter

    app = FastAPI(
        title="RealizeOS",
        description="AI Operations System — Multi-agent, multi-venture, self-evolving.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.rate_limiter = build_rate_limiter()

    # CORS — defaults to localhost dev origins; production must set CORS_ORIGINS
    cors_env = os.environ.get("CORS_ORIGINS", "")
    if cors_env:
        allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        allowed_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]
    if "*" in allowed_origins:
        logger.warning("CORS wildcard (*) is enabled — not recommended for production")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
            "X-User-ID",
            "X-API-Key",
        ],
    )

    # Register centralized error handlers
    register_error_handlers(app)

    # --- Security middleware stack (order matters: outermost → innermost) ---

    # 0. Security headers — set on ALL responses
    app.add_middleware(SecurityHeadersMiddleware)

    # 1. Audit logging — outermost so it captures everything
    app.add_middleware(AuditMiddleware)

    # 2. Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # 3. Injection guard (scans POST/PUT/PATCH bodies)
    app.add_middleware(InjectionGuardMiddleware)

    # 4. JWT auth (opt-in via env var)
    if os.environ.get("REALIZE_JWT_ENABLED", "").lower() in ("true", "1", "yes"):
        app.add_middleware(JWTAuthMiddleware)
        logger.info("JWT authentication middleware enabled")

    # 5. API key auth (skip if no key configured — development mode)
    api_key = os.environ.get("REALIZE_API_KEY")
    if api_key:
        app.add_middleware(APIKeyMiddleware, api_key=api_key)

    # Routes
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(auth.router, prefix="/api", tags=["Authentication"])
    app.include_router(systems.router, prefix="/api", tags=["Systems"])
    app.include_router(health.router, prefix="/api", tags=["Health"])
    app.include_router(activity.router, prefix="/api", tags=["Activity"])
    app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
    app.include_router(ventures.router, prefix="/api", tags=["Ventures"])
    app.include_router(venture_agents.router, prefix="/api", tags=["Venture Agents"])
    app.include_router(venture_kb.router, prefix="/api", tags=["Venture KB"])
    app.include_router(venture_shared.router, prefix="/api", tags=["Shared Files"])
    app.include_router(approvals.router, prefix="/api", tags=["Approvals"])
    app.include_router(evolution.router, prefix="/api", tags=["Evolution"])
    app.include_router(settings.router, prefix="/api", tags=["Settings"])
    app.include_router(settings_llm.router, prefix="/api", tags=["Settings LLM"])
    app.include_router(settings_memory.router, prefix="/api", tags=["Settings Memory"])
    app.include_router(settings_reports.router, prefix="/api", tags=["Settings Reports"])
    app.include_router(settings_security.router, prefix="/api", tags=["Settings Security"])
    app.include_router(settings_skills.router, prefix="/api", tags=["Settings Skills"])
    app.include_router(settings_tools.router, prefix="/api", tags=["Settings Tools"])
    app.include_router(settings_trust.router, prefix="/api", tags=["Settings Trust"])
    app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])
    app.include_router(setup.router, prefix="/api", tags=["Setup"])
    # Sprint 3 — V2 API routes
    app.include_router(agents_v2.router, prefix="/api", tags=["Agents V2"])
    app.include_router(workflows.router, prefix="/api", tags=["Workflows"])
    app.include_router(extensions.router, prefix="/api", tags=["Extensions"])
    app.include_router(routing.router, prefix="/api", tags=["Routing"])
    app.include_router(integrations.router, prefix="/api", tags=["Integrations"])
    app.include_router(storage_settings.router, prefix="/api", tags=["Storage"])
    app.include_router(devmode.router, prefix="/api", tags=["Developer Mode"])
    app.include_router(security.router, prefix="/api", tags=["Security"])

    # Serve dashboard from static/ (only if built)
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists() and (static_dir / "index.html").exists():
        if (static_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

        @app.get("/favicon.svg")
        async def favicon():
            return FileResponse(static_dir / "favicon.svg")

        @app.get("/icons.svg")
        async def icons():
            return FileResponse(static_dir / "icons.svg")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path and not full_path.startswith("api/"):
                file_path = (static_dir / full_path).resolve()
                # Ensure resolved path is still under static_dir (prevents traversal)
                if file_path.is_file() and str(file_path).startswith(str(static_dir.resolve())):
                    return FileResponse(file_path)
            return FileResponse(static_dir / "index.html")

        logger.info(f"Dashboard serving from {static_dir}")

    return app


app = create_app()
