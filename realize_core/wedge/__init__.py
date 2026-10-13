"""Self-serve wedge (STORY-46, Play W): the tender register in the user's own agent.

The user's agent (Claude, ChatGPT, …) reads the tender document itself. RealizeOS
supplies the method (steps, register format, the market's glossary and rule
cards with their verification level), checks the register the agent returns,
renders it as a finished document and records the run so the funnel can be
measured. No model runs on RealizeOS's side, and no document is stored.
"""

from realize_core.wedge.register import check_register, get_method, render_register
from realize_core.wedge.store import (
    contacts,
    funnel,
    funnel_summary,
    mark_contacted,
    purge_expired,
    record_run,
    request_call,
)

__all__ = [
    "check_register",
    "contacts",
    "funnel",
    "funnel_summary",
    "get_method",
    "mark_contacted",
    "purge_expired",
    "record_run",
    "render_register",
    "request_call",
]
