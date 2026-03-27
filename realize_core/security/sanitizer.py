"""
Input sanitizer — validate and clean user input before processing.

Provides per-channel input length limits and basic injection detection.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Default max input lengths per channel
DEFAULT_MAX_LENGTHS: dict[str, int] = {
    "dashboard": 4096,
    "api": 4096,
    "telegram": 4096,
    "whatsapp": 4096,
    "slack": 4000,
    "email": 10000,
    "webhook": 2000,
}

# Patterns that may indicate prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"<<SYS>>",
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def sanitize_input(
    text: str,
    channel: str = "dashboard",
    config: dict = None,
) -> dict:
    """
    Sanitize user input.

    Args:
        text: The raw input text
        channel: Channel source (for length limits)
        config: System config (for custom limits)

    Returns:
        {
            text: sanitized text,
            truncated: bool,
            injection_detected: bool,
            warnings: list[str],
        }
    """
    warnings = []
    truncated = False
    injection_detected = False

    # 1. Get max length for this channel
    max_lengths = dict(DEFAULT_MAX_LENGTHS)
    if config:
        security = config.get("security", {})
        custom_lengths = security.get("sanitizer", {}).get("max_length", {})
        max_lengths.update(custom_lengths)

    max_len = max_lengths.get(channel, 4096)

    # 2. Truncate if too long
    if len(text) > max_len:
        text = text[:max_len]
        truncated = True
        warnings.append(f"Input truncated to {max_len} characters (channel: {channel})")

    # 3. Strip null bytes and control characters (except newline/tab)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 4. Check for injection patterns
    for pattern in _compiled_patterns:
        if pattern.search(text):
            injection_detected = True
            warnings.append("Potential prompt injection pattern detected")
            break

    return {
        "text": text,
        "truncated": truncated,
        "injection_detected": injection_detected,
        "warnings": warnings,
    }


def is_safe_input(text: str, channel: str = "dashboard", config: dict = None) -> bool:
    """Quick check — returns True if input passes sanitization without injection detection."""
    result = sanitize_input(text, channel, config)
    return not result["injection_detected"]


class PathTraversalError(Exception):
    """Raised when a path traversal attempt is detected."""


def sanitize_path(
    user_path: str,
    allowed_root: str,
    allow_absolute: bool = False,
) -> str:
    """
    Validate and sanitize a file path against traversal attacks.

    Args:
        user_path: The user-supplied path string.
        allowed_root: The absolute root directory paths must stay within.
        allow_absolute: If False (default), reject absolute paths from users.

    Returns:
        The resolved, safe absolute path as a string.

    Raises:
        PathTraversalError: If the path is unsafe.
    """
    import os
    from pathlib import Path

    # Reject null bytes (can truncate filenames on some systems)
    if "\x00" in user_path:
        raise PathTraversalError("Null byte detected in path")

    # Reject obvious traversal patterns
    normalized = user_path.replace("\\", "/")
    if ".." in normalized.split("/"):
        raise PathTraversalError("Path traversal (..) detected")

    # Reject absolute paths unless explicitly allowed
    if not allow_absolute and os.path.isabs(user_path):
        raise PathTraversalError("Absolute paths are not allowed")

    # Resolve the full path
    root = Path(allowed_root).resolve()
    full_path = (root / user_path).resolve()

    # Ensure the resolved path is still under the allowed root
    try:
        full_path.relative_to(root)
    except ValueError:
        raise PathTraversalError(
            f"Path '{user_path}' resolves outside allowed root"
        )

    return str(full_path)
