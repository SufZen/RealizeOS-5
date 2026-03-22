"""
RealizeOS API Server — FastAPI application.

Provides REST endpoints for chat, system management, and health checks.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from realize_api.middleware import APIKeyMiddleware
from realize_api.routes import (
    activity,
    approvals,
    chat,
    dashboard,
    evolution,
    health,
    settings,
    setup,
    systems,
    ventures,
    webhooks,
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
    app.state.shared_config = config.get("shared", {
        "identity": "shared/identity.md",
        "preferences": "shared/user-preferences.md",
    })

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

    logger.info(f"RealizeOS API ready — {len(app.state.systems)} system(s) loaded")
    yield

    # Shutdown
    logger.info("RealizeOS API shutting down...")
    try:
        from realize_core.scheduler.heartbeat import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
    try:
        from realize_core.tools.web import close_http_client
        await close_http_client()
    except Exception:
        pass
    try:
        from realize_core.tools.browser import cleanup_all_sessions
        await cleanup_all_sessions()
    except Exception:
        pass
    try:
        from realize_core.tools.mcp import shutdown_mcp
        await shutdown_mcp()
    except Exception:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RealizeOS",
        description="AI Operations System — Multi-agent, multi-venture, self-evolving.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler — return JSON for all unhandled errors
    @app.exception_handler(Exception)
    async def global_exception_handler(request: FastAPIRequest, exc: Exception):
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": "internal_error"},
        )

    # API key auth (skip if no key configured — development mode)
    api_key = os.environ.get("REALIZE_API_KEY")
    if api_key:
        app.add_middleware(APIKeyMiddleware, api_key=api_key)

    # Routes
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(systems.router, prefix="/api", tags=["Systems"])
    app.include_router(health.router, tags=["Health"])
    app.include_router(activity.router, prefix="/api", tags=["Activity"])
    app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
    app.include_router(ventures.router, prefix="/api", tags=["Ventures"])
    app.include_router(approvals.router, prefix="/api", tags=["Approvals"])
    app.include_router(evolution.router, prefix="/api", tags=["Evolution"])
    app.include_router(settings.router, prefix="/api", tags=["Settings"])
    app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])
    app.include_router(setup.router, prefix="/api", tags=["Setup"])

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
            file_path = static_dir / full_path
            if file_path.is_file() and ".." not in full_path:
                return FileResponse(file_path)
            return FileResponse(static_dir / "index.html")

        logger.info(f"Dashboard serving from {static_dir}")

    return app


app = create_app()
