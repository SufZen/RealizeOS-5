"""Policy Overview — combined read-only view of both trust surfaces.

Covers ``realize_core.governance.policy_overview.effective_policy``: it returns
both the Dreaming (knowledge) and Governance (tools) surfaces, never raises even
with a malformed config, and reflects per-venture knowledge overrides. All tests
are hermetic and use ``tmp_path`` as the KB root.
"""

from __future__ import annotations

import yaml
from realize_core.governance.policy_overview import effective_policy
from realize_core.governance.trust_ladder import TrustDecision

_KNOWLEDGE_LEVELS = {"full-auto", "propose", "deny"}
_TOOL_DECISIONS = {d.value for d in TrustDecision}


def _write_venture_policy(kb_path, venture: str, mapping: dict) -> None:
    path = kb_path / "systems" / venture / "trust-policy.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"trust_policy": mapping}), encoding="utf-8")


def test_empty_config_returns_both_surfaces():
    """effective_policy({}) returns knowledge + tools + summary with valid values."""
    result = effective_policy({})

    assert isinstance(result, dict)

    # Knowledge surface: non-empty action -> level.
    knowledge = result["knowledge"]
    assert isinstance(knowledge, dict)
    assert knowledge
    assert set(knowledge.values()) <= _KNOWLEDGE_LEVELS
    # Defaults include a hard-denied action.
    assert knowledge["delete_entity"] == "deny"

    # Tools surface: action -> decision.
    tools = result["tools"]
    assert isinstance(tools, dict)
    assert tools
    assert set(tools.values()) <= _TOOL_DECISIONS
    # A known tool alias resolves through ACTION_MAP.
    assert tools["gmail_send"] in _TOOL_DECISIONS

    # Summary lines + no errors on a clean run.
    assert isinstance(result["summary"], list)
    assert result["summary"]
    assert "errors" not in result


def test_never_raises_on_malformed_config():
    """A malformed config must not raise; it falls back to a usable snapshot."""
    for bad in [None, "not-a-dict", 123, {"trust": "nonsense"}, {"trust": {"level": "x"}}]:
        result = effective_policy(bad)  # type: ignore[arg-type]
        assert isinstance(result["knowledge"], dict)
        assert isinstance(result["tools"], dict)
        assert isinstance(result["summary"], list)


def test_trust_level_changes_tool_decisions():
    """The current trust level drives the tools surface decisions."""
    low = effective_policy({"trust": {"level": 1}})
    high = effective_policy({"trust": {"level": 5}})

    # send_email is block at level 1 and auto at level 5 (default ladder).
    assert low["tools"]["send_email"] == TrustDecision.BLOCK.value
    assert high["tools"]["send_email"] == TrustDecision.AUTO.value
    assert low["trust_level"] == 1
    assert high["trust_level"] == 5


def test_venture_override_reflected_in_knowledge_surface(tmp_path):
    """With a tmp kb + venture file, the knowledge surface reflects the override."""
    # Default add_tag is full-auto; the venture makes it stricter.
    _write_venture_policy(tmp_path, "arena", {"add_tag": "propose"})

    overridden = effective_policy({}, kb_path=tmp_path, venture="arena")
    assert overridden["knowledge"]["add_tag"] == "propose"

    # Without the venture scope, defaults apply (add_tag stays full-auto).
    defaults = effective_policy({})
    assert defaults["knowledge"]["add_tag"] == "full-auto"
