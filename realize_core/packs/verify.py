"""Raise a pack's verification level through an approval (spec 010 §5, §9.4).

- Level 2 (reviewed): any named local professional; the owner approves the request.
- Level 3 (maintained): only with a partner maintenance agreement named in the request.
- Level 4 (field-proven): never through this path; it comes from a paid engagement.

The approval is a normal queue item (``action_type: pack_verify``). When a
person approves it, :func:`apply_verification` writes the reviewer and date to
the pack manifest and to the reviewed rule cards. Nothing changes on rejection.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from realize_core.packs import loader as _loader

logger = logging.getLogger(__name__)

PACK_VERIFY_ACTION = "pack_verify"
ALLOWED_LEVELS = (2, 3)


class PackVerificationError(ValueError):
    """A verification request that the rules don't allow."""


def _pack_dir(kind: str, pack_id: str, packs_root: Path | None) -> Path:
    root = packs_root or _loader.default_packs_root()
    for child in (root / kind).iterdir() if (root / kind).is_dir() else []:
        if child.is_dir() and child.name == pack_id:
            return child
    raise PackVerificationError(f"Pack {kind}/{pack_id} is not installed")


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
    _pack_dir(kind, pack_id, packs_root)
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


def _rewrite_card(path: Path, level: int, reviewer: str, today: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    meta = yaml.safe_load(text[3:end]) or {}
    meta["verification"] = level
    meta["verified_by"] = reviewer
    meta["reviewed_at"] = today
    path.write_text(
        "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100) + text[end:], encoding="utf-8"
    )
    return True


def apply_verification(params: dict, approved_by: str, *, packs_root: Path | None = None) -> dict:
    """Write an approved verification to the pack. Returns what changed."""
    level = int(params.get("level", 0))
    reviewer = str(params.get("reviewer") or "")
    validate_request(level, reviewer, params.get("partner_agreement"))
    pack_dir = _pack_dir(str(params.get("kind")), str(params.get("pack_id")), packs_root)
    today = datetime.now(UTC).date().isoformat()
    wanted = set(params.get("cards") or [])

    updated: list[str] = []
    for card_path in sorted((pack_dir / "rules").glob("*.md")):
        card = _loader.load_rule_card(card_path, [])
        if card and (not wanted or card.id in wanted) and _rewrite_card(card_path, level, reviewer, today):
            updated.append(card.id)

    manifest_path = pack_dir / "pack.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not wanted:  # the whole pack was reviewed
        verification = dict(manifest.get("verification") or {})
        verification.update({"level": level, "reviewed_by": reviewer, "reviewed_at": today, "approved_by": approved_by})
        if level == 3:
            verification["partner_agreement"] = params.get("partner_agreement")
        if params.get("corrections"):
            verification["corrections"] = params["corrections"]
        manifest["verification"] = verification
        manifest_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
        )
    logger.info(
        "Pack %s/%s verification %s applied to %d cards", params.get("kind"), params.get("pack_id"), level, len(updated)
    )
    return {"cards": updated, "pack_level_changed": not wanted, "level": level}
