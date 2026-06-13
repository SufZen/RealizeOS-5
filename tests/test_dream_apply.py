"""
Tests for the Dream apply-loop (feature 004, US1).

Hermetic: each test builds a real ``git init``'d venture directory with a
sample FABRIC entity under ``tmp_path``, seeds approved proposals into a real
``DreamInbox``, runs :func:`apply_approved`, and asserts the FABRIC write, the
``dream:`` git commit, the proposal status, and the safety guards.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from realize_core.dreaming.apply import apply_approved
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import DreamProposal, ProposalStatus, TrustPolicy
from realize_core.fabric.crud import read_entity

# ── Fixtures / helpers ───────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _write_entity(
    repo: Path,
    layer: str,
    slug: str,
    entity_id: str,
    entity_type: str = "insight",
    extra_fm: str = "",
    tags: str = "",
) -> Path:
    """Write a minimal FABRIC entity markdown file and commit it."""
    layer_dir = repo / layer
    layer_dir.mkdir(parents=True, exist_ok=True)
    path = layer_dir / f"{slug}.md"
    fm = [
        "---",
        f"id: {entity_id}",
        f"type: {entity_type}",
        f"title: {slug.replace('-', ' ').title()}",
        f"slug: {slug}",
    ]
    if tags:
        fm.append(f"tags: [{tags}]")
    if extra_fm:
        fm.append(extra_fm)
    fm.append("---")
    path.write_text("\n".join(fm) + "\n\nBody.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"seed {entity_id}")
    return path


def _make_inbox(tmp_path: Path) -> DreamInbox:
    return DreamInbox(
        inbox_path=tmp_path / "inbox.jsonl",
        policy=TrustPolicy(),
    )


def _seed_approved(inbox: DreamInbox, proposal: DreamProposal) -> DreamProposal:
    """Inject an already-APPROVED proposal directly into the inbox."""
    proposal.status = ProposalStatus.APPROVED
    proposal.reviewed_at = datetime.now()
    proposal.reviewed_by = "test"
    inbox._proposals[proposal.proposal_id] = proposal
    inbox._save()
    return proposal


def _commit_count(repo: Path) -> int:
    out = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        check=True,
        text=True,
    )
    return int(out.stdout.strip())


def _last_message(repo: Path) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=str(repo),
        capture_output=True,
        check=True,
        text=True,
    )
    return out.stdout.strip()


# ── Tests ────────────────────────────────────────────────────────────────────


def test_add_tag_applied(tmp_path: Path) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    _write_entity(repo, "I-insights", "growth-idea", "ins-001")

    inbox = _make_inbox(tmp_path)
    proposal = _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="reflex",
            action="add_tag",
            entity_id="ins-001",
            entity_type="insight",
            venture="venture-a",
            title="Tag it",
            diff={"add_tags": ["growth"]},
        ),
    )

    before = _commit_count(repo)
    results = apply_approved(inbox, {"venture-a": repo})

    assert len(results) == 1
    assert results[0].outcome == "applied"
    assert results[0].commit_sha

    # Tag landed in the file.
    entity = read_entity(repo / "I-insights" / "growth-idea.md", venture="venture-a")
    assert "growth" in entity.tags

    # Proposal status + provenance.
    reloaded = inbox.get(proposal.proposal_id)
    assert reloaded.status == ProposalStatus.APPLIED
    assert reloaded.applied_commit
    assert reloaded.applied_at is not None

    # A dream: commit exists.
    assert _commit_count(repo) == before + 1
    assert _last_message(repo).startswith("dream: add_tag ins-001")


@pytest.mark.parametrize("action", ["delete_entity", "modify_decision", "send_message"])
def test_hard_deny_actions_blocked(tmp_path: Path, action: str) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    path = _write_entity(repo, "I-insights", "thing", "ins-002")
    original = path.read_text(encoding="utf-8")

    inbox = _make_inbox(tmp_path)
    _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="curator",
            action=action,
            entity_id="ins-002",
            entity_type="insight",
            venture="venture-a",
            title="Dangerous",
            diff={"add_tags": ["x"]},
        ),
    )

    before = _commit_count(repo)
    results = apply_approved(inbox, {"venture-a": repo})

    assert results[0].outcome == "blocked"
    assert path.read_text(encoding="utf-8") == original  # untouched
    assert _commit_count(repo) == before  # NO commit


def test_foundations_target_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    path = _write_entity(repo, "F-foundations", "venture-identity", "found-001", entity_type="foundation")
    original = path.read_text(encoding="utf-8")

    inbox = _make_inbox(tmp_path)
    _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="reflex",
            action="add_tag",
            entity_id="found-001",
            entity_type="foundation",
            venture="venture-a",
            title="Tag foundation",
            diff={"add_tags": ["core"]},
        ),
    )

    before = _commit_count(repo)
    results = apply_approved(inbox, {"venture-a": repo})

    assert results[0].outcome == "blocked"
    assert "F-foundations" in results[0].reason or "protected" in results[0].reason
    assert path.read_text(encoding="utf-8") == original
    assert _commit_count(repo) == before


def test_committed_decision_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    path = _write_entity(
        repo,
        "I-insights",
        "pricing-decision",
        "dec-001",
        entity_type="decision",
        extra_fm="status: committed",
    )
    original = path.read_text(encoding="utf-8")

    inbox = _make_inbox(tmp_path)
    _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="reflex",
            action="add_tag",
            entity_id="dec-001",
            entity_type="decision",
            venture="venture-a",
            title="Tag decision",
            diff={"add_tags": ["pricing"]},
        ),
    )

    before = _commit_count(repo)
    results = apply_approved(inbox, {"venture-a": repo})

    assert results[0].outcome == "blocked"
    assert "committed" in results[0].reason
    assert path.read_text(encoding="utf-8") == original
    assert _commit_count(repo) == before


def test_dry_run_makes_no_changes(tmp_path: Path) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    path = _write_entity(repo, "I-insights", "idea", "ins-003")
    original = path.read_text(encoding="utf-8")

    inbox = _make_inbox(tmp_path)
    proposal = _seed_approved(
        inbox,
        DreamProposal(
            cycle_type="reflex",
            action="add_tag",
            entity_id="ins-003",
            entity_type="insight",
            venture="venture-a",
            title="Tag it",
            diff={"add_tags": ["growth"]},
        ),
    )

    before = _commit_count(repo)
    results = apply_approved(inbox, {"venture-a": repo}, dry_run=True)

    assert results[0].outcome == "applied"
    assert results[0].reason == "dry-run"
    assert path.read_text(encoding="utf-8") == original  # ZERO file changes
    assert _commit_count(repo) == before  # ZERO commits
    # Not marked applied in dry-run.
    assert inbox.get(proposal.proposal_id).status == ProposalStatus.APPROVED


def test_handler_failure_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "venture-a"
    _init_repo(repo)
    _write_entity(repo, "I-insights", "first", "ins-004")
    _write_entity(repo, "I-insights", "second", "ins-005")

    inbox = _make_inbox(tmp_path)
    _seed_approved(
        inbox,
        DreamProposal(
            proposal_id="dream-fails",
            cycle_type="reflex",
            action="add_tag",
            entity_id="ins-004",
            entity_type="insight",
            venture="venture-a",
            title="Will fail",
            diff={"add_tags": ["a"]},
        ),
    )
    _seed_approved(
        inbox,
        DreamProposal(
            proposal_id="dream-ok",
            cycle_type="reflex",
            action="add_tag",
            entity_id="ins-005",
            entity_type="insight",
            venture="venture-a",
            title="Will succeed",
            diff={"add_tags": ["b"]},
        ),
    )

    # Make update_entity raise ONLY for the first entity.
    import realize_core.dreaming.apply as apply_mod

    real_update = apply_mod.crud.update_entity

    def flaky_update(entity, updates=None, body=None, modified_by=""):
        if entity.id == "ins-004":
            raise RuntimeError("boom")
        return real_update(entity, updates, body=body, modified_by=modified_by)

    monkeypatch.setattr(apply_mod.crud, "update_entity", flaky_update)

    # Must not raise; both proposals processed.
    results = apply_approved(inbox, {"venture-a": repo})

    by_id = {r.proposal_id: r for r in results}
    assert by_id["dream-fails"].outcome == "failed"
    assert by_id["dream-ok"].outcome == "applied"
    assert by_id["dream-ok"].commit_sha
