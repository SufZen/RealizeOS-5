"""
Per-venture Dreaming Trust Policy.

Covers ``TrustPolicy.load_for_venture`` resolution/merge semantics and the
optional per-proposal ``policy`` override on ``DreamInbox.submit`` /
``submit_batch``. All tests are hermetic and use ``tmp_path`` as the KB root.
"""

from __future__ import annotations

import yaml
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import (
    DreamProposal,
    ProposalStatus,
    TrustLevel,
    TrustPolicy,
)


def _write_yaml(path, mapping: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"trust_policy": mapping}), encoding="utf-8")


def test_venture_overrides_global_and_inherits_rest(tmp_path):
    """Venture file overrides ONE action while inheriting the rest from global."""
    # Global makes update_summary auto and suggest_archive deny.
    _write_yaml(
        tmp_path / "shared" / "trust-policy.yaml",
        {"update_summary": "full-auto", "suggest_archive": "deny"},
    )
    # Venture only changes update_summary back to propose.
    _write_yaml(
        tmp_path / "systems" / "arena" / "trust-policy.yaml",
        {"update_summary": "propose"},
    )

    policy = TrustPolicy.load_for_venture(tmp_path, "arena")

    # Overridden by the venture file.
    assert policy.check("update_summary") == TrustLevel.PROPOSE
    # Inherited from the global file (not in the venture file).
    assert policy.check("suggest_archive") == TrustLevel.DENY
    # Inherited from the built-in defaults (in neither file).
    assert policy.check("add_tag") == TrustLevel.FULL_AUTO
    assert policy.check("delete_entity") == TrustLevel.DENY


def test_missing_venture_file_falls_back_to_global(tmp_path):
    """No venture file → global policy is the effective one."""
    _write_yaml(
        tmp_path / "shared" / "trust-policy.yaml",
        {"add_tag": "propose"},  # global makes add_tag stricter than default
    )
    # No systems/burtucala/trust-policy.yaml on disk.

    policy = TrustPolicy.load_for_venture(tmp_path, "burtucala")

    assert policy.check("add_tag") == TrustLevel.PROPOSE  # from global
    assert policy.check("delete_entity") == TrustLevel.DENY  # built-in default


def test_missing_both_files_uses_builtin_defaults(tmp_path):
    """No global and no venture file → built-in defaults only."""
    policy = TrustPolicy.load_for_venture(tmp_path, "nope")

    assert policy.check("add_tag") == TrustLevel.FULL_AUTO
    assert policy.check("update_summary") == TrustLevel.PROPOSE
    assert policy.check("delete_entity") == TrustLevel.DENY


def test_venture_layer_merges_over_global_for_distinct_actions(tmp_path):
    """Global and venture touch different actions — both survive the merge."""
    _write_yaml(
        tmp_path / "shared" / "trust-policy.yaml",
        {"merge_entities": "full-auto"},
    )
    _write_yaml(
        tmp_path / "systems" / "arena" / "trust-policy.yaml",
        {"create_insight": "deny"},
    )

    policy = TrustPolicy.load_for_venture(tmp_path, "arena")

    assert policy.check("merge_entities") == TrustLevel.FULL_AUTO  # global
    assert policy.check("create_insight") == TrustLevel.DENY  # venture


def test_submit_with_venture_policy_override(tmp_path):
    """submit(proposal, policy=venture) gates by the venture policy."""
    inbox = DreamInbox(inbox_path=tmp_path / "inbox.jsonl", policy=TrustPolicy())

    # update_summary is PROPOSE under the default inbox policy.
    venture_policy = TrustPolicy(overrides={"update_summary": "full-auto"})

    # With the venture override → auto-approved.
    pid_override = inbox.submit(
        DreamProposal(action="update_summary", title="Venture auto"),
        policy=venture_policy,
    )
    assert inbox.get(pid_override).status == ProposalStatus.APPROVED

    # Without an override → still PROPOSE → pending (default behavior preserved).
    pid_default = inbox.submit(DreamProposal(action="update_summary", title="Default pending"))
    assert inbox.get(pid_default).status == ProposalStatus.PENDING


def test_submit_batch_with_venture_policy_override(tmp_path):
    """submit_batch forwards the per-venture policy to every proposal."""
    inbox = DreamInbox(inbox_path=tmp_path / "inbox.jsonl", policy=TrustPolicy())
    venture_policy = TrustPolicy(overrides={"suggest_decision": "full-auto"})

    pids = inbox.submit_batch(
        [
            DreamProposal(action="suggest_decision", title="A"),
            DreamProposal(action="suggest_decision", title="B"),
        ],
        policy=venture_policy,
    )

    assert all(inbox.get(pid).status == ProposalStatus.APPROVED for pid in pids)


def test_submit_without_policy_is_unchanged(tmp_path):
    """Default (no policy arg) gating matches the inbox's own policy exactly."""
    inbox = DreamInbox(inbox_path=tmp_path / "inbox.jsonl", policy=TrustPolicy())

    auto = inbox.submit(DreamProposal(action="add_tag", title="auto"))
    pending = inbox.submit(DreamProposal(action="create_insight", title="pending"))
    denied = inbox.submit(DreamProposal(action="delete_entity", title="denied"))

    assert inbox.get(auto).status == ProposalStatus.APPROVED
    assert inbox.get(pending).status == ProposalStatus.PENDING
    assert inbox.get(denied).status == ProposalStatus.REJECTED
