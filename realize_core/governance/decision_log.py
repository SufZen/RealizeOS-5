"""Decision log: decisions as first-class FABRIC entities (STORY-44, Play A).

Every approval a person decides becomes a ``decision`` entity in the venture's
``B-brain/decisions/`` folder, linked to its approval row and to the sources it
relied on. Outside agents can propose a decision made elsewhere (a meeting, a
WhatsApp thread) with :func:`propose_decision`; it is recorded only when a
person approves it in the queue.

Writes are idempotent on the approval id, so retries never duplicate entries.
Counts come from the files that exist, never from estimates.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DECISIONS_DIR = Path("B-brain") / "decisions"

#: Action type of an approval item that proposes a decision made elsewhere.
DECISION_LOG_ACTION = "decision_log"

#: Approval items that are inputs, not decisions.
NOT_DECISIONS = frozenset({"skill_input", "agent_input", "agent_credential"})

MAX_TITLE_CHARS = 200
MAX_STATEMENT_CHARS = 5000


def _kb_path(kb_path: Path | str | None) -> Path:
    if kb_path is not None:
        return Path(kb_path)
    from realize_core.config import KB_PATH

    return KB_PATH


def decision_id(approval_id: str, when: datetime) -> str:
    """Stable entity id for the decision behind an approval."""
    short = re.sub(r"[^a-z0-9]", "", approval_id.lower())[:12] or "unknown"
    return f"dec-{when:%Y-%m}-approval-{short}"


def _clean_basis(basis: Any) -> list[dict[str, str]]:
    """Keep well-formed ``{source, locator}`` entries."""
    out: list[dict[str, str]] = []
    for item in basis if isinstance(basis, list) else []:
        if isinstance(item, dict) and item.get("source"):
            out.append({"source": str(item["source"])[:500], "locator": str(item.get("locator") or "")[:200]})
    return out


def _has_located_source(basis: list[dict[str, str]]) -> bool:
    return any(b.get("locator") for b in basis)


def _existing(venture_dir: Path, approval_id: str) -> Path | None:
    folder = venture_dir / DECISIONS_DIR
    if not folder.is_dir():
        return None
    short = re.sub(r"[^a-z0-9]", "", approval_id.lower())[:12]
    for path in folder.glob(f"dec-*-approval-{short}.md"):
        return path
    return None


def _params(record: dict) -> dict:
    import json

    raw = record.get("params_json") or record.get("params")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}


def record_approval_decision(
    record: dict, approve: bool, *, action_type: str | None = None, kb_path: Path | str | None = None
) -> Path | None:
    """Write the decision entity for a decided approval. Returns its path, or None.

    Skipped for inputs (answers, credentials) and for rejected decision
    proposals, which never happened. Idempotent on the approval id.
    """
    from realize_core.scaffold import find_venture_dir

    action_type = action_type or record.get("action_type") or ""
    if action_type in NOT_DECISIONS:
        return None
    if action_type == DECISION_LOG_ACTION and not approve:
        return None
    approval_id = str(record.get("id") or "")
    venture_dir = find_venture_dir(_kb_path(kb_path), record.get("venture_key") or "")
    if not approval_id or venture_dir is None:
        return None
    existing = _existing(venture_dir, approval_id)
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    params = _params(record)
    decided_by = record.get("decided_by") or "unknown"
    if action_type == DECISION_LOG_ACTION:
        title = str(params.get("title") or "Decision")[:MAX_TITLE_CHARS]
        statement = str(params.get("statement") or "")[:MAX_STATEMENT_CHARS]
        basis = _clean_basis(params.get("basis"))
        affects = [str(a) for a in params.get("affects") or []][:50]
        project = params.get("project")
        created_by = params.get("requested_by") or record.get("requested_by") or decided_by
        outcome = "recorded"
    else:
        action = record.get("action_name") or action_type or "request"
        verdict = "Approved" if approve else "Rejected"
        title = f"{verdict}: {action}"[:MAX_TITLE_CHARS]
        statement = str(record.get("decision_note") or "")[:MAX_STATEMENT_CHARS]
        basis = _clean_basis(params.get("basis") or params.get("sources"))
        affects = [str(a) for a in params.get("affects") or []][:50]
        project = params.get("project")
        created_by = decided_by
        outcome = "approved" if approve else "rejected"

    entity_id = decision_id(approval_id, now)
    frontmatter = {
        "id": entity_id,
        "type": "decision",
        "title": title,
        "status": "committed",
        "date": now.date().isoformat(),
        "kind": params.get("kind") or ("logged" if action_type == DECISION_LOG_ACTION else action_type or "approval"),
        "outcome": outcome,
        "approval_id": approval_id,
        "decided_by": decided_by,
        "channel": record.get("decision_channel") or record.get("channel"),
        "venture": record.get("venture_key"),
        "project": project,
        "basis": basis,
        "affects": affects,
        "source": "manual",
        "created_by": created_by,
        "created_at": now.isoformat(),
        "verified": _has_located_source(basis),
    }
    frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, [], "")}
    lines = [statement or f"{outcome.capitalize()} by {decided_by}."]
    if basis:
        lines.append("\n## Basis")
        lines.extend(f"- {b['source']}" + (f" ({b['locator']})" if b["locator"] else "") for b in basis)
    else:
        lines.append("\n_No source recorded for this decision._")
    path = venture_dir / DECISIONS_DIR / f"{entity_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    logger.info("Decision %s recorded for approval %s", entity_id, approval_id)
    return path


def propose_decision(
    venture_key: str,
    *,
    title: str,
    statement: str,
    basis: list[dict] | None = None,
    affects: list[str] | None = None,
    project: str | None = None,
    requested_by: str | None = None,
    db_path=None,
) -> str:
    """Queue a decision made elsewhere for a person to confirm. Returns the approval id."""
    from realize_core.governance.gates import create_approval_request

    clean = _clean_basis(basis)
    params = {
        "title": title[:MAX_TITLE_CHARS],
        "statement": statement[:MAX_STATEMENT_CHARS],
        "basis": clean,
        "affects": [str(a) for a in affects or []][:50],
        "project": project,
        "requested_by": requested_by,
    }
    payload = {
        "summary": f"Record decision: {params['title']}",
        "statement": params["statement"],
        "sources": len(clean),
        "warning": None
        if _has_located_source(clean)
        else "No source with a locator; it will be flagged as unverified.",
    }
    return create_approval_request(
        venture_key,
        "external_agent",
        DECISION_LOG_ACTION,
        payload,
        expires_minutes=7 * 24 * 60,
        db_path=db_path,
        params=params,
        requested_by=requested_by,
    )


def list_decisions(venture_dir: Path, *, since: datetime | None = None) -> list[dict]:
    """Decision entities in a venture, newest first."""
    folder = Path(venture_dir) / DECISIONS_DIR
    out: list[dict] = []
    if not folder.is_dir():
        return out
    for path in folder.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        try:
            meta = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError:
            continue
        if meta.get("type") != "decision":
            continue
        created = str(meta.get("created_at") or meta.get("date") or "")
        if since is not None:
            try:
                when = datetime.fromisoformat(created)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
            except ValueError:
                continue
            if when < since:
                continue
        out.append({**meta, "_path": path, "_body": text[end + 4 :].strip()})
    return sorted(out, key=lambda d: str(d.get("created_at") or d.get("date") or ""), reverse=True)


def weekly_counts(venture_dir: Path, *, days: int = 7) -> dict[str, int]:
    """Decisions recorded in the last ``days`` and how many lack a located source."""
    recent = list_decisions(venture_dir, since=datetime.now(UTC) - timedelta(days=days))
    return {"recorded": len(recent), "without_source": sum(1 for d in recent if not d.get("verified"))}


_LABELS = {
    "en": {
        "title": "Decision log",
        "date": "Date",
        "decision": "Decision",
        "by": "Decided by",
        "basis": "Basis",
        "none": "No source",
    },
    "he": {
        "title": "יומן החלטות",
        "date": "תאריך",
        "decision": "החלטה",
        "by": "החליט/ה",
        "basis": "מקור",
        "none": "אין מקור",
    },
    "pt": {
        "title": "Registo de decisões",
        "date": "Data",
        "decision": "Decisão",
        "by": "Decidido por",
        "basis": "Fonte",
        "none": "Sem fonte",
    },
}


def export_markdown(venture_dir: Path, *, language: str = "en", project: str | None = None) -> str:
    """The decision log as a finished-document-ready markdown table in he, en or pt."""
    labels = _LABELS.get(language, _LABELS["en"])
    rows = [d for d in list_decisions(venture_dir) if project is None or d.get("project") == project]
    lines = [
        f"# {labels['title']}",
        "",
        f"| {labels['date']} | {labels['decision']} | {labels['by']} | {labels['basis']} |",
        "|---|---|---|---|",
    ]
    for d in rows:
        basis = d.get("basis") or []
        cited = "; ".join(f"{b.get('source')} {b.get('locator') or ''}".strip() for b in basis) or labels["none"]
        title = str(d.get("title", "")).replace("|", "\\|")
        lines.append(f"| {d.get('date', '')} | {title} | {d.get('decided_by', '')} | {cited.replace('|', '/')} |")
    return "\n".join(lines) + "\n"
