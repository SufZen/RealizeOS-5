"""
Storage settings API routes — configure cloud storage, export/import data.
"""

import json
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class StorageConfig(BaseModel):
    """Storage configuration model."""

    provider: str = "local"  # "local" | "s3"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint_url: str = ""
    sync_enabled: bool = False


STORAGE_CONFIG_FILE = ".storage-config.json"


def _get_config_path() -> Path:
    """Get the storage config file path."""
    return Path(os.getcwd()) / STORAGE_CONFIG_FILE


def _load_config() -> dict:
    """Load storage configuration from disk."""
    path = _get_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse storage config: %s", exc)
            return {"provider": "local"}
    return {"provider": "local"}


def _save_config(config: dict) -> None:
    """Save storage configuration to disk."""
    path = _get_config_path()
    # Don't save credentials in plain text — mask them
    safe = {**config}
    path.write_text(json.dumps(safe, indent=2), encoding="utf-8")


@router.get("/storage/config")
async def get_storage_config(request: Request):
    """Get current storage configuration."""
    config = _load_config()
    # Mask sensitive keys for the frontend
    if config.get("s3_access_key"):
        config["s3_access_key"] = "***" + config["s3_access_key"][-4:]
    if config.get("s3_secret_key"):
        config["s3_secret_key"] = "***" + config["s3_secret_key"][-4:]

    # Get storage stats
    systems_dir = Path(os.getcwd()) / "systems"
    total_size = 0
    venture_count = 0
    if systems_dir.exists():
        for item in systems_dir.iterdir():
            if item.is_dir():
                venture_count += 1
                for f in item.rglob("*"):
                    if f.is_file():
                        total_size += f.stat().st_size

    return {
        "config": config,
        "stats": {
            "ventures": venture_count,
            "total_size_bytes": total_size,
            "storage_path": str(systems_dir),
        },
    }


_SECRET_FIELDS = ("s3_access_key", "s3_secret_key")


@router.put("/storage/config")
async def update_storage_config(request: Request, config: StorageConfig):
    """Update storage configuration and apply it to the running storage layer.

    GET returns the S3 keys masked ("***abcd"); a masked value sent back
    keeps the stored key instead of overwriting it. The new provider is built
    before the file is saved, so a configuration that can't be used is
    refused and the old one stays in effect (Codex audit: saving used to
    change only the file, not the provider the app was using).
    """
    from realize_core.storage import factory

    previous = _load_config()
    merged = config.model_dump()
    for field in _SECRET_FIELDS:
        value = merged.get(field) or ""
        if value.startswith("***"):
            merged[field] = previous.get(field, "")
    try:
        factory.reconfigure(merged)
    except (ImportError, ValueError, OSError, RuntimeError) as exc:
        logger.warning("Storage config refused: %s", exc)
        factory.reconfigure(previous)
        raise HTTPException(status_code=400, detail=f"Storage configuration can't be used: {exc}") from exc
    _save_config(merged)
    logger.info(f"Storage config updated: provider={config.provider}")
    return {"status": "ok", "message": "Storage configuration updated and applied."}


@router.post("/storage/test")
async def test_storage_connection(request: Request, config: StorageConfig):
    """Test S3 connection with provided credentials."""
    if config.provider != "s3":
        return {"status": "ok", "message": "Local storage requires no connection test."}

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        kwargs = {
            "aws_access_key_id": config.s3_access_key,
            "aws_secret_access_key": config.s3_secret_key,
            "region_name": config.s3_region,
        }
        if config.s3_endpoint_url:
            kwargs["endpoint_url"] = config.s3_endpoint_url

        s3 = boto3.client("s3", **kwargs)
        # Try to list objects (limited to 1) to verify access
        s3.list_objects_v2(Bucket=config.s3_bucket, MaxKeys=1)
        return {"status": "ok", "message": f"Successfully connected to bucket '{config.s3_bucket}'."}

    except ImportError:
        raise HTTPException(status_code=500, detail="boto3 is not installed. Run: pip install boto3")
    except NoCredentialsError:
        raise HTTPException(status_code=400, detail="Invalid or missing credentials.")
    except ClientError as e:
        raise HTTPException(status_code=400, detail=f"S3 error: {e.response['Error']['Message']}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {e!s}")


#: What an export contains, relative to the KB root: the venture's brain and config.
_EXPORT_TREES = ("systems", "shared")
_EXPORT_FILES = ("realize-os.yaml",)


def _sqlite_snapshot(source: Path, dest: Path) -> None:
    """Copy a live SQLite database consistently (the backup API, not a file copy)."""
    import sqlite3

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()


def _build_export(kb_path: Path, zip_path: Path) -> list[str]:
    """Write the export ZIP and return the archive names it contains.

    An explicit list, never "the whole working directory" (Codex audit: the
    old export zipped cwd, including earlier exports and itself, and copied
    live SQLite files). Secrets (.env, .credentials) are not included.
    """
    import tempfile
    import zipfile

    from realize_core.config import synapse_dir
    from realize_core.db.schema import get_db_path
    from realize_core.memory.store import _resolve_db_path as memory_db_path

    names: list[str] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in _EXPORT_FILES:
            path = kb_path / rel
            if path.is_file():
                zf.write(path, rel)
                names.append(rel)
        for tree in _EXPORT_TREES:
            root = kb_path / tree
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts):
                    arcname = f"{tree}/{path.relative_to(root).as_posix()}"
                    zf.write(path, arcname)
                    names.append(arcname)

        synapse = synapse_dir(kb_path)
        databases = {
            "data/memory.db": memory_db_path(),
            "data/realize_data.db": get_db_path(),
            "data/synapse/synapse.db": synapse / "synapse.db",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for arcname, source in databases.items():
                if source and Path(source).is_file():
                    snapshot = Path(tmp) / Path(arcname).name
                    _sqlite_snapshot(Path(source), snapshot)
                    zf.write(snapshot, arcname)
                    names.append(arcname)
        inbox = synapse / "dream-inbox.jsonl"
        if inbox.is_file():
            zf.write(inbox, "data/synapse/dream-inbox.jsonl")
            names.append("data/synapse/dream-inbox.jsonl")
        names += _export_packs(zf, kb_path)
    return names


#: Where the writable pack folder (``REALIZE_PACKS_PATH``) goes in the export.
_CUSTOM_PACKS_ARCHIVE = "custom-packs"
#: The resolved-pack inventory in the export.
_PACKS_INVENTORY_ARCHIVE = "packs-inventory.json"


def _export_packs(zf, kb_path: Path) -> list[str]:
    """Add what a clean restore needs to resolve the same packs and levels.

    - the verification state approvals recorded (``data/packs/verification.json``);
    - the writable pack folder, ``REALIZE_PACKS_PATH`` (``custom-packs/``),
      without hidden files or anything that resolves outside it;
    - ``packs-inventory.json``: installed packs (versions, origin, content
      hash, levels) and what each venture resolves, to check the restore with
      ``python cli.py packs inventory --compare``.

    Shipped packs come with the release and are listed in the inventory only.
    """
    from realize_core.config import get_features, load_config
    from realize_core.packs import state as pack_state
    from realize_core.packs.inventory import build_inventory
    from realize_core.packs.loader import custom_packs_root

    names: list[str] = []
    try:
        state_file = pack_state.state_path()
    except pack_state.VerificationStateError as exc:
        logger.warning("Pack verification state not exported: %s", exc)
        state_file = None
    if state_file is not None and state_file.is_file():
        arcname = f"data/{pack_state.STATE_DIR}/{pack_state.STATE_FILE}"
        zf.write(state_file, arcname)
        names.append(arcname)

    custom = custom_packs_root()
    if custom is not None:
        for path in sorted(custom.rglob("*")):
            rel = path.relative_to(custom)
            if not path.is_file() or any(part.startswith(".") for part in rel.parts):
                continue
            if custom not in path.resolve().parents:
                logger.warning("Not exporting %s: it resolves outside %s", path, custom)
                continue
            arcname = f"{_CUSTOM_PACKS_ARCHIVE}/{rel.as_posix()}"
            zf.write(path, arcname)
            names.append(arcname)

    config_file = kb_path / "realize-os.yaml"
    try:
        enabled = bool(get_features(load_config(config_file)).get("packs")) if config_file.is_file() else None
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Could not read the packs flag for the inventory: %s", exc)
        enabled = None
    inventory = build_inventory(kb_path, packs_enabled=enabled)
    zf.writestr(_PACKS_INVENTORY_ARCHIVE, json.dumps(inventory, indent=2, ensure_ascii=False, default=str))
    names.append(_PACKS_INVENTORY_ARCHIVE)
    return names


@router.post("/storage/export")
async def export_data(request: Request):
    """Download the ventures' data as a ZIP.

    Contains realize-os.yaml, systems/ and shared/, consistent snapshots of
    the databases, the pack verification state, the writable pack folder
    (``REALIZE_PACKS_PATH``) and a resolved-pack inventory. API keys and
    credentials (.env, .credentials) are not included; copy them yourself when
    moving servers. The ZIP is built in a temp folder and removed after the
    download.
    """
    import asyncio
    import tempfile
    from datetime import datetime

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    kb_path = Path(getattr(request.app.state, "kb_path", None) or os.getcwd())
    tmp_dir = Path(tempfile.mkdtemp(prefix="realizeos-export-"))
    zip_name = f"realizeos-export-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = tmp_dir / zip_name
    try:
        names = await asyncio.to_thread(_build_export, kb_path, zip_path)
    except (OSError, ValueError) as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.error("Export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed; see server logs") from e
    if not names:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=404, detail="No data to export.")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_name,
        headers={"X-Export-Files": str(len(names))},
        background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
    )


@router.get("/storage/sync/status")
async def get_sync_status(request: Request):
    """Get current sync status with real data from the sync manager."""
    config = _load_config()

    # Try to get live sync manager status
    sync_info = {
        "sync_enabled": config.get("sync_enabled", False),
        "provider": config.get("provider", "local"),
        "is_running": False,
        "last_sync": None,
        "stats": {},
    }

    try:
        from realize_core.storage.factory import get_sync_manager

        mgr = get_sync_manager()
        if mgr is not None:
            sync_info["is_running"] = mgr.is_running
            sync_info["stats"] = mgr.get_sync_stats()

            # Get last completed sync
            history = mgr.get_sync_history(limit=1, status="completed")
            if history:
                last = history[0]
                sync_info["last_sync"] = {
                    "id": last.id,
                    "sync_type": last.sync_type,
                    "file_key": last.file_key,
                    "completed_at": last.completed_at,
                }
    except Exception as exc:
        logger.debug("Sync status query failed: %s", exc)

    return sync_info


@router.post("/storage/sync/trigger")
async def trigger_sync(request: Request):
    """Trigger a background incremental sync (push local → S3)."""
    config = _load_config()

    if not config.get("sync_enabled"):
        raise HTTPException(status_code=400, detail="Sync is not enabled in storage configuration.")

    try:
        import asyncio

        from realize_core.storage.factory import get_sync_manager

        mgr = get_sync_manager()
        if mgr is None:
            raise HTTPException(status_code=400, detail="Sync manager not available. Check S3 configuration.")

        if mgr.is_running:
            return {"status": "skipped", "message": "A sync is already in progress."}

        # Run sync in background (don't block the request)
        asyncio.create_task(mgr.incremental_sync())

        return {"status": "ok", "message": "Incremental sync started."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {exc}")


@router.get("/storage/sync/history")
async def sync_history(
    request: Request,
    limit: int = 50,
    status: str = "",
):
    """Get sync operation history."""
    try:
        from realize_core.storage.factory import get_sync_manager

        mgr = get_sync_manager()
        if mgr is None:
            return {"entries": [], "count": 0}

        entries = mgr.get_sync_history(limit=limit, status=status or None)
        return {
            "entries": [
                {
                    "id": e.id,
                    "sync_type": e.sync_type,
                    "source_backend": e.source_backend,
                    "target_backend": e.target_backend,
                    "file_key": e.file_key,
                    "file_size_bytes": e.file_size_bytes,
                    "status": e.status,
                    "error_message": e.error_message,
                    "created_at": e.created_at,
                    "completed_at": e.completed_at,
                }
                for e in entries
            ],
            "count": len(entries),
        }
    except Exception as exc:
        logger.debug("Sync history query failed: %s", exc)
        return {"entries": [], "count": 0}


@router.get("/storage/provider/info")
async def provider_info(request: Request):
    """Get info about the current active storage provider."""
    try:
        from realize_core.storage.factory import get_storage_provider

        provider = get_storage_provider()
        return {
            "backend": str(provider.backend),
            "type": type(provider).__name__,
            "repr": repr(provider),
        }
    except Exception:
        logger.warning("Storage provider lookup failed", exc_info=True)
        return {
            "backend": "local",
            "type": "unknown",
            "error": "Storage provider unavailable",
        }
