"""Policy Overview — a single read-only view of BOTH trust surfaces.

RealizeOS intentionally runs two trust surfaces that govern *different* layers
(see ADR 0002):

1. **Knowledge (Dreaming)** — :class:`realize_core.dreaming.policy.TrustPolicy`
   governs self-evolving KNOWLEDGE writes (add_tag, modify_decision, ...) with
   levels FULL_AUTO / PROPOSE / DENY.
2. **Tools (Governance)** — :func:`realize_core.governance.trust_ladder.check_trust`
   governs TOOL execution (gmail_send -> send_email, ...) with the 5-tier ladder,
   resolving to BLOCK / APPROVE / AUTO at the system's current trust level.

This module does **not** change either system's behavior. It only *reads* both
through their public APIs and returns a combined snapshot so an operator or
dashboard can see the effective policy in one place. It never raises and has no
side effects.
"""

from __future__ import annotations

from pathlib import Path

from realize_core.dreaming.policy import TrustPolicy
from realize_core.governance.trust_ladder import (
    ACTION_MAP,
    check_trust,
    get_trust_level,
    get_trust_rules,
)


def _knowledge_surface(kb_path: Path | None, venture: str | None) -> dict[str, str]:
    """Return the Dreaming policy as ``{action: level}`` using public APIs."""
    if kb_path is not None and venture:
        policy = TrustPolicy.load_for_venture(kb_path, venture)
    else:
        policy = TrustPolicy()
    return policy.all_actions


def _tool_surface(config: dict) -> dict[str, str]:
    """Return ``{governance_action: decision}`` for all KNOWN governance actions.

    The action list is derived from trust_ladder's public surface: the configured
    trust rules (``get_trust_rules``) give the canonical trust-action types, and
    ``ACTION_MAP`` contributes the tool-level aliases that route into them. Each is
    resolved through the public :func:`check_trust` at the current trust level.
    """
    actions = set(get_trust_rules(config).keys())
    actions.update(ACTION_MAP.keys())
    return {action: check_trust(action, config).value for action in sorted(actions)}


def effective_policy(
    config: dict,
    kb_path: Path | str | None = None,
    venture: str | None = None,
) -> dict:
    """Return a combined, read-only view of both trust surfaces.

    Args:
        config: System configuration dict (read for ``config['trust']``).
        kb_path: Optional KB root. When given together with ``venture``, the
            knowledge surface reflects the venture's effective Dreaming policy;
            otherwise the built-in defaults are returned.
        venture: Optional venture key for the knowledge surface override.

    Returns:
        A dict with keys:

        - ``"knowledge"``: ``{action: level}`` — the Dreaming policy
          (FULL_AUTO / PROPOSE / DENY).
        - ``"tools"``: ``{action: decision}`` — the Governance decisions
          (BLOCK / APPROVE / AUTO) at the current trust level.
        - ``"trust_level"``: the current system trust level (1-5).
        - ``"summary"``: a list of human-readable lines describing both surfaces.
        - ``"errors"``: present only if a surface failed to build; maps the
          surface name to its error string.

    Never raises: any failure in a surface is caught, recorded under
    ``"errors"``, and that surface is returned empty. No writes, no side effects.
    """
    config = config if isinstance(config, dict) else {}
    errors: dict[str, str] = {}

    try:
        knowledge = _knowledge_surface(Path(kb_path) if kb_path is not None else None, venture)
    except Exception as e:
        knowledge = {}
        errors["knowledge"] = f"{type(e).__name__}: {e}"

    try:
        tools = _tool_surface(config)
    except Exception as e:
        tools = {}
        errors["tools"] = f"{type(e).__name__}: {e}"

    try:
        trust_level = get_trust_level(config)
    except Exception as e:
        trust_level = None
        errors.setdefault("trust_level", f"{type(e).__name__}: {e}")

    scope = f"venture '{venture}'" if (kb_path is not None and venture) else "defaults"
    summary = [
        "RealizeOS runs two intentionally separate trust surfaces (see ADR 0002).",
        f"Knowledge (Dreaming): {len(knowledge)} action(s) governing self-evolving "
        f"KNOWLEDGE writes as FULL_AUTO / PROPOSE / DENY — showing {scope}.",
        f"Tools (Governance): {len(tools)} action(s) governing TOOL execution as "
        f"BLOCK / APPROVE / AUTO at trust level {trust_level}.",
    ]

    result: dict = {
        "knowledge": knowledge,
        "tools": tools,
        "trust_level": trust_level,
        "summary": summary,
    }
    if errors:
        result["errors"] = errors
    return result
