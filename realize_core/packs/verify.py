"""Raise a pack's verification level through an approval (spec 010 §5, §9.4).

- Level 2 (reviewed): any named local professional; the owner approves the request.
- Level 3 (maintained): only with a partner maintenance agreement named in the request.
- Level 4 (field-proven): never through this path; it comes from a paid engagement.

The approval is a normal queue item (``action_type: pack_verify``). A pack is
shared by every venture that uses it, so only a global pack maintainer (the
owner, not limited to some ventures, never an outside agent) may approve or
reject it (audit N01; enforced in
:func:`realize_core.governance.gates.decide_approval`).

When it is approved, :func:`apply_verification` records the reviewer, the
date, the new level, the next review date and a fingerprint of each approved
card's content, for the reviewed cards or for the whole pack, in the
verification state under ``DATA_PATH`` (:mod:`realize_core.packs.state`), in
one atomic write. Pack files are never edited by an approval, so shipped packs
can stay read-only (audit N04). Nothing changes on rejection.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from realize_core.packs import loader as _loader
from realize_core.packs import state
from realize_core.packs.models import VERIFICATION_NAMES, Pack

logger = logging.getLogger(__name__)

PACK_VERIFY_ACTION = "pack_verify"
ALLOWED_LEVELS = (2, 3)


class PackVerificationError(ValueError):
    """A verification request that the rules don't allow."""


def _installed(kind: str, pack_id: str, packs_root: Path | None) -> Pack:
    pack = _loader.find_pack(kind, pack_id, packs_root) if kind in _loader.PACK_KINDS else None
    if pack is None:
        raise PackVerificationError(f"Pack {kind}/{pack_id} is not installed")
    return pack


def validate_request(level: int, reviewer: str, partner_agreement: str | None) -> None:
    """Check a verification request against the rules in spec 010 §9.4."""
    if level not in ALLOWED_LEVELS:
        raise PackVerificationError("Only levels 2 and 3 can be granted by approval; level 4 comes from paid work")
    if not reviewer.strip():
        raise PackVerificationError("A named reviewer is required")
    if level == 3 and not (partner_agreement or "").strip():
        raise PackVerificationError("Level 3 needs a partner maintenance agreement")


def request_verification(
    venture_key: str,
    *,
    kind: str,
    pack_id: str,
    level: int,
    reviewer: str,
    cards: list[str] | None = None,
    corrections: dict[str, int] | None = None,
    partner_agreement: str | None = None,
    note: str = "",
    requested_by: str | None = None,
    packs_root: Path | None = None,
    db_path=None,
) -> str:
    """Queue a verification for approval. Returns the approval id."""
    from realize_core.governance.gates import create_approval_request

    validate_request(level, reviewer, partner_agreement)
    _installed(kind, pack_id, packs_root)
    params = {
        "kind": kind,
        "pack_id": pack_id,
        "level": level,
        "reviewer": reviewer,
        "cards": list(cards or []),
        "corrections": dict(corrections or {}),
        "partner_agreement": partner_agreement,
        "note": note,
    }
    payload = {
        "summary": f"Raise {kind}/{pack_id} to verification {level}",
        "reviewer": reviewer,
        "cards": len(params["cards"]) or "all",
    }
    return create_approval_request(
        venture_key,
        "pack_maintainer",
        PACK_VERIFY_ACTION,
        payload,
        expires_minutes=14 * 24 * 60,
        db_path=db_path,
        params=params,
        requested_by=requested_by,
    )


def _as_level(value: Any) -> int:
    if isinstance(value, bool):
        raise PackVerificationError(f"Verification level '{value}' is not a whole number")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PackVerificationError(f"Verification level '{value}' is not a whole number") from exc


def apply_verification(
    params: dict, approved_by: str, *, approval_id: str | None = None, packs_root: Path | None = None
) -> dict[str, Any]:
    """Record an approved verification. Returns what changed.

    The reviewer, the date and the level go to the verification state under
    ``DATA_PATH`` in one atomic write: for the listed ``cards`` only (the
    pack's own level stays as it was), or with no ``cards`` for the whole pack
    and every card in it. The pack's files are not touched. Each card also
    gets its next review date (today plus the pack's review interval, six
    months unless ``pack.yaml`` sets ``verification.review_interval_months``)
    and a fingerprint of the content approved, so a later edit to the card
    drops it back to its file's level.

    Returns:
        ``{"pack", "level", "reviewer", "cards", "skipped", "pack_level_changed", "review_by"}``.
        ``skipped`` lists requested cards the pack no longer has.

    Raises:
        PackVerificationError: The request breaks the rules, or the pack or
            every requested card is gone.
        realize_core.packs.state.VerificationStateError: The state can't be
            written (nothing was recorded then).
    """
    level = _as_level(params.get("level", 0))
    reviewer = str(params.get("reviewer") or "").strip()
    partner_agreement = params.get("partner_agreement")
    validate_request(level, reviewer, partner_agreement)
    kind, pack_id = str(params.get("kind") or ""), str(params.get("pack_id") or "")
    pack = _installed(kind, pack_id, packs_root)

    requested = params.get("cards") or []
    if not isinstance(requested, list):
        raise PackVerificationError("cards must be a list of rule card ids")
    wanted = {str(c) for c in requested}
    if wanted:
        cards = sorted(wanted & set(pack.rules))
        skipped = sorted(wanted - set(pack.rules))
        if not cards:
            raise PackVerificationError(f"None of the requested cards are in {kind}/{pack_id}: {', '.join(skipped)}")
    else:
        cards, skipped = sorted(pack.rules), []
    corrections = params.get("corrections")
    today = datetime.now(UTC).date()
    review_by = state.add_months(today, state.review_interval_months(pack)).isoformat()
    state.record_verification(
        kind,
        pack.id,
        version=pack.version,
        level=level,
        reviewer=reviewer,
        approved_by=approved_by,
        approval_id=approval_id,
        cards=cards,
        whole_pack=not wanted,
        partner_agreement=str(partner_agreement) if level == 3 else None,
        corrections=corrections if isinstance(corrections, dict) else None,
        today=today.isoformat(),
        review_by=review_by,
        fingerprints={card_id: state.card_fingerprint(pack.rules[card_id]) for card_id in cards},
    )
    logger.info("Pack %s/%s verification %s applied to %d cards", kind, pack_id, level, len(cards))
    return {
        "pack": f"{kind}/{pack.id}",
        "level": level,
        "reviewer": reviewer,
        "cards": cards,
        "skipped": skipped,
        "pack_level_changed": not wanted,
        "review_by": review_by,
    }


def describe_result(result: dict[str, Any]) -> str:
    """One line for the approval: what an applied verification changed."""
    level = result.get("level")
    name = VERIFICATION_NAMES.get(level, "?") if isinstance(level, int) else "?"
    cards = result.get("cards") or []
    if result.get("pack_level_changed"):
        text = f"{result.get('pack')} and its {len(cards)} rule cards raised to verification {level} ({name})"
    else:
        text = f"{len(cards)} rule card(s) of {result.get('pack')} raised to verification {level} ({name}): "
        text += ", ".join(cards)
    text += f"; reviewed by {result.get('reviewer')}."
    if result.get("review_by"):
        text += f" Next review by {result['review_by']}."
    if result.get("skipped"):
        text += f" Not in the pack any more, so skipped: {', '.join(result['skipped'])}."
    return text
