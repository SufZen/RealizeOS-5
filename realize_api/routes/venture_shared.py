"""
Shared Files API routes — cross-venture shared file management.

Endpoints:
- GET  /api/shared/files — list shared files
- GET  /api/shared/file — read shared file
- PUT  /api/shared/file — save shared file
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/shared/files")
async def list_shared_files(request: Request):
    """List files in the shared directory."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))
    shared_dir = kb_path / "shared"

    if not shared_dir.exists():
        return {"files": []}

    files = []
    for f in sorted(shared_dir.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            files.append(
                {
                    "name": f.name,
                    "relative_path": str(f.relative_to(kb_path)),
                    "size": f.stat().st_size,
                    "directory": str(f.parent.relative_to(shared_dir)) if f.parent != shared_dir else "",
                }
            )
    return {"files": files}


@router.get("/shared/file")
async def read_shared_file(path: str, request: Request):
    """Read a shared file."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path / path
    try:
        file_path.resolve().relative_to(kb_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = file_path.read_text(encoding="utf-8")
    return {"path": path, "content": content, "size": file_path.stat().st_size}


@router.put("/shared/file")
async def save_shared_file(request: Request):
    """Save a shared file."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")

    if not path or ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path / path
    try:
        file_path.resolve().relative_to(kb_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return {"status": "saved", "path": path, "size": file_path.stat().st_size}
