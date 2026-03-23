"""
Plugin Discovery & Loading: auto-discover plugins from the plugins/ directory.

Convention:
    plugins/
        my-plugin/
            plugin.yaml     # Manifest: name, version, type, entry_point
            __init__.py     # Python module with on_load/on_unload hooks

Manifest schema (plugin.yaml):
    name: "my-plugin"
    version: "1.0.0"
    type: "tool"           # tool | channel | integration
    entry_point: "__init__" # Python module name (relative to plugin dir)
    description: "What this plugin does"
    keywords: ["search", "web"]  # For tool plugins: trigger keywords
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Loaded plugins registry
_plugins: dict[str, dict] = {}


def discover_plugins(plugins_dir: Path = None) -> list[dict]:
    """
    Discover plugins from the plugins/ directory.

    Returns list of plugin manifests (not yet loaded).
    """
    plugins_dir = plugins_dir or Path("plugins")
    if not plugins_dir.exists():
        logger.debug(f"No plugins directory at {plugins_dir}")
        return []

    manifests = []
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed — cannot load plugin manifests")
        return []

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue

        manifest_path = plugin_dir / "plugin.yaml"
        if not manifest_path.exists():
            continue

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            if not manifest or not isinstance(manifest, dict) or "name" not in manifest:
                logger.warning(f"Invalid plugin manifest: {manifest_path}")
                continue

            manifest["_dir"] = str(plugin_dir)
            manifest["_manifest_path"] = str(manifest_path)
            manifests.append(manifest)
            logger.debug(f"Discovered plugin: {manifest['name']} ({manifest.get('type', 'unknown')})")

        except Exception as e:
            logger.warning(f"Failed to read plugin manifest {manifest_path}: {e}")

    return manifests


def load_plugin(manifest: dict) -> bool:
    """
    Load a single plugin from its manifest.

    Imports the entry point module and calls on_load() if defined.
    """
    name = manifest["name"]
    plugin_dir = Path(manifest["_dir"])
    entry_point = manifest.get("entry_point", "__init__")

    if name in _plugins:
        logger.debug(f"Plugin already loaded: {name}")
        return True

    try:
        module_path = plugin_dir / f"{entry_point}.py"
        if not module_path.exists():
            module_path = plugin_dir / entry_point / "__init__.py"
            if not module_path.exists():
                logger.warning(f"Plugin entry point not found: {name} ({module_path})")
                return False

        # Load the module
        spec = importlib.util.spec_from_file_location(f"plugins.{name}", str(module_path))
        if not spec or not spec.loader:
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"plugins.{name}"] = module
        spec.loader.exec_module(module)

        # Call on_load hook if defined
        on_load = getattr(module, "on_load", None)
        if callable(on_load):
            on_load()

        _plugins[name] = {
            **manifest,
            "_module": module,
            "_loaded": True,
        }
        logger.info(f"Loaded plugin: {name} v{manifest.get('version', '?')} ({manifest.get('type', 'unknown')})")
        return True

    except Exception as e:
        logger.error(f"Failed to load plugin '{name}': {e}")
        return False


def unload_plugin(name: str) -> bool:
    """Unload a plugin and call its on_unload hook."""
    plugin = _plugins.pop(name, None)
    if not plugin:
        return False

    module = plugin.get("_module")
    if module:
        on_unload = getattr(module, "on_unload", None)
        if callable(on_unload):
            try:
                on_unload()
            except Exception as e:
                logger.warning(f"Error in on_unload for '{name}': {e}")

        sys.modules.pop(f"plugins.{name}", None)

    logger.info(f"Unloaded plugin: {name}")
    return True


def load_all_plugins(plugins_dir: Path = None) -> int:
    """Discover and load all plugins. Returns count of successfully loaded plugins."""
    manifests = discover_plugins(plugins_dir)
    loaded = 0
    for manifest in manifests:
        if load_plugin(manifest):
            loaded += 1
    logger.info(f"Loaded {loaded}/{len(manifests)} plugins")
    return loaded


def get_loaded_plugins() -> dict[str, dict]:
    """Get all currently loaded plugins."""
    return dict(_plugins)


def get_tool_plugins() -> list[dict]:
    """Get all loaded plugins of type 'tool'."""
    return [p for p in _plugins.values() if p.get("type") == "tool"]


def get_plugin_keywords() -> dict[str, list[str]]:
    """Get keyword → plugin mapping for tool routing."""
    mapping = {}
    for p in get_tool_plugins():
        for kw in p.get("keywords", []):
            mapping.setdefault(kw, []).append(p["name"])
    return mapping
