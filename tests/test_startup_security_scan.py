"""The startup security scan must not block the event loop (5.31 follow-up #2).

The scan asks the provider registry which providers are available, and the Ollama
``/api/tags`` probe can take up to 2s on a host without Ollama. The lifespan now runs
the scan in a worker thread, so the loop keeps serving while it runs.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import pytest


def _slow_scan(record: dict):
    def scan(project_root=None, config=None):
        record["thread"] = threading.current_thread()
        time.sleep(0.4)  # stands in for the Ollama probe timing out
        return {
            "passed": 1,
            "warnings": 0,
            "critical": 1,
            "checks": [{"name": "stub check", "status": "critical", "detail": "stub detail"}],
        }

    return scan


def test_startup_scan_runs_off_the_event_loop(monkeypatch, caplog):
    from realize_api import main
    from realize_core.security import scanner

    record: dict = {}
    monkeypatch.setattr(scanner, "run_security_scan", _slow_scan(record))

    async def scenario():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        tick_task = asyncio.create_task(ticker())
        loop_thread = threading.current_thread()
        await main._run_startup_security_scan()
        tick_task.cancel()
        return ticks, loop_thread

    with caplog.at_level(logging.ERROR, logger="realize_api.main"):
        ticks, loop_thread = asyncio.run(scenario())

    assert record["thread"] is not loop_thread, "the scan ran on the event-loop thread"
    assert ticks >= 5, f"the event loop was blocked during the scan (only {ticks} ticks)"
    # Results and logging are unchanged.
    assert "1 critical issue(s)" in caplog.text
    assert "stub check" in caplog.text


def test_startup_scan_failure_is_swallowed(monkeypatch):
    from realize_api import main
    from realize_core.security import scanner

    def boom(project_root=None, config=None):
        raise RuntimeError("scan broke")

    monkeypatch.setattr(scanner, "run_security_scan", boom)
    asyncio.run(main._run_startup_security_scan())  # must not raise


@pytest.mark.parametrize("name", ["_run_startup_security_scan"])
def test_lifespan_uses_the_threaded_scan(name):
    import inspect

    from realize_api import main

    src = inspect.getsource(main.lifespan)
    assert f"await {name}()" in src
    assert "run_security_scan(Path" not in src
