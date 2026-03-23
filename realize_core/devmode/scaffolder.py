"""
Extension scaffolder for Developer Mode.

Generates boilerplate for new RealizeOS extensions, guiding
AI tools to add features through the extension system rather
than modifying core files.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EXTENSION_TYPES = ("tool", "channel", "integration", "hook")


def scaffold_extension(
    name: str,
    ext_type: str = "tool",
    root: Path | None = None,
    description: str = "",
) -> Path:
    """
    Create a new extension scaffold.

    Args:
        name: Extension name (kebab-case, e.g. 'stripe-payments').
        ext_type: Extension type: tool, channel, integration, or hook.
        root: Project root directory.
        description: Short description of the extension.

    Returns:
        Path to the created extension directory.
    """
    if ext_type not in EXTENSION_TYPES:
        raise ValueError(f"Invalid type '{ext_type}'. Must be one of: {EXTENSION_TYPES}")

    root = root or Path.cwd()
    ext_dir = root / "extensions" / name
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "tests").mkdir(exist_ok=True)

    # Convert kebab-case to PascalCase for class name
    class_name = "".join(word.capitalize() for word in name.split("-")) + "Extension"
    module_name = name.replace("-", "_")

    # 1. extension.yaml manifest
    manifest = f"""name: {name}
version: "1.0.0"
type: {ext_type}
description: "{description or f'A {ext_type} extension for RealizeOS'}"
author: ""
entry_point: "extensions.{module_name}.{class_name}"
dependencies: []
"""
    (ext_dir / "extension.yaml").write_text(manifest, encoding="utf-8")

    # 2. __init__.py with extension class
    init_code = f'''"""
{name} — {description or f'A {ext_type} extension for RealizeOS.'}
"""

from __future__ import annotations

import logging
from typing import Any

from realize_core.extensions.base import (
    BaseExtension,
    ExtensionManifest,
    ExtensionType,
)

logger = logging.getLogger(__name__)


class {class_name}:
    """
    {description or f'{ext_type.capitalize()} extension for RealizeOS.'}

    Implements the BaseExtension protocol for auto-discovery
    and lifecycle management.
    """

    def __init__(self) -> None:
        self._manifest = ExtensionManifest(
            name="{name}",
            version="1.0.0",
            extension_type=ExtensionType.{ext_type.upper()},
            description="{description or f'A {ext_type} extension'}",
        )

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def extension_type(self) -> ExtensionType:
        return self._manifest.extension_type

    @property
    def manifest(self) -> ExtensionManifest:
        return self._manifest

    async def on_load(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the extension."""
        logger.info("{name} extension loaded")
        # TODO: Add initialization logic here

    async def on_unload(self) -> None:
        """Clean up resources."""
        logger.info("{name} extension unloaded")

    def is_available(self) -> bool:
        """Check if dependencies are satisfied."""
        return True
'''
    (ext_dir / "__init__.py").write_text(init_code, encoding="utf-8")

    # 3. README.md
    readme = f"""# {name}

{description or f'A {ext_type} extension for RealizeOS.'}

## Installation

This extension is auto-discovered by RealizeOS at startup.
Place it in the `extensions/` directory.

## Configuration

Add configuration to `realize-os.yaml`:

```yaml
extensions:
  {name}:
    enabled: true
    # Add your config here
```

## Development

```bash
# Run tests
python -m pytest extensions/{name}/tests/ -v

# Check extension loads
python -c "from extensions.{module_name} import {class_name}; print({class_name}().name)"
```
"""
    (ext_dir / "README.md").write_text(readme, encoding="utf-8")

    # 4. Test skeleton
    test_code = f'''"""Tests for {name} extension."""

import pytest
from extensions.{module_name} import {class_name}


class Test{class_name}:
    """Tests for the {name} extension."""

    def test_name(self):
        ext = {class_name}()
        assert ext.name == "{name}"

    def test_is_available(self):
        ext = {class_name}()
        assert ext.is_available() is True

    @pytest.mark.asyncio
    async def test_on_load(self):
        ext = {class_name}()
        await ext.on_load()

    @pytest.mark.asyncio
    async def test_on_unload(self):
        ext = {class_name}()
        await ext.on_unload()
'''
    (ext_dir / "tests" / f"test_{module_name}.py").write_text(test_code, encoding="utf-8")

    logger.info(
        "Scaffolded extension '%s' (type=%s) at %s",
        name, ext_type, ext_dir,
    )
    return ext_dir
