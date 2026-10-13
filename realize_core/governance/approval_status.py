"""
Effective status of approval items (Codex audit N11).

Nothing rewrites a lapsed item: a pending row past its ``expires_at`` stays
``pending`` in the table, and every decision path already refuses it
(:func:`realize_core.governance.gates._decide` checks the expiry in the same
UPDATE that decides). Readers apply the same rule here, so a list never offers
an item that no one can decide any more:

- ``pending`` means *still decidable*: stored as pending and not past ``expires_at``.
- ``expired`` covers stored ``expired`` rows and pending rows that lapsed.

Listed rows report this effective ``status`` and carry an ``expired`` flag.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

#: Stored statuses that mean a person (or the clock) already settled the item.
DECIDED_STATUSES = frozenset({"approved", "rejected", "answered"})


def now_stamp() -> str:
    """The current time in the ``approval_queue`` stamp format (stamps sort as text)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def is_lapsed(row: dict[str, Any], now: str) -> bool:
    """True for a pending item whose ``expires_at`` has passed (it can't be decided)."""
    expires_at = row.get("expires_at")
    return row.get("status") == "pending" and bool(expires_at) and str(expires_at) <= now


def with_effective_status(row: dict[str, Any], now: str) -> dict[str, Any]:
    """The row as a list shows it: a lapsed pending item becomes ``expired``.

    Adds ``expired`` (bool) to every row; the stored row is not changed.
    """
    view = dict(row)
    if is_lapsed(row, now):
        view["status"] = "expired"
    view["expired"] = view.get("status") == "expired"
    return view


def status_clause(status: str, now: str) -> tuple[str, list[str]]:
    """SQL condition and parameters that select items by effective status.

    Args:
        status: ``pending`` (still decidable), ``expired`` (stored or lapsed),
            or any stored status, matched as is.
        now: Current stamp from :func:`now_stamp`.
    """
    if status == "pending":
        return "(status = 'pending' AND (expires_at IS NULL OR expires_at > ?))", [now]
    if status == "expired":
        return (
            "(status = 'expired' OR (status = 'pending' AND expires_at IS NOT NULL AND expires_at <= ?))",
            [now],
        )
    return "status = ?", [status]


def decision_refusal(row: dict[str, Any], now: str) -> tuple[str, str]:
    """Why an existing item could not be decided: ``(reason, message)``.

    ``reason`` is ``expired``, ``already_decided`` or ``not_pending``; the
    message is plain language for the person who tried.
    """
    view = with_effective_status(row, now)
    status = view.get("status")
    if view["expired"]:
        return "expired", "This request expired before anyone decided it, so nothing was done."
    if status in DECIDED_STATUSES:
        who = row.get("decided_by")
        by = f" by {who}" if who else ""
        return "already_decided", f"This request was already {status}{by}. Your decision was not applied."
    return "not_pending", "This request can no longer be decided."


#: Decision fields a refused decision returns, so the client can show the item's real state.
DECISION_FIELDS = (
    "id",
    "status",
    "expired",
    "expires_at",
    "decided_at",
    "decided_by",
    "decision_channel",
    "decision_note",
    "executed_at",
    "execution_status",
    "result_json",
    "error",
)


def decision_summary(row: dict[str, Any], now: str) -> dict[str, Any]:
    """The item's current decision state (effective status), for a refused decision."""
    view = with_effective_status(row, now)
    return {key: view.get(key) for key in DECISION_FIELDS}
