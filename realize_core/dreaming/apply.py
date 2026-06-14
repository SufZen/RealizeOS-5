"""
Apply-loop — write approved Dream proposals back into FABRIC.

This closes the Dreaming loop (US1 of feature 004): approved proposals are
written to the FABRIC markdown files via :mod:`realize_core.fabric.crud`, the
change is recorded as a reversible ``dream:`` git commit, the proposal is
marked ``applied`` with the commit SHA, and an event is logged.

SAFETY-CRITICAL. This module enforces an INDEPENDENT hard-deny guard at apply
time — separate from (and in addition to) the trust policy that gates proposal
submission. Even an ``approved`` proposal is blocked when:

- its ``action`` is on the fixed hard-deny set (delete/modify-decision/send),
- its target file lives under ``F-foundations/`` (or is the ``A-agents`` README),
- its target is a ``decision`` entity whose frontmatter ``status == "committed"``.

Every proposal is processed under its own ``try``/``except`` so a single
failure (``outcome="failed"``) never aborts the batch and never raises.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from realize_core.dreaming.policy import DreamProposal
from realize_core.fabric import crud
from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.event_log import EventLog
from realize_core.fabric.event_types import dream_event

logger = logging.getLogger(__name__)


# ── Hard-deny guard constants (FIXED — enforced regardless of policy/status) ──

# Actions that may NEVER be applied by the loop, no matter what.
HARD_DENY_ACTIONS: frozenset[str] = frozenset(
    {
        "delete_entity",
        "modify_decision",
        "send_message",
    }
)

# v1 safe, reversible action set the apply-loop knows how to write.
SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {
        "add_tag",
        "add_ref",
        "annotate_entity",
        "update_summary",
        "flag_stale_commitment",
        "flag_orphan",
    }
)

# Path fragments that mark a protected FABRIC layer/file. A target whose file
# path contains any of these (case-insensitive, path-segment aware) is blocked.
_PROTECTED_PATH_SEGMENTS: tuple[str, ...] = ("F-foundations",)
_PROTECTED_PATH_SUFFIXES: tuple[str, ...] = ("A-agents/_README",)

_APPLIED_BY = "dream-apply"


@dataclass
class ApplyResult:
    """Per-proposal outcome of the apply-loop."""

    proposal_id: str
    outcome: str  # "applied" | "skipped" | "blocked" | "failed"
    reason: str = ""
    commit_sha: str = ""


# ── Hard-deny guard ──────────────────────────────────────────────────────────


def _path_is_protected(path: Path | None) -> bool:
    """True if the file path is under a protected FABRIC layer/file."""
    if path is None:
        return False
    # Normalise to forward slashes for cross-platform, segment-aware matching.
    parts = [p for p in path.parts if p not in ("", ".", "/", "\\")]
    lowered = [p.lower() for p in parts]
    for seg in _PROTECTED_PATH_SEGMENTS:
        if seg.lower() in lowered:
            return True
    posix = "/".join(parts).lower()
    return any(suffix.lower() in posix for suffix in _PROTECTED_PATH_SUFFIXES)


def _hard_deny_reason(proposal: DreamProposal, entity: FabricEntity | None) -> str:
    """
    Return a non-empty block reason if the proposal must be hard-denied.

    Checked INDEPENDENTLY of trust policy and proposal status. The action check
    works without an entity (so it fires even when the target cannot be found);
    the path/decision checks require the located entity.
    """
    if proposal.action in HARD_DENY_ACTIONS:
        return f"hard-deny action: {proposal.action}"

    if entity is not None:
        if _path_is_protected(entity.path):
            return "protected target (F-foundations / A-agents README)"
        if entity.type == "decision":
            status = str(entity.frontmatter.get("status", "")).strip().lower()
            if status == "committed":
                return "committed decision is immutable"

    return ""


# ── Entity location ──────────────────────────────────────────────────────────


def _locate_entity(
    proposal: DreamProposal,
    venture_dirs: dict[str, Path],
) -> FabricEntity | None:
    """
    Find the FABRIC entity targeted by a proposal.

    Resolution order:
    1. An explicit file path in ``proposal.diff["path"]`` (read directly).
    2. Scan the proposal's venture dir and match ``entity.id == entity_id``.

    Returns ``None`` when the entity cannot be found.
    """
    diff = proposal.diff or {}
    explicit = diff.get("path")
    if explicit:
        candidate = Path(explicit)
        if candidate.exists():
            return crud.read_entity(candidate, venture=proposal.venture)

    venture_dir = venture_dirs.get(proposal.venture)
    if venture_dir is None:
        return None

    if not proposal.entity_id:
        return None

    for entity in crud.scan_venture(venture_dir, venture=proposal.venture):
        if entity.id == proposal.entity_id:
            return entity
    return None


# ── Per-action change computation ────────────────────────────────────────────


def _compute_updates(proposal: DreamProposal, entity: FabricEntity) -> dict:
    """
    Compute the frontmatter ``updates`` dict for a supported action.

    Returns the dict to hand to :func:`crud.update_entity`. An empty dict means
    "nothing to write" — the caller treats that as a skip.
    """
    action = proposal.action
    diff = proposal.diff or {}

    if action == "add_tag":
        add = [str(t).strip().lower() for t in diff.get("add_tags", []) if str(t).strip()]
        if not add:
            return {}
        merged = sorted(set(entity.tags) | set(add))
        if merged == sorted(set(entity.tags)):
            return {}
        return {"tags": merged}

    if action == "add_ref":
        add = [str(r).strip() for r in diff.get("add_refs", []) if str(r).strip()]
        if not add:
            return {}
        existing = list(entity.frontmatter.get("refs", entity.refs) or [])
        merged = list(dict.fromkeys([*existing, *add]))  # order-preserving dedup
        if merged == list(existing):
            return {}
        return {"refs": merged}

    if action == "update_summary":
        summary = diff.get("summary", diff.get("suggested_value", ""))
        if not summary:
            return {}
        return {"summary": summary}

    if action == "annotate_entity":
        # Curator emits an empty diff (untagged hint); Reflex suggests a field.
        field = diff.get("suggest_field")
        if field:
            value = diff.get("suggested_value", "")
            # Never silently overwrite an existing value.
            if field in entity.frontmatter and entity.frontmatter.get(field):
                return {}
            return {field: value}
        note = diff.get("note") or proposal.description
        if not note:
            return {}
        return {"dream_note": note}

    if action == "flag_stale_commitment":
        return {"stale_commitment": True}

    if action == "flag_orphan":
        return {"orphan": True}

    return {}


# ── Git commit ───────────────────────────────────────────────────────────────


def _git_commit_file(repo_dir: Path, file_path: Path, message: str) -> str:
    """
    Stage and commit a single file in ``repo_dir``'s git repository.

    Returns the resulting commit SHA. Raises on git failure so the caller marks
    the proposal ``failed`` (the FABRIC write already happened, but it is NOT
    marked applied without a recorded, reversible commit).
    """
    try:
        rel = str(file_path.relative_to(repo_dir))
    except ValueError:
        rel = str(file_path)

    subprocess.run(
        ["git", "add", "--", rel],
        cwd=str(repo_dir),
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message, "--", rel],
        cwd=str(repo_dir),
        capture_output=True,
        check=True,
        text=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        check=True,
        text=True,
    )
    return sha.stdout.strip()


# ── Event logging ────────────────────────────────────────────────────────────


def _log(event_log: EventLog | None, result: ApplyResult, proposal: DreamProposal) -> None:
    """Append an apply event for the given outcome (best-effort)."""
    if event_log is None:
        return
    try:
        event_log.append(
            dream_event(
                action=f"apply_{result.outcome}",
                cycle_type=proposal.cycle_type,
                venture=proposal.venture,
                proposal_id=proposal.proposal_id,
                action_type=proposal.action,
                entity_id=proposal.entity_id,
                reason=result.reason,
                commit_sha=result.commit_sha,
            )
        )
    except Exception as exc:  # logging must never break the loop
        logger.debug("Failed to log apply event for %s: %s", proposal.proposal_id, exc)


# ── Public entry point ───────────────────────────────────────────────────────


def apply_approved(
    inbox,
    venture_dirs: dict[str, Path],
    dry_run: bool = False,
    event_log: EventLog | None = None,
    urgent_recipient: str = "",
) -> list[ApplyResult]:
    """
    Apply all approved proposals in ``inbox`` to FABRIC.

    Args:
        inbox: A ``DreamInbox`` exposing ``approved()`` and ``mark_applied()``.
        venture_dirs: Map of venture key → venture root directory (a git repo).
        dry_run: When True, compute intended writes but make ZERO file changes
            and ZERO commits; supported writes report ``outcome="applied"`` with
            ``reason="dry-run"``.
        event_log: Optional event log for per-outcome audit events.
        urgent_recipient: When non-empty (and NOT a dry-run), an immediate
            urgent alert email is sent for every ``blocked`` outcome — a
            hard-denied action that was nonetheless marked approved (a forbidden
            write was attempted). Blocked items never appear in the morning
            digest, so this is the only notification for them. When empty
            (default), behavior is byte-for-byte unchanged.

    Returns:
        One :class:`ApplyResult` per approved proposal. Never raises — each
        proposal is isolated under its own ``try``/``except``.
    """
    results: list[ApplyResult] = []

    for proposal in inbox.approved():
        try:
            result = _apply_one(proposal, venture_dirs, dry_run=dry_run, inbox=inbox)
        except Exception as exc:  # belt-and-suspenders: one failure never aborts batch
            logger.error("Apply failed for %s: %s", proposal.proposal_id, exc, exc_info=True)
            result = ApplyResult(proposal.proposal_id, "failed", reason=str(exc)[:200])
        _log(event_log, result, proposal)

        # Immediate urgent alert for a forbidden write that was attempted. Guarded
        # so alert failures can never affect the apply loop or raise. Dry-runs do
        # not alert (no write was actually attempted).
        if result.outcome == "blocked" and urgent_recipient and not dry_run:
            _send_block_alert(urgent_recipient, result, proposal, event_log)

        results.append(result)

    return results


def _send_block_alert(
    urgent_recipient: str,
    result: ApplyResult,
    proposal: DreamProposal,
    event_log: EventLog | None,
) -> None:
    """Send an immediate urgent alert for a blocked (hard-denied) proposal.

    Fully guarded: any failure here is logged and swallowed so the apply loop
    is never affected and never raises.
    """
    try:
        import asyncio

        # Lazy import to avoid a hard dependency / import cycle on the channels
        # package (and its optional google libs) at module load time.
        from realize_core.channels.email import send_urgent_alert

        subject = f"[RealizeOS URGENT] Blocked forbidden write: {proposal.action or '?'}"
        body = (
            "The Dreaming apply-loop BLOCKED an approved proposal because it "
            "attempted a hard-denied action (a forbidden write).\n\n"
            f"  proposal: {proposal.proposal_id}\n"
            f"  action:   {proposal.action or '?'}\n"
            f"  venture:  {proposal.venture or '(no venture)'}\n"
            f"  entity:   {proposal.entity_id or '(none)'}\n"
            f"  reason:   {result.reason or '(no reason given)'}\n\n"
            "No change was written. Review the Dream Inbox to investigate how an "
            "approved proposal carried a hard-denied action."
        )
        asyncio.run(
            send_urgent_alert(
                recipient=urgent_recipient,
                subject=subject,
                body=body,
                event_log=event_log,
            )
        )
    except Exception as exc:  # alerting must never affect the apply loop
        logger.error(
            "Urgent alert dispatch failed for blocked proposal %s: %s",
            proposal.proposal_id,
            exc,
            exc_info=True,
        )


def _apply_one(
    proposal: DreamProposal,
    venture_dirs: dict[str, Path],
    dry_run: bool,
    inbox,
) -> ApplyResult:
    """Apply a single approved proposal. Helper for :func:`apply_approved`."""
    pid = proposal.proposal_id

    # 1. Action-level hard-deny — fires WITHOUT needing to locate the entity.
    action_block = _hard_deny_reason(proposal, entity=None)
    if action_block:
        logger.warning("Blocked proposal %s: %s", pid, action_block)
        return ApplyResult(pid, "blocked", reason=action_block)

    # 2. Unsupported actions are skipped (left for a later increment).
    if proposal.action not in SUPPORTED_ACTIONS:
        return ApplyResult(pid, "skipped", reason="unsupported action (v1)")

    # 3. Locate the target entity.
    entity = _locate_entity(proposal, venture_dirs)
    if entity is None:
        return ApplyResult(pid, "skipped", reason="target entity not found")

    # 4. Entity-level hard-deny (protected path / committed decision).
    target_block = _hard_deny_reason(proposal, entity=entity)
    if target_block:
        logger.warning("Blocked proposal %s: %s", pid, target_block)
        return ApplyResult(pid, "blocked", reason=target_block)

    # 5. Compute the change.
    updates = _compute_updates(proposal, entity)
    if not updates:
        return ApplyResult(pid, "skipped", reason="no-op (nothing to write)")

    # 6. Dry-run: report intent, write nothing.
    if dry_run:
        return ApplyResult(pid, "applied", reason="dry-run")

    # 7. Write to FABRIC.
    crud.update_entity(entity, updates, modified_by=_APPLIED_BY)

    # 8. Commit the single file (reversible). A commit failure -> "failed".
    venture_dir = venture_dirs.get(proposal.venture)
    repo_dir = venture_dir if venture_dir is not None else (entity.path.parent if entity.path else None)
    if repo_dir is None or entity.path is None:
        return ApplyResult(pid, "failed", reason="no repo/path to commit")

    message = f"dream: {proposal.action} {proposal.entity_id} ({pid})"
    try:
        commit_sha = _git_commit_file(repo_dir, entity.path, message)
    except Exception as exc:
        logger.error("Git commit failed for %s: %s", pid, exc)
        return ApplyResult(pid, "failed", reason=f"git commit failed: {str(exc)[:160]}")

    # 9. Mark applied via the public inbox API.
    inbox.mark_applied(pid, commit_sha=commit_sha)

    return ApplyResult(pid, "applied", commit_sha=commit_sha)
