"""
Preference learner — detect and adapt to user communication patterns.

Tracks:
- Preferred response length (concise vs detailed)
- Communication tone (formal vs casual)
- Topic interests (most discussed domains)
- Active hours (when the user is most active)
- Language patterns (emoji use, formatting preferences)

Preferences are stored in memory DB and injected into the prompt builder
as an additional context layer.
"""
import logging
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory cache of learned preferences per user
_preference_cache: dict[str, dict] = {}


def analyze_preferences(system_key: str, user_id: str = "dashboard-user") -> dict:
    """
    Analyze conversation history to learn user preferences.

    Returns a preferences dict that can be injected into prompts.
    """
    cache_key = f"{system_key}:{user_id}"
    if cache_key in _preference_cache:
        return _preference_cache[cache_key]

    try:
        from realize_core.memory.conversation import get_history_with_timestamps
        history = get_history_with_timestamps(system_key, user_id)
    except Exception:
        history = []

    if len(history) < 3:
        return {}

    user_msgs = [m for m in history if m.get("role") == "user"]
    [m for m in history if m.get("role") == "assistant"]

    prefs = {}

    # 1. Response length preference
    if user_msgs:
        avg_user_len = sum(len(m.get("content", "")) for m in user_msgs) / len(user_msgs)
        if avg_user_len < 50:
            prefs["response_style"] = "concise"
            prefs["response_hint"] = "User sends short messages. Keep responses brief and direct."
        elif avg_user_len > 300:
            prefs["response_style"] = "detailed"
            prefs["response_hint"] = "User writes detailed messages. Provide thorough, comprehensive responses."
        else:
            prefs["response_style"] = "balanced"

    # 2. Tone detection
    if user_msgs:
        all_user_text = " ".join(m.get("content", "") for m in user_msgs[-20:]).lower()
        formal_signals = sum(1 for w in ["please", "kindly", "would you", "could you", "regarding", "sincerely"]
                           if w in all_user_text)
        casual_signals = sum(1 for w in ["hey", "cool", "awesome", "thanks!", "yeah", "gonna", "wanna", "lol"]
                           if w in all_user_text)
        if formal_signals > casual_signals + 2:
            prefs["tone"] = "formal"
            prefs["tone_hint"] = "User prefers formal communication."
        elif casual_signals > formal_signals + 2:
            prefs["tone"] = "casual"
            prefs["tone_hint"] = "User prefers casual, friendly communication."

    # 3. Topic interests
    if user_msgs:
        topic_keywords = {
            "strategy": ["strategy", "plan", "roadmap", "goals", "vision", "growth"],
            "content": ["write", "post", "article", "blog", "content", "copy"],
            "finance": ["budget", "cost", "invoice", "payment", "revenue", "profit"],
            "operations": ["task", "schedule", "meeting", "deadline", "process", "workflow"],
            "technical": ["code", "build", "deploy", "api", "database", "server"],
            "marketing": ["seo", "ads", "campaign", "audience", "brand", "funnel"],
        }
        topic_counts = Counter()
        for msg in user_msgs[-30:]:
            text = msg.get("content", "").lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in text for kw in keywords):
                    topic_counts[topic] += 1

        if topic_counts:
            top_topics = topic_counts.most_common(3)
            prefs["top_topics"] = [t[0] for t in top_topics]
            prefs["topics_hint"] = f"User frequently discusses: {', '.join(t[0] for t in top_topics)}."

    # 4. Active hours
    timestamps = []
    for msg in user_msgs:
        ts = msg.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamps.append(dt.hour)
            except (ValueError, TypeError):
                pass

    if len(timestamps) >= 5:
        hour_counts = Counter(timestamps)
        peak_hour = hour_counts.most_common(1)[0][0]
        prefs["peak_hour"] = peak_hour

    # 5. Emoji usage
    if user_msgs:
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF]"
        )
        emoji_count = sum(len(emoji_pattern.findall(m.get("content", ""))) for m in user_msgs[-20:])
        if emoji_count > 5:
            prefs["uses_emoji"] = True

    # Cache result
    _preference_cache[cache_key] = prefs
    return prefs


def get_preference_prompt_layer(system_key: str, user_id: str = "dashboard-user") -> str:
    """
    Generate a prompt layer string from learned preferences.

    This gets injected into the system prompt by the prompt builder.
    """
    prefs = analyze_preferences(system_key, user_id)
    if not prefs:
        return ""

    lines = ["## User Preferences (Learned)", ""]
    if prefs.get("response_hint"):
        lines.append(f"- {prefs['response_hint']}")
    if prefs.get("tone_hint"):
        lines.append(f"- {prefs['tone_hint']}")
    if prefs.get("topics_hint"):
        lines.append(f"- {prefs['topics_hint']}")
    if prefs.get("uses_emoji"):
        lines.append("- User uses emojis in messages. Feel free to use them occasionally.")

    if len(lines) <= 2:
        return ""

    return "\n".join(lines)


def clear_preference_cache(system_key: str = "", user_id: str = ""):
    """Clear cached preferences (call after significant changes)."""
    if system_key and user_id:
        _preference_cache.pop(f"{system_key}:{user_id}", None)
    else:
        _preference_cache.clear()


def store_preferences(system_key: str, user_id: str = "dashboard-user"):
    """Store current preferences to memory DB for persistence."""
    prefs = analyze_preferences(system_key, user_id)
    if not prefs:
        return

    try:
        import json

        from realize_core.memory.store import store_memory
        store_memory(
            system_key=system_key,
            category="user_preferences",
            content=json.dumps(prefs),
            tags=["preferences", "auto-learned"],
        )
    except Exception as e:
        logger.warning(f"Failed to store preferences: {e}")
