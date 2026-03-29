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


@router.put("/storage/config")
async def update_storage_config(request: Request, config: StorageConfig):
    """Update storage configuration."""
    _save_config(config.model_dump())
    logger.info(f"Storage config updated: provider={config.provider}")
    return {"status": "ok", "message": "Storage configuration updated."}


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
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.post("/storage/export")
async def export_data(request: Request):
    """Export all user data as a downloadable zip."""
    try:
        base_dir = Path(os.getcwd())
        export_items = []

        # Collect exportable items
        for item_name in ["systems", ".credentials"]:
            item_path = base_dir / item_name
            if item_path.exists():
                export_items.append((item_name, item_path))

        for file_name in [".env", "realize-os.yaml"]:
            file_path = base_dir / file_name
            if file_path.exists():
                export_items.append((file_name, file_path))

        # Collect databases
        for db_file in base_dir.glob("*.db"):
            export_items.append((db_file.name, db_file))

        if not export_items:
            raise HTTPException(status_code=404, detail="No data to export.")

        # Create zip
        export_dir = base_dir / "backups"
        export_dir.mkdir(exist_ok=True)

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"realizeos-export-{timestamp}"
        zip_path = shutil.make_archive(
            str(export_dir / zip_name),
            "zip",
            root_dir=str(base_dir),
            base_dir=None,
        )

        return {
            "status": "ok",
            "message": "Data exported successfully.",
            "path": zip_path,
            "size_bytes": Path(zip_path).stat().st_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


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
    except Exception as exc:
        return {
            "backend": "local",
            "type": "unknown",
            "error": str(exc),
        }
