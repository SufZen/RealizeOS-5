"""
Lightweight interaction tracker — wraps analytics for use in handlers.

Also detects satisfaction signals from user messages.
"""
import logging
import time

from realize_core.evolution.analytics import log_interaction

logger = logging.getLogger(__name__)

NEGATIVE_SIGNALS = [
    "no that's wrong", "that's not right", "incorrect", "wrong answer",
    "not what i asked", "try again", "redo this", "start over",
    "that's not what i meant", "you misunderstood",
]

RETRY_SIGNALS = [
    "again", "retry", "one more time", "let me rephrase",
    "what i meant was", "i said",
]


def detect_satisfaction_signal(message: str) -> str | None:
    """Detect if a message indicates satisfaction (or lack thereof)."""
    msg_lower = message.lower()
    for phrase in NEGATIVE_SIGNALS:
        if phrase in msg_lower:
            return "correction"
    for phrase in RETRY_SIGNALS:
        if phrase in msg_lower:
            return "retry"
    if any(w in msg_lower for w in ["thanks", "perfect", "great", "exactly", "good"]):
        return "positive"
    return None


class InteractionTimer:
    """Context manager to time interactions and log them."""

    def __init__(self, user_id: str, system_key: str, message: str):
        self.user_id = str(user_id)
        self.system_key = system_key
        self.message = message
        self.start_time = None
        self.agent_key = ""
        self.skill_name = ""
        self.task_type = ""
        self.tools_used = []
        self.intent = ""
        self.error = ""

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = int((time.time() - self.start_time) * 1000)
        if exc_val:
            self.error = str(exc_val)[:200]
        try:
            log_interaction(
                user_id=self.user_id, system_key=self.system_key,
                message=self.message, latency_ms=latency_ms,
                agent_key=self.agent_key, skill_name=self.skill_name,
                task_type=self.task_type, tools_used=self.tools_used,
                intent=self.intent, error=self.error,
            )
        except Exception as e:
            logger.debug(f"Interaction logging failed (non-fatal): {e}")
        return False
