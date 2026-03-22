"""
Creative Session Manager for RealizeOS.

Tracks active creative sessions with state, pipeline position, drafts, and loaded context.
Uses SQLite write-through with in-memory cache for persistence across restarts.

A session represents an ongoing creative task that persists across multiple messages
and can involve multiple agents working in sequence.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


def _db_ctx():
    """Get a SQLite connection context manager from memory store."""
    from realize_core.memory.store import db_connection
    return db_connection()


@dataclass
class CreativeSession:
    """An active creative work session."""
    id: str
    system_key: str
    brief: str
    task_type: str
    active_agent: str
    stage: str  # "briefing", "drafting", "iterating", "reviewing", "approved", "completed"
    pipeline: list[str] = field(default_factory=list)
    pipeline_index: int = 0
    context_files: list[str] = field(default_factory=list)
    drafts: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    user_id: str = ""

    def current_pipeline_agent(self) -> str | None:
        """Get the agent at the current pipeline position."""
        if 0 <= self.pipeline_index < len(self.pipeline):
            return self.pipeline[self.pipeline_index]
        return None

    def advance_pipeline(self) -> str | None:
        """Move to next agent in pipeline. Returns the new agent or None if done."""
        self.pipeline_index += 1
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.pipeline_index < len(self.pipeline):
            self.active_agent = self.pipeline[self.pipeline_index]
            self.save()
            return self.active_agent
        self.save()
        return None

    def add_draft(self, content: str, agent: str):
        """Record a new draft version."""
        self.drafts.append({
            "version": len(self.drafts) + 1,
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save()

    def latest_draft(self) -> dict | None:
        """Get the most recent draft."""
        return self.drafts[-1] if self.drafts else None

    def save(self):
        """Persist session state to SQLite."""
        try:
            with _db_ctx() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "INSERT OR REPLACE INTO sessions "
                    "(id, system_key, user_id, brief, task_type, active_agent, stage, "
                    "pipeline, pipeline_index, context_files, drafts, review, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.id, self.system_key, self.user_id, self.brief, self.task_type,
                        self.active_agent, self.stage,
                        json.dumps(self.pipeline), self.pipeline_index,
                        json.dumps(self.context_files), json.dumps(self.drafts),
                        json.dumps(self.review), self.created_at, now,
                    ),
                )
        except Exception as e:
            logger.warning(f"Failed to persist session {self.id}: {e}")

    def summary(self) -> str:
        """Human-readable session status."""
        lines = [
            f"Session ({self.system_key}) - {self.stage}, agent: {self.active_agent}",
            f"Brief: {self.brief[:120]}{'...' if len(self.brief) > 120 else ''}",
        ]
        if self.pipeline:
            pipeline_display = []
            for i, agent in enumerate(self.pipeline):
                if i < self.pipeline_index:
                    pipeline_display.append(f"done: {agent}")
                elif i == self.pipeline_index:
                    pipeline_display.append(f"{agent} (active)")
                else:
                    pipeline_display.append(agent)
            lines.append(f"Pipeline: {' > '.join(pipeline_display)}")
        if self.drafts:
            lines.append(f"Drafts: {len(self.drafts)} version(s)")
        if self.context_files:
            file_names = [f.split("/")[-1] for f in self.context_files]
            lines.append(f"Loaded context: {', '.join(file_names)}")
        return "\n".join(lines)


# Storage: {(system_key, user_id): CreativeSession}
_sessions: dict[tuple[str, str], CreativeSession] = {}
_hydrated_users: set[str] = set()


def _hydrate_sessions(user_id: str):
    """Lazy-load sessions from SQLite for a user."""
    if user_id in _hydrated_users:
        return
    _hydrated_users.add(user_id)

    try:
        with _db_ctx() as conn:
            rows = conn.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,)).fetchall()

        for row in rows:
            session = CreativeSession(
                id=row["id"],
                system_key=row["system_key"],
                brief=row["brief"],
                task_type=row["task_type"],
                active_agent=row["active_agent"],
                stage=row["stage"],
                pipeline=json.loads(row["pipeline"]),
                pipeline_index=row["pipeline_index"],
                context_files=json.loads(row["context_files"]),
                drafts=json.loads(row["drafts"]),
                review=json.loads(row["review"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                user_id=str(row["user_id"]),
            )
            _sessions[(session.system_key, str(row["user_id"]))] = session
            logger.info(f"Hydrated session {session.id} for {session.system_key}")
    except Exception as e:
        logger.debug(f"Failed to hydrate sessions for user {user_id}: {e}")


def create_session(
    system_key: str,
    user_id: str,
    brief: str,
    task_type: str,
    pipeline: list[str],
) -> CreativeSession:
    """Create a new creative session."""
    session = CreativeSession(
        id=str(uuid.uuid4())[:8],
        system_key=system_key,
        brief=brief,
        task_type=task_type,
        active_agent=pipeline[0] if pipeline else "orchestrator",
        stage="briefing",
        pipeline=pipeline,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        user_id=str(user_id),
    )
    _sessions[(system_key, str(user_id))] = session
    session.save()
    return session


def get_session(system_key: str, user_id: str) -> CreativeSession | None:
    """Get the active session for a user in a system."""
    _hydrate_sessions(str(user_id))
    return _sessions.get((system_key, str(user_id)))


def end_session(system_key: str, user_id: str):
    """End (remove) a session."""
    key = (system_key, str(user_id))
    session = _sessions.pop(key, None)
    if session:
        try:
            with _db_ctx() as conn:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
        except Exception:
            pass
        logger.info(f"Ended session {session.id}")
