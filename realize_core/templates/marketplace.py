"""
Vertical Template Marketplace — Community-ready venture templates.

Provides tools for:
- Packaging ventures into distributable templates
- Installing templates from a registry
- Listing available templates
- Template validation

Template format:
Each template is a directory containing:
- template.yaml (metadata + config)
- agents/ (agent persona definitions)
- skills/ (skill definitions)
- brand.yaml (brand profile)
- kb/ (sample knowledge base content)
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template models
# ---------------------------------------------------------------------------


class TemplateManifest:
    """Metadata describing a venture template."""

    def __init__(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "",
        vertical: str = "",
        tags: list[str] | None = None,
        requires: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.vertical = vertical
        self.tags = tags or []
        self.requires = requires or []
        self.metadata = metadata or {}
        self.created_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "vertical": self.vertical,
            "tags": self.tags,
            "requires": self.requires,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateManifest:
        return cls(
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            vertical=data.get("vertical", ""),
            tags=data.get("tags", []),
            requires=data.get("requires", []),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Template operations
# ---------------------------------------------------------------------------


def load_template_manifest(template_dir: Path) -> TemplateManifest | None:
    """Load template.yaml from a template directory."""
    try:
        import yaml  # noqa: F811
    except ImportError:
        logger.error("PyYAML required for template loading")
        return None

    manifest_path = template_dir / "template.yaml"
    if not manifest_path.exists():
        logger.warning("Template manifest not found: %s", manifest_path)
        return None

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            logger.warning("Invalid template manifest: %s", manifest_path)
            return None

        return TemplateManifest.from_dict(data)

    except Exception as e:
        logger.error("Failed to load template manifest: %s", e)
        return None


def validate_template(template_dir: Path) -> tuple[bool, list[str]]:
    """
    Validate a template directory has all required files.

    Returns (is_valid, list_of_errors).
    """
    errors: list[str] = []
    required_files = ["template.yaml"]

    for filename in required_files:
        if not (template_dir / filename).exists():
            errors.append(f"Missing required file: {filename}")

    # Check for at least one agent or skill
    agents_dir = template_dir / "agents"
    skills_dir = template_dir / "skills"
    has_agents = agents_dir.exists() and any(agents_dir.iterdir()) if agents_dir.exists() else False
    has_skills = skills_dir.exists() and any(skills_dir.iterdir()) if skills_dir.exists() else False

    if not has_agents and not has_skills:
        errors.append("Template must include at least one agent or skill definition")

    # Validate manifest loads
    manifest = load_template_manifest(template_dir)
    if manifest is None:
        errors.append("Could not load template.yaml")
    elif not manifest.name or manifest.name == "Untitled":
        errors.append("Template name is required in template.yaml")

    return len(errors) == 0, errors


def install_template(
    template_dir: Path,
    target_dir: Path,
    overwrite: bool = False,
) -> tuple[bool, str]:
    """
    Install a template to a target venture directory.

    Copies all template files to the target directory.
    """
    if not template_dir.exists():
        return False, f"Template directory not found: {template_dir}"

    is_valid, errors = validate_template(template_dir)
    if not is_valid:
        return False, f"Template validation failed: {'; '.join(errors)}"

    if target_dir.exists() and not overwrite:
        return False, f"Target directory already exists: {target_dir}"

    try:
        if target_dir.exists() and overwrite:
            shutil.rmtree(target_dir)

        shutil.copytree(template_dir, target_dir)
        logger.info("Template installed to: %s", target_dir)
        return True, f"✅ Template installed to {target_dir}"

    except Exception as e:
        return False, f"Installation failed: {e}"


# ---------------------------------------------------------------------------
# Template Registry (filesystem-based)
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """
    Registry of available templates.

    Initially filesystem-based; can be extended to GitHub-based
    registry for community templates.
    """

    def __init__(self, registry_dir: Path | None = None):
        self._registry_dir = registry_dir
        self._templates: dict[str, TemplateManifest] = {}
        if registry_dir and registry_dir.exists():
            self._scan_registry()

    def _scan_registry(self):
        """Scan registry directory for available templates."""
        if not self._registry_dir:
            return

        for item in self._registry_dir.iterdir():
            if item.is_dir():
                manifest = load_template_manifest(item)
                if manifest:
                    self._templates[manifest.name] = manifest

    def list_templates(
        self,
        vertical: str | None = None,
        tag: str | None = None,
    ) -> list[TemplateManifest]:
        """List available templates with optional filtering."""
        templates = list(self._templates.values())

        if vertical:
            templates = [t for t in templates if t.vertical == vertical]

        if tag:
            templates = [t for t in templates if tag in t.tags]

        return templates

    def get_template(self, name: str) -> TemplateManifest | None:
        """Get a template by name."""
        return self._templates.get(name)

    def register_template(self, template_dir: Path) -> tuple[bool, str]:
        """Register a template in the registry."""
        manifest = load_template_manifest(template_dir)
        if manifest is None:
            return False, "Could not load template manifest"

        self._templates[manifest.name] = manifest
        return True, f"Registered: {manifest.name} v{manifest.version}"

    @property
    def count(self) -> int:
        return len(self._templates)
