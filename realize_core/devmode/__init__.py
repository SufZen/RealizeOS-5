"""
RealizeOS Developer Mode — Safe AI client integration.

Enables local AI coding tools (Claude Code, Gemini CLI, Cursor, etc.)
to develop and extend the system with proper guardrails:

- File protection tiers (PROTECTED / GUARDED / OPEN)
- Context file generation for 9+ AI tools
- Git safety net (snapshot / rollback)
- Extension scaffolding
- Post-modification health checks
"""

from realize_core.devmode.protection import FileProtection, ProtectionTier

__all__ = ["FileProtection", "ProtectionTier"]
