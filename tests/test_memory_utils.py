"""Test memory store, conversation, and preferences."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from realize_core.config import DATA_PATH
from realize_core.memory.store import db_connection, init_db, store_memory, search_memories, log_llm_usage, get_usage_stats, get_feedback_signals
from realize_core.memory.conversation import add_message, get_history, clear_history
from realize_core.utils.cost_tracker import log_usage, get_usage_summary
from realize_core.utils.humanizer import humanize
from realize_core.utils.rate_limiter import RateLimiter


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", test_db)
    init_db()
    
    # also clear preference cache
    from realize_core.memory.preference_learner import clear_preference_cache
    clear_preference_cache()
    
    # clear conversation cache
    from realize_core.memory.conversation import clear_all
    clear_all()
    
    yield test_db


def test_memory_store_and_search():
    store_memory("sys-1", "fact", "The sky is blue", ["nature", "color"])
    store_memory("sys-1", "decision", "We chose Python", ["tech"])
    store_memory("sys-2", "learning", "User likes brevity", ["user-pref"])

    # Search all
    results = search_memories("blue")
    assert len(results) == 1
    assert results[0]["content"] == "The sky is blue"

    # Search specific system
    results = search_memories("Python", system_key="sys-1")
    assert len(results) == 1
    
    results = search_memories("Python", system_key="sys-2")
    assert len(results) == 0


def test_conversation_history():
    add_message("bot-1", "user-1", "user", "Hi there")
    add_message("bot-1", "user-1", "assistant", "Hello!")
    
    history = get_history("bot-1", "user-1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[0]["content"] == "Hi there"
    
    clear_history("bot-1", "user-1")
    assert len(get_history("bot-1", "user-1")) == 0


def test_llm_usage_tracking():
    log_llm_usage("model-a", 100, 50, 0.05, "tenant-1")
    log_llm_usage("model-b", 200, 100, 0.10, "tenant-1")
    
    stats = get_usage_stats("tenant-1", days=1)
    assert stats["total_calls"] == 2
    assert stats["total_input_tokens"] == 300
    assert stats["total_output_tokens"] == 150
    assert round(stats["total_cost_usd"], 2) == 0.15


def test_humanizer():
    assert humanize("✨ Here is the code ✨") == "Here is the code"
    assert humanize("Absolutely!\n\nThe solution is simple.") == "The solution is simple."
    assert humanize("**bold text**", channel="email") == "bold text"


def test_rate_limiter():
    limiter = RateLimiter(requests_per_minute=2, cost_per_hour_usd=1.0)
    
    # Check rate limits
    assert limiter.check_rate_limit("user-1") is True
    limiter.record_request("user-1")
    assert limiter.check_rate_limit("user-1") is True
    limiter.record_request("user-1")
    assert limiter.check_rate_limit("user-1") is False  # exceeded 2
    
    # Check cost limits
    assert limiter.check_cost_limit("user-2") is True
    limiter.record_cost(0.8, "user-2")
    assert limiter.check_cost_limit("user-2") is True
    limiter.record_cost(0.3, "user-2")
    assert limiter.check_cost_limit("user-2") is False  # exceeded $1.0
