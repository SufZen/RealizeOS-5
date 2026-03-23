"""
Output humanizer for RealizeOS.

Strips machine-generated marks from AI output to make it sound natural
across different channels (chat, email, documents). Removes decorative
symbols, excessive formatting, and AI-typical patterns.
"""

import logging
import re

logger = logging.getLogger(__name__)


def humanize(text: str, channel: str = "api") -> str:
    """
    Clean up AI-generated text for human consumption.

    Args:
        text: Raw AI output text.
        channel: Target channel for format-specific cleaning.

    Returns:
        Cleaned, human-sounding text.
    """
    if not text:
        return text

    result = text

    # Strip common AI artifacts
    result = _strip_decorative_symbols(result)
    result = _strip_excessive_formatting(result)
    result = _strip_ai_preambles(result)

    # Channel-specific cleaning
    if channel == "telegram":
        result = _clean_for_telegram(result)
    elif channel == "email":
        result = _clean_for_email(result)

    return result.strip()


def _strip_decorative_symbols(text: str) -> str:
    """Remove decorative Unicode symbols that AI models like to add."""
    # Remove decorative bullets and symbols
    text = re.sub(r"[✨🔹🔸▪️▫️◾◽🔷🔶💡🎯📌📍🚀💫⭐🌟✅❌⚠️📝🔑💪🎉]", "", text)
    # Remove repeated decorative dashes/equals
    text = re.sub(r"^[═─━]{3,}$", "", text, flags=re.MULTILINE)
    return text


def _strip_excessive_formatting(text: str) -> str:
    """Reduce excessive markdown formatting."""
    # Remove more than 2 consecutive blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    # Remove trailing whitespace on lines
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text


def _strip_ai_preambles(text: str) -> str:
    """Remove common AI preamble phrases."""
    preambles = [
        r"^(Sure!|Of course!|Absolutely!|Great question!|Happy to help!|Here you go!)\s*\n*",
        r"^(I'd be happy to|Let me|I'll)\s+(help you with that|assist you|do that)[.!]\s*\n*",
    ]
    for pattern in preambles:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text


def _clean_for_telegram(text: str) -> str:
    """Telegram-specific cleaning."""
    # Remove markdown headers (Telegram doesn't render them well)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Limit message length for Telegram (4096 char limit)
    if len(text) > 4000:
        text = text[:3997] + "..."
    return text


def _clean_for_email(text: str) -> str:
    """Email-specific cleaning."""
    # Remove markdown bold/italic (email uses HTML)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    return text
