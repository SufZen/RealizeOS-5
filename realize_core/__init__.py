"""
RealizeOS Core Engine

The AI operations engine that powers RealizeOS. Provides multi-LLM routing,
dynamic prompt assembly, hybrid knowledge base search, multi-step skill
execution, and agent pipeline orchestration.

Usage:
    from realize_core.llm.router import classify_task, select_model, route_to_llm
    from realize_core.prompt.builder import build_system_prompt
    from realize_core.kb.indexer import KBIndexer
    from realize_core.skills.detector import detect_skill
    from realize_core.skills.executor import execute_skill
"""

from pathlib import Path as _Path


def _read_version() -> str:
    """Return the release version: repo ``VERSION`` file, else package metadata."""
    version_file = _Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("realize-os")
    except PackageNotFoundError:
        return "unknown"


__version__ = _read_version()
