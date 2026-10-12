"""
Apply a (re)loaded configuration to the running app.

Every place that reloads ``realize-os.yaml`` goes through
:func:`reload_app_config`, so the live state matches what Settings shows:
the config, the systems dict (built with the KB path) and the governance
tool gate the tool registry consults before dispatch.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def reload_app_config(app_state: Any, kb_path: str | Path | None = None, config: dict | None = None) -> dict:
    """Load (or take) the config and apply it to ``app_state``; return it.

    Args:
        app_state: ``app.state`` (or the MCP app-state proxy).
        kb_path: KB root for building systems; defaults to ``app_state.kb_path``.
        config: An already loaded config; loaded from disk when None.
    """
    from realize_core.config import build_systems_dict, load_config

    if config is None:
        config = load_config()
    kb = kb_path if kb_path is not None else getattr(app_state, "kb_path", None)
    app_state.config = config
    app_state.systems = build_systems_dict(config, Path(kb) if kb is not None else None)
    sync_tool_gate(app_state, config)
    return config


def sync_tool_gate(app_state: Any, config: dict) -> None:
    """Make the registry's governance gate match ``features.enforce_gates`` and the trust config.

    Installs a gate when enforcement is turned on, removes it when turned off,
    and hands an existing gate the new config so a trust-level change applies
    to the next tool call, not the next restart.
    """
    from realize_core.config import get_features
    from realize_core.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    gate = getattr(app_state, "tool_gate", None)

    if get_features(config).get("enforce_gates"):
        if gate is None:
            from realize_core.governance.tool_gate import ToolGate
            from realize_core.tools.approval import ApprovalStore

            store = getattr(app_state, "approval_store", None) or ApprovalStore()
            app_state.approval_store = store
            gate = ToolGate(config=config, approval_store=store)
            app_state.tool_gate = gate
            logger.warning("Governance ENFORCEMENT ON: tool gate installed (features.enforce_gates=true)")
        else:
            gate.update_config(config)
        registry.set_gate(gate)
    elif registry.has_gate or gate is not None:
        registry.set_gate(None)
        app_state.tool_gate = None
        logger.warning("Governance enforcement turned OFF: tool gate removed (features.enforce_gates=false)")
