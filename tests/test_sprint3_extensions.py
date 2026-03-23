"""
Sprint 3 Tests — Extension system: registry, loader, cron, hooks.

Tests the Sprint 3 extension modules:
  1. ExtensionRegistry — registration, lifecycle, lookup, status
  2. ExtensionLoader — manifest parsing, filesystem discovery, config discovery
  3. CronExtension — lifecycle, NoOp scheduler, job API
  4. HooksExtension — subscribe/unsubscribe, emit, priority, error isolation
  5. __init__ re-exports
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from realize_core.extensions.base import (
    ExtensionManifest,
    ExtensionRegistration,
    ExtensionStatus,
    ExtensionType,
)

# ---------------------------------------------------------------------------
# Helpers: minimal extension implementation for testing
# ---------------------------------------------------------------------------


class _DummyExtension:
    """Minimal extension that satisfies the BaseExtension protocol."""

    def __init__(self, name: str = "dummy") -> None:
        self._name = name
        self._loaded = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def extension_type(self) -> ExtensionType:
        return ExtensionType.TOOL

    @property
    def manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            name=self._name,
            version="1.0.0",
            extension_type=ExtensionType.TOOL,
        )

    async def on_load(self, config=None) -> None:
        self._loaded = True

    async def on_unload(self) -> None:
        self._loaded = False

    def is_available(self) -> bool:
        return True


class _FailingExtension(_DummyExtension):
    """Extension that explodes on load."""

    async def on_load(self, config=None) -> None:
        msg = "BOOM"
        raise RuntimeError(msg)


# =====================================================================
# 1. ExtensionRegistry
# =====================================================================


class TestExtensionRegistry:
    """Tests for realize_core.extensions.registry."""

    def test_imports(self):
        pass

    def test_register(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        manifest = ExtensionManifest(name="test-ext", extension_type=ExtensionType.TOOL)
        result = reg.register(manifest)
        assert isinstance(result, ExtensionRegistration)
        assert result.name == "test-ext"
        assert result.status == ExtensionStatus.DISCOVERED

    def test_register_replaces(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        m1 = ExtensionManifest(name="ext", version="1.0.0")
        m2 = ExtensionManifest(name="ext", version="2.0.0")
        reg.register(m1)
        reg.register(m2)
        assert reg.count == 1
        assert reg.get("ext").manifest.version == "2.0.0"

    def test_register_instance(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _DummyExtension("my-ext")
        result = reg.register_instance(ext)
        assert result.status == ExtensionStatus.LOADED
        assert result.instance is ext

    def test_unregister(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        reg.register(ExtensionManifest(name="ext"))
        assert reg.unregister("ext")
        assert not reg.unregister("ext")
        assert reg.count == 0

    def test_load_unknown(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        result = asyncio.run(reg.load_extension("nonexistent"))
        assert not result

    def test_load_instance(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _DummyExtension("loadable")
        reg.register_instance(ext)
        result = asyncio.run(reg.load_extension("loadable"))
        assert result
        assert reg.get("loadable").status == ExtensionStatus.ACTIVE

    def test_load_failing(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _FailingExtension("fails")
        reg.register_instance(ext)
        result = asyncio.run(reg.load_extension("fails"))
        assert not result
        assert reg.get("fails").status == ExtensionStatus.ERROR
        assert "BOOM" in reg.get("fails").error_message

    def test_unload(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _DummyExtension("ul")
        reg.register_instance(ext)
        asyncio.run(reg.load_extension("ul"))
        assert asyncio.run(reg.unload_extension("ul"))
        assert reg.get("ul").status == ExtensionStatus.DISCOVERED
        assert reg.get("ul").instance is None

    def test_reload(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _DummyExtension("rl")
        reg.register_instance(ext)
        asyncio.run(reg.load_extension("rl"))
        result = asyncio.run(reg.reload_extension("rl"))
        assert result

    def test_load_all(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        for i in range(3):
            reg.register_instance(_DummyExtension(f"ext-{i}"))
        count = asyncio.run(reg.load_all())
        assert count == 3
        assert reg.active_count == 3

    def test_unload_all(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        for i in range(3):
            reg.register_instance(_DummyExtension(f"ext-{i}"))
        asyncio.run(reg.load_all())
        unloaded = asyncio.run(reg.unload_all())
        assert unloaded == 3
        assert reg.active_count == 0

    def test_disable(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        ext = _DummyExtension("dis")
        reg.register_instance(ext)
        asyncio.run(reg.load_extension("dis"))
        asyncio.run(reg.disable_extension("dis"))
        assert reg.get("dis").status == ExtensionStatus.DISABLED

    def test_get_by_type(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        reg.register(ExtensionManifest(name="t1", extension_type=ExtensionType.TOOL))
        reg.register(ExtensionManifest(name="h1", extension_type=ExtensionType.HOOK))
        assert len(reg.get_by_type(ExtensionType.TOOL)) == 1
        assert len(reg.get_by_type(ExtensionType.HOOK)) == 1

    def test_names_and_count(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        reg.register(ExtensionManifest(name="a"))
        reg.register(ExtensionManifest(name="b"))
        assert set(reg.names) == {"a", "b"}
        assert reg.count == 2

    def test_status_summary(self):
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        reg.register_instance(_DummyExtension("active-ext"))
        asyncio.run(reg.load_extension("active-ext"))
        summary = reg.status_summary()
        assert summary["total"] == 1
        assert summary["active"] == 1
        assert "active-ext" in summary["extensions"]

    def test_singleton(self):
        # Reset singleton for test isolation
        import realize_core.extensions.registry as mod
        from realize_core.extensions.registry import get_extension_registry

        mod._registry = None
        r1 = get_extension_registry()
        r2 = get_extension_registry()
        assert r1 is r2
        mod._registry = None  # cleanup

    def test_resolve_entry_point_invalid(self):
        from realize_core.extensions.registry import ExtensionRegistry

        assert ExtensionRegistry._resolve_entry_point("") is None
        assert ExtensionRegistry._resolve_entry_point("no_dot") is None


# =====================================================================
# 2. ExtensionLoader
# =====================================================================


class TestExtensionLoader:
    """Tests for realize_core.extensions.loader."""

    def test_imports(self):
        pass

    def test_discover_empty_directory(self):
        from realize_core.extensions.loader import ExtensionLoader
        from realize_core.extensions.registry import ExtensionRegistry

        reg = ExtensionRegistry()
        loader = ExtensionLoader(registry=reg, base_dir=tempfile.gettempdir())
        result = loader.discover_from_directory("/nonexistent/path")
        assert result == []

    def test_discover_from_directory_with_manifest(self):
        """Test discovery from a directory with extension.yaml."""
        from realize_core.extensions.loader import ExtensionLoader
        from realize_core.extensions.registry import ExtensionRegistry

        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = Path(tmpdir) / "my-ext"
            ext_dir.mkdir()
            manifest = {
                "name": "my-ext",
                "version": "1.0.0",
                "type": "tool",
                "description": "Test extension",
            }
            import yaml

            (ext_dir / "extension.yaml").write_text(
                yaml.dump(manifest),
                encoding="utf-8",
            )

            reg = ExtensionRegistry()
            loader = ExtensionLoader(registry=reg, base_dir=tmpdir)
            manifests = loader.discover_from_directory(tmpdir)
            assert len(manifests) == 1
            assert manifests[0].name == "my-ext"
            assert manifests[0].extension_type == ExtensionType.TOOL

    def test_discover_from_config(self):
        """Test discovery from a YAML config file."""
        from realize_core.extensions.loader import ExtensionLoader
        from realize_core.extensions.registry import ExtensionRegistry

        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "extensions": [
                    {
                        "name": "stripe-tools",
                        "type": "tool",
                        "entry_point": "some.module.Stripe",
                    },
                    {
                        "name": "slack-channel",
                        "type": "channel",
                    },
                ],
            }
            config_path = Path(tmpdir) / "realize-os.yaml"
            import yaml

            config_path.write_text(yaml.dump(config), encoding="utf-8")

            reg = ExtensionRegistry()
            loader = ExtensionLoader(registry=reg, base_dir=tmpdir)
            manifests = loader.discover_from_config(config_path)
            assert len(manifests) == 2
            names = {m.name for m in manifests}
            assert names == {"stripe-tools", "slack-channel"}

    def test_discover_all_deduplicates(self):
        """Config-defined extensions win over filesystem-discovered ones."""
        from realize_core.extensions.loader import ExtensionLoader
        from realize_core.extensions.registry import ExtensionRegistry

        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Config
            config = {
                "extensions": [{"name": "dupe", "type": "tool", "version": "2.0.0"}],
            }
            import yaml

            config_path = Path(tmpdir) / "realize-os.yaml"
            config_path.write_text(yaml.dump(config), encoding="utf-8")

            # Filesystem
            ext_dir = Path(tmpdir) / "extensions" / "dupe"
            ext_dir.mkdir(parents=True)
            (ext_dir / "extension.yaml").write_text(
                yaml.dump({"name": "dupe", "version": "1.0.0"}),
                encoding="utf-8",
            )

            reg = ExtensionRegistry()
            loader = ExtensionLoader(registry=reg, base_dir=tmpdir)
            manifests = loader.discover_all(config_path)
            assert len(manifests) == 1
            assert manifests[0].version == "2.0.0"  # config wins

    def test_discover_skips_hidden_dirs(self):
        from realize_core.extensions.loader import ExtensionLoader
        from realize_core.extensions.registry import ExtensionRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            hidden = Path(tmpdir) / ".hidden-ext"
            hidden.mkdir()
            (hidden / "extension.yaml").write_text("name: hidden")

            reg = ExtensionRegistry()
            loader = ExtensionLoader(registry=reg, base_dir=tmpdir)
            manifests = loader.discover_from_directory(tmpdir)
            assert len(manifests) == 0


# =====================================================================
# 3. CronExtension
# =====================================================================


class TestCronExtension:
    """Tests for realize_core.extensions.cron."""

    def test_imports(self):
        pass

    def test_protocol_compliance(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        assert ext.name == "cron"
        assert ext.extension_type == ExtensionType.INTEGRATION
        assert ext.is_available()

    def test_manifest(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        m = ext.manifest
        assert m.name == "cron"
        assert m.extension_type == ExtensionType.INTEGRATION

    def test_on_load_and_unload(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        asyncio.run(ext.on_load())
        assert ext._loaded
        assert ext.is_running  # NoOp scheduler starts
        asyncio.run(ext.on_unload())
        assert not ext._loaded

    def test_add_job(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        asyncio.run(ext.on_load())
        result = ext.add_job("test-job", func=lambda: None, trigger="interval", seconds=60)
        assert result
        assert ext.job_count == 1
        jobs = ext.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test-job"
        asyncio.run(ext.on_unload())

    def test_remove_job(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        asyncio.run(ext.on_load())
        ext.add_job("rm-job", func=lambda: None)
        assert ext.remove_job("rm-job")
        assert ext.job_count == 0
        asyncio.run(ext.on_unload())

    def test_add_job_before_load(self):
        from realize_core.extensions.cron import CronExtension

        ext = CronExtension()
        result = ext.add_job("early", func=lambda: None)
        assert not result

    def test_resolve_func_invalid(self):
        from realize_core.extensions.cron import CronExtension

        assert CronExtension._resolve_func("") is None
        assert CronExtension._resolve_func("no_dot") is None
        assert CronExtension._resolve_func("nonexistent.module.func") is None

    def test_noop_scheduler(self):
        from realize_core.extensions.cron import _NoOpScheduler

        sched = _NoOpScheduler()
        assert not sched.running
        sched.start()
        assert sched.running
        assert sched.add_job(lambda: None, id="x") is None
        assert sched.get_jobs() == []
        sched.shutdown()
        assert not sched.running


# =====================================================================
# 4. HooksExtension
# =====================================================================


class TestHooksExtension:
    """Tests for realize_core.extensions.hooks."""

    def test_imports(self):
        pass

    def test_protocol_compliance(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        assert ext.name == "hooks"
        assert ext.extension_type == ExtensionType.HOOK
        assert ext.is_available()

    def test_event_type_enum(self):
        from realize_core.extensions.hooks import EventType

        assert EventType.ON_MESSAGE == "on_message"
        assert EventType.ON_VENTURE_CHANGE == "on_venture_change"
        assert EventType.ON_AGENT_COMPLETE == "on_agent_complete"
        assert EventType.ON_ERROR == "on_error"

    def test_subscribe_and_emit(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        results_collector = []

        async def handler(data):
            results_collector.append(data)

        ext.subscribe("test_event", handler)
        asyncio.run(ext.emit("test_event", {"key": "value"}))
        assert len(results_collector) == 1
        assert results_collector[0]["key"] == "value"
        asyncio.run(ext.on_unload())

    def test_subscribe_sync_handler(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        results_collector = []

        def sync_handler(data):
            results_collector.append(data)

        ext.subscribe("sync_event", sync_handler)
        asyncio.run(ext.emit("sync_event", {"sync": True}))
        assert len(results_collector) == 1
        asyncio.run(ext.on_unload())

    def test_priority_ordering(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        order = []

        async def first(data):
            order.append("first")

        async def second(data):
            order.append("second")

        ext.subscribe("ordered", second, priority=10)
        ext.subscribe("ordered", first, priority=1)
        asyncio.run(ext.emit("ordered"))
        assert order == ["first", "second"]
        asyncio.run(ext.on_unload())

    def test_unsubscribe(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        async def handler(data):
            pass

        sub = ext.subscribe("event", handler)
        assert ext.subscription_count == 1
        assert ext.unsubscribe(sub)
        assert ext.subscription_count == 0
        asyncio.run(ext.on_unload())

    def test_unsubscribe_all(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        for i in range(5):
            ext.subscribe("bulk", lambda d: None)

        removed = ext.unsubscribe_all("bulk")
        assert removed == 5
        assert ext.subscription_count == 0
        asyncio.run(ext.on_unload())

    def test_emit_empty_event(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())
        results = asyncio.run(ext.emit("no_listeners"))
        assert results == []
        asyncio.run(ext.on_unload())

    def test_error_isolation(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        results_collector = []

        async def bad_handler(data):
            msg = "handler error"
            raise ValueError(msg)

        async def good_handler(data):
            results_collector.append("ok")

        ext.subscribe("err_event", bad_handler, priority=1)
        ext.subscribe("err_event", good_handler, priority=2)
        results = asyncio.run(ext.emit("err_event"))
        assert len(results) == 2
        assert results[0] is None  # bad handler
        assert len(results_collector) == 1  # good handler still ran
        asyncio.run(ext.on_unload())

    def test_fail_fast(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())

        async def bad_handler(data):
            msg = "boom"
            raise ValueError(msg)

        async def good_handler(data):
            pass

        ext.subscribe("ff", bad_handler, priority=1)
        ext.subscribe("ff", good_handler, priority=2)
        with pytest.raises(ValueError, match="boom"):
            asyncio.run(ext.emit("ff", fail_fast=True))
        asyncio.run(ext.on_unload())

    def test_get_events(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        ext.subscribe("a", lambda d: None)
        ext.subscribe("b", lambda d: None)
        assert set(ext.get_events()) == {"a", "b"}

    def test_emit_count(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())
        asyncio.run(ext.emit("e1"))
        asyncio.run(ext.emit("e2"))
        assert ext.emit_count == 2
        asyncio.run(ext.on_unload())
        assert ext.emit_count == 0

    def test_status_summary(self):
        from realize_core.extensions.hooks import HooksExtension

        ext = HooksExtension()
        asyncio.run(ext.on_load())
        ext.subscribe("ev", lambda d: None)
        summary = ext.status_summary()
        assert summary["loaded"]
        assert summary["total_subscriptions"] == 1
        asyncio.run(ext.on_unload())

    def test_singleton(self):
        import realize_core.extensions.hooks as mod
        from realize_core.extensions.hooks import get_hooks

        mod._hooks = None
        h1 = get_hooks()
        h2 = get_hooks()
        assert h1 is h2
        mod._hooks = None  # cleanup


# =====================================================================
# 5. __init__ re-exports
# =====================================================================


class TestExtensionPackageExports:
    """Verify the __init__.py re-exports work."""

    def test_all_exports(self):
        pass

    def test_dunder_all(self):
        import realize_core.extensions as ext

        assert hasattr(ext, "__all__")
        assert "ExtensionRegistry" in ext.__all__
        assert "HooksExtension" in ext.__all__
        assert "CronExtension" in ext.__all__
