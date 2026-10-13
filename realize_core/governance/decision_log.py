"""Decision log: decisions as first-class FABRIC entities (STORY-44, Play A).

Every approval a person decides becomes a ``decision`` entity in the venture's
``B-brain/decisions/`` folder, linked to its approval row and to the sources it
relied on. Outside agents can propose a decision made elsewhere (a meeting, a
WhatsApp thread) with :func:`propose_decision`; it is recorded only when a
person approves it in the queue.

Writes are idempotent on the approval id, so retries never duplicate entries.
Counts come from the files that exist, never from estimates.

Writes are durable (Codex audit N05): the intent is stored in
``decision_writes`` (migration 013) in the same transaction that records the
decision (:func:`queue_with_decision`), so a crash right after a decision
can't lose its entry; :func:`log_decision` then writes the file and marks the
intent done. A write that fails (disk full, read-only mount, venture folder
missing) stays pending and is retried at startup, after the next decision that
is logged, and by ``realize-os decisions retry``.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
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

#: Pending decision writes retried in one pass, so a retry stays cheap.
RETRY_BATCH = 50

#: Automatic retries (startup, after a decision) stop after this many failed
#: attempts, so a venture whose folder is gone doesn't slow every approval.
#: ``realize-os decisions retry`` still tries every pending write.
MAX_AUTO_ATTEMPTS = 5

#: Durable decision-write intents (migration 013). One row per approval.
DDL = """
CREATE TABLE IF NOT EXISTS decision_writes (
    approval_id  TEXT PRIMARY KEY,
    venture_key  TEXT NOT NULL DEFAULT '',
    approve      INTEGER NOT NULL,
    action_type  TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    decision_id  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_writes_status ON decision_writes(status, created_at);
"""


class DecisionLogError(Exception):
    """The decision can't be written yet (for example its venture folder isn't there)."""


def _kb_path(kb_path: Path | str | None) -> Path:
    if kb_path is not None:
        return Path(kb_path)
    from realize_core.config import KB_PATH

    return KB_PATH


def is_decision(action_type: str | None, approve: bool) -> bool:
    """Whether a decided approval belongs in the decision log.

    Inputs (answers, credentials) are not decisions, and a rejected decision
    proposal never happened.
    """
    if (action_type or "") in NOT_DECISIONS:
        return False
    return not (action_type == DECISION_LOG_ACTION and not approve)


def decision_venture_dir(
    venture_key: str, *, kb_path: Path | str | None = None, config: dict | None = None
) -> Path | None:
    """The venture folder decisions go to, from the configured key → directory mapping.

    Reads the venture's ``systems:`` entry in realize-os.yaml (``config``, or
    the loaded config), so a ``directory`` that differs from the key is
    honoured. Without an entry the folder is matched by name. Never returns a
    folder outside ``systems/`` or ``ventures/``.

    Returns:
        The folder, or None when the venture has none on disk.

    Raises:
        DecisionLogError: the configured directory is outside ``systems/`` or ``ventures/``.
    """
    from realize_core.scaffold import UnsafeVentureDirError, resolve_venture_dir

    if not venture_key:
        return None
    if config is None:
        from realize_core.config import load_config

        config = load_config()
    systems = config.get("systems") if isinstance(config, dict) else None
    entry = next(
        (s for s in systems or [] if isinstance(s, dict) and s.get("key") == venture_key),
        None,
    )
    try:
        return resolve_venture_dir(_kb_path(kb_path), venture_key, entry)
    except UnsafeVentureDirError as exc:
        raise DecisionLogError(
            f"Venture '{venture_key}' is configured with a directory outside systems/ or ventures/"
        ) from exc


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


def _decided_at(record: dict) -> datetime:
    """When the decision was made (the approval's ``decided_at``), so a retried write keeps its date."""
    raw = record.get("decided_at")
    if isinstance(raw, str) and raw:
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            when = None
        if when is not None:
            return when if when.tzinfo else when.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _write_atomically(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temporary file, so a failed write never leaves a partial entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove temporary decision file %s", tmp, exc_info=True)
        raise


def record_approval_decision(
    record: dict,
    approve: bool,
    *,
    action_type: str | None = None,
    kb_path: Path | str | None = None,
    config: dict | None = None,
) -> Path | None:
    """Write the decision entity for a decided approval. Returns its path, or None.

    Skipped for inputs (answers, credentials) and for rejected decision
    proposals, which never happened, and when the venture has no folder.
    Idempotent on the approval id. Use :func:`log_decision` for a write that
    is retried after a failure.

    Raises:
        OSError: the file could not be written.
    """
    action_type = action_type or record.get("action_type") or ""
    if not is_decision(action_type, approve):
        return None
    try:
        return _write_decision(record, approve, action_type, kb_path=kb_path, config=config)
    except DecisionLogError as exc:
        logger.warning("Decision for approval %s not recorded: %s", record.get("id"), exc)
        return None


def _write_decision(
    record: dict,
    approve: bool,
    action_type: str,
    *,
    kb_path: Path | str | None = None,
    config: dict | None = None,
) -> Path:
    """Write (or find) the decision file for a decided approval.

    Raises:
        DecisionLogError: no approval id, or no usable venture folder.
        OSError: the file could not be written.
    """
    approval_id = str(record.get("id") or "")
    if not approval_id:
        raise DecisionLogError("The approval has no id")
    venture_key = record.get("venture_key") or ""
    venture_dir = decision_venture_dir(venture_key, kb_path=kb_path, config=config)
    if venture_dir is None:
        raise DecisionLogError(f"Venture '{venture_key}' has no folder for its decision log")
    existing = _existing(venture_dir, approval_id)
    if existing is not None:
        return existing

    now = _decided_at(record)
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
    _write_atomically(
        path,
        "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + "\n".join(lines) + "\n",
    )
    logger.info("Decision %s recorded for approval %s", entity_id, approval_id)
    return path


# ---------------------------------------------------------------------------
# Durable writes (Codex audit N05)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _connect(db_path=None) -> sqlite3.Connection:
    from realize_core.db.schema import get_connection

    conn = get_connection(db_path)
    conn.executescript(DDL)
    return conn


#: What can go wrong writing one decision file (anything else is a bug and is raised).
_WRITE_ERRORS = (DecisionLogError, OSError, ValueError, yaml.YAMLError)


def _outcome(logged: bool, error: str | None = None, *, pending: bool = False, decision: str | None = None) -> dict:
    """What a caller (and the approval API) learns about a decision-log write."""
    return {"logged": logged, "pending": pending, "error": error, "decision_id": decision}


def _public_error(exc: Exception) -> str:
    """A short reason for the API, without server paths (the full error is logged and stored)."""
    if isinstance(exc, OSError):
        return exc.strerror or type(exc).__name__
    return str(exc) or type(exc).__name__


def log_decision(
    record: dict,
    approve: bool,
    *,
    action_type: str | None = None,
    kb_path: Path | str | None = None,
    db_path=None,
    retry_others: bool = True,
) -> dict:
    """Record a decided approval in the decision log, durably. Never raises.

    The intent is stored first; the file is written; the intent is marked
    done. A failed write stays pending and is retried later
    (:func:`retry_pending_decisions`), and never produces a second entry.
    After a successful write, other pending writes are retried.

    Returns:
        ``{"logged": bool, "pending": bool, "error": str | None, "decision_id": str | None}``.
        ``pending`` means a retry is queued. Inputs and rejected proposals
        are not decisions: ``logged`` and ``pending`` are both False and
        ``error`` is None.
    """
    action_type = action_type or record.get("action_type") or ""
    approval_id = str(record.get("id") or "")
    if not is_decision(action_type, approve) or not approval_id:
        return _outcome(False)

    queued = _queue(record, approve, action_type, db_path)
    try:
        path = _write_decision(record, approve, action_type, kb_path=kb_path)
    except _WRITE_ERRORS as exc:
        logger.warning("Decision log write failed for approval %s: %s", approval_id, exc)
        error = _public_error(exc)
        if queued:
            _mark(approval_id, db_path, error=str(exc) or error)
            return _outcome(False, error, pending=True)
        return _outcome(False, f"{error} (and it could not be queued for a retry)")
    decision = path.stem
    if queued:
        _mark(approval_id, db_path, decision=decision)
    if retry_others:
        try:
            retry_pending_decisions(kb_path=kb_path, db_path=db_path, exclude=(approval_id,))
        except Exception:
            # This decision is logged; a broken retry of others must not report otherwise.
            logger.warning("Retrying pending decision-log writes failed", exc_info=True)
    return _outcome(True, decision=decision)


def ensure_intent_table(conn: sqlite3.Connection) -> None:
    """Create ``decision_writes`` on ``conn`` if it isn't there (call outside a transaction)."""
    conn.executescript(DDL)


def queue_with_decision(conn: sqlite3.Connection, record: dict, approve: bool, action_type: str | None) -> bool:
    """Store the intent to log a decision in the same transaction that records the decision.

    Called by :func:`realize_core.governance.gates.decide_approval` (through
    ``_decide``) before it commits the decision, so a crash right after the
    commit can't lose the decision-log entry: the intent is retried at startup
    (:func:`retry_pending_decisions`). :func:`log_decision` later finds it
    queued and writes the entry once. Inputs and rejected proposals are not
    decisions and are not queued. Does not commit.

    Returns:
        True when the intent is stored (or already was).
    """
    action_type = action_type or record.get("action_type") or ""
    approval_id = str(record.get("id") or "")
    if not approval_id or not is_decision(action_type, approve):
        return False
    now = _now()
    conn.execute(
        """INSERT OR IGNORE INTO decision_writes
           (approval_id, venture_key, approve, action_type, status, attempts, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
        (approval_id, record.get("venture_key") or "", int(bool(approve)), action_type, now, now),
    )
    return True


def _queue(record: dict, approve: bool, action_type: str, db_path) -> bool:
    """Store the intent to log this decision. Returns False when the database can't be written."""
    now = _now()
    try:
        conn = _connect(db_path)
        try:
            conn.execute(
                """INSERT OR IGNORE INTO decision_writes
                   (approval_id, venture_key, approve, action_type, status, attempts, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
                (str(record.get("id")), record.get("venture_key") or "", int(bool(approve)), action_type, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        logger.warning("Could not queue the decision-log write for approval %s", record.get("id"), exc_info=True)
        return False
    return True


def _mark(approval_id: str, db_path, *, decision: str | None = None, error: str | None = None) -> None:
    """Record one attempt: done (with its decision id) or still pending (with the error)."""
    try:
        conn = _connect(db_path)
        try:
            if decision is not None:
                conn.execute(
                    """UPDATE decision_writes SET status = 'done', attempts = attempts + 1, last_error = NULL,
                       decision_id = ?, updated_at = ? WHERE approval_id = ?""",
                    (decision, _now(), approval_id),
                )
            else:
                conn.execute(
                    """UPDATE decision_writes SET attempts = attempts + 1, last_error = ?, updated_at = ?
                       WHERE approval_id = ? AND status = 'pending'""",
                    ((error or "")[:500], _now(), approval_id),
                )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        logger.warning("Could not update the decision-log write for approval %s", approval_id, exc_info=True)


def pending_decisions(db_path=None, *, limit: int = RETRY_BATCH, max_attempts: int | None = None) -> list[dict]:
    """Decision writes still waiting to be written, oldest first.

    ``max_attempts`` leaves out writes that already failed that many times.
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM decision_writes WHERE status = 'pending' AND (? IS NULL OR attempts < ?)
               ORDER BY created_at LIMIT ?""",
            (max_attempts, max_attempts, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _approval_row(approval_id: str, db_path) -> dict | None:
    from realize_core.db.schema import get_connection

    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def retry_pending_decisions(
    *,
    kb_path: Path | str | None = None,
    db_path=None,
    limit: int = RETRY_BATCH,
    exclude: tuple[str, ...] = (),
    max_attempts: int | None = MAX_AUTO_ATTEMPTS,
) -> dict[str, int]:
    """Write decisions whose earlier write failed. Never raises.

    Each one is rebuilt from its approval row, so the entry is the same as the
    first attempt would have written; an entry that already exists is reused,
    never duplicated. Runs at startup and after each decision that is logged
    (writes that failed ``max_attempts`` times are skipped), and from
    ``realize-os decisions retry`` (``max_attempts=None``: every pending write).

    Returns:
        ``{"logged": n, "pending": n}``: written now, and still waiting
        (including any beyond this pass's ``limit``).
    """
    from realize_core.config import load_config

    try:
        intents = [
            i
            for i in pending_decisions(db_path, limit=limit, max_attempts=max_attempts)
            if i["approval_id"] not in exclude
        ]
    except (sqlite3.Error, OSError):
        logger.warning("Could not read pending decision-log writes", exc_info=True)
        return {"logged": 0, "pending": 0}
    if not intents:
        return {"logged": 0, "pending": _pending_count(db_path)}

    config = load_config()
    logged = 0
    for intent in intents:
        approval_id = intent["approval_id"]
        try:
            record = _approval_row(approval_id, db_path)
        except (sqlite3.Error, OSError) as exc:
            _mark(approval_id, db_path, error=f"Could not read the approval: {exc}")
            continue
        if record is None:
            _mark(approval_id, db_path, error="The approval no longer exists")
            continue
        try:
            path = _write_decision(
                record, bool(intent["approve"]), intent["action_type"] or "", kb_path=kb_path, config=config
            )
        except _WRITE_ERRORS as exc:
            logger.warning("Decision log retry failed for approval %s: %s", approval_id, exc)
            _mark(approval_id, db_path, error=str(exc) or type(exc).__name__)
            continue
        _mark(approval_id, db_path, decision=path.stem)
        logged += 1
    if logged:
        logger.info("Decision log: %d pending write(s) recorded on retry", logged)
    return {"logged": logged, "pending": _pending_count(db_path)}


def _pending_count(db_path) -> int:
    """How many decision writes are still waiting (0 if the database can't be read)."""
    try:
        conn = _connect(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM decision_writes WHERE status = 'pending'").fetchone()[0]
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        logger.warning("Could not count pending decision-log writes", exc_info=True)
        return 0


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
