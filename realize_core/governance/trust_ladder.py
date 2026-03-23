"""
Trust Ladder — graduated permission system with 5 trust tiers.

Replaces binary on/off gates with a nuanced permission model:
  Tier 1: Block (action not allowed)
  Tier 2: Approve (requires human approval every time)
  Tier 3: Approve (requires approval for sensitive targets)
  Tier 4: Auto (auto-approved, logged)
  Tier 5: Auto (fully autonomous, minimal logging)

Each action type has a threshold per tier. The system's current trust level
determines which tier applies.

Configuration in realize-os.yaml:
  trust:
    level: 3  # Current system trust level (1-5)
    actions:
      send_email: {1: block, 2: approve, 3: approve, 4: auto, 5: auto}
      publish_content: {1: block, 2: approve, 3: approve, 4: approve, 5: auto}
      ...
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TrustDecision(Enum):
    BLOCK = "block"
    APPROVE = "approve"
    AUTO = "auto"


# Default trust rules (used when not configured in YAML)
DEFAULT_TRUST_RULES: dict[str, dict[int, str]] = {
    "send_email": {1: "block", 2: "approve", 3: "approve", 4: "auto", 5: "auto"},
    "publish_content": {1: "block", 2: "approve", 3: "approve", 4: "approve", 5: "auto"},
    "external_api": {1: "block", 2: "approve", 3: "auto", 4: "auto", 5: "auto"},
    "create_event": {1: "approve", 2: "auto", 3: "auto", 4: "auto", 5: "auto"},
    "high_cost_llm": {1: "approve", 2: "approve", 3: "auto", 4: "auto", 5: "auto"},
    "kb_save": {1: "approve", 2: "auto", 3: "auto", 4: "auto", 5: "auto"},
    "phone_call": {1: "block", 2: "approve", 3: "approve", 4: "approve", 5: "approve"},
    "social_post": {1: "block", 2: "approve", 3: "approve", 4: "approve", 5: "approve"},
    "financial_action": {1: "block", 2: "block", 3: "approve", 4: "approve", 5: "approve"},
    "drive_upload": {1: "block", 2: "approve", 3: "approve", 4: "auto", 5: "auto"},
}

# Map tool actions to trust action types
ACTION_MAP: dict[str, str] = {
    "gmail_send": "send_email",
    "gmail_create_draft": "send_email",
    "calendar_create_event": "create_event",
    "calendar_update_event": "create_event",
    "drive_create_doc": "external_api",
    "drive_upload_file": "drive_upload",
    "browser_click": "external_api",
    "browser_type": "external_api",
    "web_search": "external_api",
    "linkedin_post": "social_post",
    "twitter_post": "social_post",
    "phone_call": "phone_call",
    "stripe_create_invoice": "financial_action",
    "stripe_create_payment_link": "financial_action",
}


def get_trust_level(config: dict = None) -> int:
    """Get the current system trust level (1-5)."""
    if config:
        trust_config = config.get("trust", {})
        level = trust_config.get("level", trust_config.get("proactivity_level", 3))
        return max(1, min(5, int(level)))
    return 3  # Default to tier 3


def get_trust_rules(config: dict = None) -> dict[str, dict[int, str]]:
    """Get trust rules from config, falling back to defaults."""
    rules = dict(DEFAULT_TRUST_RULES)
    if config:
        trust_config = config.get("trust", {})
        custom_actions = trust_config.get("actions", {})
        for action, tiers in custom_actions.items():
            if isinstance(tiers, dict):
                rules[action] = {int(k): v for k, v in tiers.items()}
    return rules


def check_trust(action: str, config: dict = None, channel: str = "dashboard") -> TrustDecision:
    """
    Check whether an action is allowed under the current trust level.

    Args:
        action: The action to check (e.g., "gmail_send", "send_email")
        config: System configuration dict
        channel: The channel making the request

    Returns:
        TrustDecision: BLOCK, APPROVE, or AUTO
    """
    # Resolve tool action to trust action type
    trust_action = ACTION_MAP.get(action, action)

    rules = get_trust_rules(config)
    level = get_trust_level(config)

    # Get the rule for this action
    action_rules = rules.get(trust_action)
    if not action_rules:
        # No rule defined — default to auto for known actions, approve for unknown
        return TrustDecision.AUTO

    # Look up the decision for the current trust level
    decision_str = action_rules.get(level, "approve")

    try:
        return TrustDecision(decision_str)
    except ValueError:
        return TrustDecision.APPROVE


def is_action_allowed(action: str, config: dict = None, channel: str = "dashboard") -> bool:
    """Check if an action is allowed (not blocked)."""
    return check_trust(action, config, channel) != TrustDecision.BLOCK


def requires_approval(action: str, config: dict = None, channel: str = "dashboard") -> bool:
    """Check if an action requires human approval."""
    return check_trust(action, config, channel) == TrustDecision.APPROVE


def get_trust_matrix(config: dict = None) -> dict:
    """
    Get the full trust matrix for display in the dashboard.

    Returns dict with:
        level: current trust level
        actions: {action_name: {1: "block", 2: "approve", ...}}
    """
    return {
        "level": get_trust_level(config),
        "actions": get_trust_rules(config),
    }


def set_trust_level(config_path: str, level: int) -> bool:
    """Update the trust level in realize-os.yaml."""
    level = max(1, min(5, int(level)))
    try:
        from pathlib import Path

        import yaml

        path = Path(config_path)
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if "trust" not in config:
            config["trust"] = {}
        config["trust"]["level"] = level
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        logger.error(f"Failed to set trust level: {e}")
        return False
