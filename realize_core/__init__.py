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

__version__ = "0.1.0"
