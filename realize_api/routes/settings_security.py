"""
Security Scanner API.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/security/scan")
async def run_security_scan(request: Request):
    """Run a security scan of the system."""
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    config = getattr(request.app.state, "config", {})

    from realize_core.security.scanner import run_security_scan as _scan

    results = _scan(kb_path, config)
    return results
