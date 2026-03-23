"""
Venture Export/Import: portable venture packages (.zip).

Export creates a sanitized zip of a venture's FABRIC structure.
Import restores a venture from a zip package.
"""

import json
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Files/patterns to exclude from export (secrets, caches)
EXCLUDE_PATTERNS = {
    ".env",
    ".env.local",
    "credentials.json",
    "token.json",
    "__pycache__",
    ".DS_Store",
    "Thumbs.db",
    "*.db",
    "*.sqlite",
    "*.pyc",
    "node_modules",
}


def export_venture(
    venture_key: str,
    kb_path: Path,
    output_path: Path = None,
    sys_conf: dict = None,
) -> Path:
    """
    Export a venture as a portable .zip package.

    Includes: FABRIC structure, agent definitions, skill definitions, sanitized config.
    Excludes: secrets, databases, caches.

    Returns the path to the created zip file.
    """
    sys_dir = kb_path / "systems" / venture_key
    if not sys_dir.exists():
        raise FileNotFoundError(f"Venture directory not found: {sys_dir}")

    output_path = output_path or Path(f"{venture_key}.zip")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Walk the venture directory
        for file_path in sorted(sys_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if _should_exclude(file_path):
                continue

            arcname = f"systems/{venture_key}/{file_path.relative_to(sys_dir)}"
            zf.write(file_path, arcname)

        # Include manifest
        manifest = {
            "venture_key": venture_key,
            "name": sys_conf.get("name", venture_key) if sys_conf else venture_key,
            "version": "1.0",
            "exported_by": "RealizeOS 5",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    file_count = len(zipfile.ZipFile(output_path).namelist())
    logger.info(f"Exported venture '{venture_key}' to {output_path} ({file_count} files)")
    return output_path


def import_venture(
    zip_path: Path,
    kb_path: Path,
    venture_key: str = None,
) -> dict:
    """
    Import a venture from a .zip package.

    Creates the venture directory structure and restores all files.

    Returns:
        { "venture_key": str, "files_imported": int }
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Import file not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Read manifest if present
        manifest = {}
        if "manifest.json" in zf.namelist():
            manifest = json.loads(zf.read("manifest.json"))

        # Determine venture key
        if not venture_key:
            venture_key = manifest.get("venture_key")
        if not venture_key:
            # Try to infer from first path in zip
            for name in zf.namelist():
                parts = Path(name).parts
                if len(parts) >= 2 and parts[0] == "systems":
                    venture_key = parts[1]
                    break
        if not venture_key:
            raise ValueError("Cannot determine venture key — provide --key or include manifest.json")

        # Extract files
        target_dir = kb_path / "systems" / venture_key
        files_imported = 0

        for zip_info in zf.infolist():
            if zip_info.is_dir() or zip_info.filename == "manifest.json":
                continue

            # Remap paths to target venture key
            parts = Path(zip_info.filename).parts
            if len(parts) >= 2 and parts[0] == "systems":
                # Replace original venture key with target key
                new_parts = ("systems", venture_key) + parts[2:]
                dest = kb_path / Path(*new_parts)
            else:
                dest = target_dir / zip_info.filename

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(zip_info.filename))
            files_imported += 1

    logger.info(f"Imported venture '{venture_key}' from {zip_path} ({files_imported} files)")
    return {"venture_key": venture_key, "files_imported": files_imported}


def _should_exclude(file_path: Path) -> bool:
    """Check if a file should be excluded from export."""
    name = file_path.name
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern or name in EXCLUDE_PATTERNS:
            return True
    return any(part in EXCLUDE_PATTERNS for part in file_path.parts)
