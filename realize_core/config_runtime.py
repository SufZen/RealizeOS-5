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
    sync_skill_cascade(app_state, config)
    return config


def sync_skill_cascade(app_state: Any, config: dict) -> None:
    """Load the ventures' skills with their packs' skills when ``features.packs`` is on (spec 010).

    With the flag on, every venture's own skills and the skills its packs add
    are (re)loaded, so a reload picks up pack changes and a venture's own skill
    always wins over a pack skill with the same id. With the flag off and never
    on, nothing is loaded here: skill loading stays as it was before packs.
    Turning the flag off reloads without the pack skills.
    """
    from realize_core.config import get_features
    from realize_core.skills import detector

    enabled = bool(get_features(config).get("packs"))
    was_enabled = detector.pack_cascade_enabled()
    detector.configure_pack_cascade(enabled)
    kb = getattr(app_state, "kb_path", None)
    if kb is None or not (enabled or was_enabled):
        return
    detector.reload_skills(kb_path=Path(kb))


class FailClosedGate:
    """Stand-in installed when the real gate can't be built or updated.

    Enforcement was asked for but its policy couldn't be loaded, so nothing
    that may write runs: writes are blocked and reads still work (the same
    rule the registry applies when a gate raises).
    """

    def __init__(self, reason: str):
        self.reason = reason

    def update_config(self, config: dict | None) -> None:
        """Ignored: only a successful sync replaces this gate."""

    def decide(self, action_name: str, params: dict | None = None, *, is_destructive: bool | None = None):
        """Allow reads, block everything else."""
        from realize_core.governance.tool_gate import GateDecision, GateOutcome

        if is_destructive is False:
            return GateDecision(GateOutcome.ALLOW, action_name)
        return GateDecision(GateOutcome.BLOCK, action_name, reason=f"governance policy unavailable: {self.reason}")


def sync_tool_gate(app_state: Any, config: dict) -> None:
    """Make the registry's governance gate match ``features.enforce_gates`` and the trust config.

    Installs a gate when enforcement is turned on, removes it when turned off,
    and hands an existing gate the new config so a trust-level change applies
    to the next tool call, not the next restart. If the gate can't be built
    or updated, a :class:`FailClosedGate` goes in instead: a failure never
    leaves the system ungated while Settings say enforcement is on.
    """
    from realize_core.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    try:
        _apply_gate(app_state, config, registry)
    except Exception as exc:
        logger.error("Tool gate could not be applied; blocking writes until fixed: %s", exc, exc_info=True)
        gate = FailClosedGate(str(exc)[:200])
        app_state.tool_gate = gate
        registry.set_gate(gate)


def _apply_gate(app_state: Any, config: dict, registry: Any) -> None:
    """Install, update or remove the gate for ``config`` (may raise)."""
    from realize_core.config import get_features

    gate = getattr(app_state, "tool_gate", None)
    if get_features(config).get("enforce_gates"):
        if gate is None or isinstance(gate, FailClosedGate):
            from realize_core.governance.tool_gate import ToolGate
            from realize_core.tools.approval import ApprovalStore

            store = getattr(app_state, "approval_store", None) or ApprovalStore()
            app_state.approval_store = store
            gate = ToolGate(config=config, approval_store=store, kb_path=getattr(app_state, "kb_path", None))
            app_state.tool_gate = gate
            logger.warning("Governance ENFORCEMENT ON: tool gate installed (features.enforce_gates=true)")
        else:
            gate.update_config(config)
        registry.set_gate(gate)
    elif registry.has_gate or gate is not None:
        registry.set_gate(None)
        app_state.tool_gate = None
        logger.warning("Governance enforcement turned OFF: tool gate removed (features.enforce_gates=false)")
