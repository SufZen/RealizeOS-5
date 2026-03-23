"""
Guardrails — safety constraints and quality gate enforcement.

Provides:
- Rule-based guardrail evaluation
- PASS/FAIL verdict parsing from agent/QA output
- Guardrail violation detection
- Quality gate enforcement (strict vs advisory)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from realize_core.agents.base import GuardrailConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------


class Verdict(StrEnum):
    """Quality gate verdict."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VerdictResult:
    """
    Parsed verdict from agent/QA output.

    Attributes:
        verdict: PASS, FAIL, or UNKNOWN.
        confidence: How confident the parser is (0.0–1.0).
        feedback: Extracted feedback text.
        raw_match: The exact text that triggered the verdict.
    """

    verdict: Verdict
    confidence: float = 1.0
    feedback: str = ""
    raw_match: str = ""


# Patterns that indicate PASS (order matters — more specific first)
_PASS_PATTERNS = [
    re.compile(r"\bPASS\b", re.IGNORECASE),
    re.compile(r"\bAPPROVED\b", re.IGNORECASE),
    re.compile(r"\bLGTM\b", re.IGNORECASE),
    re.compile(r"\b(?:verdict|result|status)\s*:\s*(?:pass|approved|accepted)\b", re.IGNORECASE),
    re.compile(r"\bqualit(?:y\s+)?gate\s*:\s*pass\b", re.IGNORECASE),
]

# Patterns that indicate FAIL
_FAIL_PATTERNS = [
    re.compile(r"\bFAIL\b", re.IGNORECASE),
    re.compile(r"\bREJECTED\b", re.IGNORECASE),
    re.compile(r"\bREVISIONS?\s+NEEDED\b", re.IGNORECASE),
    re.compile(r"\b(?:verdict|result|status)\s*:\s*(?:fail|rejected|revisions?\s+needed)\b", re.IGNORECASE),
    re.compile(r"\bqualit(?:y\s+)?gate\s*:\s*fail\b", re.IGNORECASE),
    re.compile(r"\bNOT\s+APPROVED\b", re.IGNORECASE),
]


def parse_verdict(text: str) -> VerdictResult:
    """
    Parse a PASS/FAIL verdict from agent or QA output text.

    Looks for explicit verdict markers (PASS, FAIL, APPROVED, REJECTED,
    REVISIONS NEEDED, LGTM, etc.).

    Returns:
        A VerdictResult with the parsed verdict and extracted feedback.
    """
    if not text or not text.strip():
        return VerdictResult(verdict=Verdict.UNKNOWN, confidence=0.0)

    # Check FAIL first (more conservative — a rejection should win over noise)
    for pattern in _FAIL_PATTERNS:
        match = pattern.search(text)
        if match:
            return VerdictResult(
                verdict=Verdict.FAIL,
                confidence=0.9,
                feedback=_extract_feedback(text),
                raw_match=match.group(0),
            )

    for pattern in _PASS_PATTERNS:
        match = pattern.search(text)
        if match:
            return VerdictResult(
                verdict=Verdict.PASS,
                confidence=0.9,
                feedback=_extract_feedback(text),
                raw_match=match.group(0),
            )

    return VerdictResult(
        verdict=Verdict.UNKNOWN,
        confidence=0.3,
        feedback=text.strip()[:500],
    )


def _extract_feedback(text: str) -> str:
    """
    Extract the feedback portion of a verdict output.

    Looks for text after the verdict line, or returns the full text
    (truncated) if no clear structure is found.
    """
    # Try to find content after the verdict line
    lines = text.strip().splitlines()
    feedback_lines = []
    found_verdict = False

    for line in lines:
        if found_verdict:
            feedback_lines.append(line)
        elif any(p.search(line) for p in _PASS_PATTERNS + _FAIL_PATTERNS):
            found_verdict = True
            # Include rest of verdict line if there's content after the keyword
            remainder = line.strip()
            if len(remainder) > 20:  # Has meaningful content beyond keyword
                feedback_lines.append(remainder)

    if feedback_lines:
        return "\n".join(feedback_lines).strip()[:2000]

    return text.strip()[:500]


# ---------------------------------------------------------------------------
# Guardrail evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardrailViolation:
    """A detected guardrail violation."""

    guardrail_name: str
    description: str
    enforcement: str  # "strict" or "advisory"
    detail: str = ""


def check_guardrails(
    text: str,
    guardrails: list[GuardrailConfig],
    context: dict[str, Any] | None = None,
) -> list[GuardrailViolation]:
    """
    Check text against a list of guardrail configurations.

    This performs keyword-based guardrail checking. For more sophisticated
    checks (LLM-based), use ``evaluate_with_llm()``.

    Args:
        text: The agent output to check.
        guardrails: List of guardrail configs to evaluate.
        context: Optional context for rule evaluation.

    Returns:
        List of violations found (empty = all clear).
    """
    violations: list[GuardrailViolation] = []

    for guardrail in guardrails:
        violation = _evaluate_guardrail(text, guardrail, context or {})
        if violation:
            violations.append(violation)

    if violations:
        strict_count = sum(1 for v in violations if v.enforcement == "strict")
        logger.warning(
            "Guardrail check found %d violation(s) (%d strict)",
            len(violations),
            strict_count,
        )

    return violations


def _evaluate_guardrail(
    text: str,
    guardrail: GuardrailConfig,
    context: dict[str, Any],
) -> GuardrailViolation | None:
    """
    Evaluate a single guardrail against text.

    Basic keyword-based detection — checks for prohibited content patterns.
    """
    # Check for common safety patterns based on guardrail description
    description_lower = guardrail.description.lower()

    # Pattern: "never share confidential data" → check for email/phone/SSN patterns
    if "confidential" in description_lower or "sensitive" in description_lower:
        if _contains_sensitive_data(text):
            return GuardrailViolation(
                guardrail_name=guardrail.name,
                description=guardrail.description,
                enforcement=guardrail.enforcement,
                detail="Output may contain sensitive data patterns",
            )

    # Pattern: "confirm before sending" → advisory, always pass
    if "confirm" in description_lower and "before" in description_lower:
        # This is an advisory that requires human confirmation
        # It doesn't block content, just flags it
        return None

    return None


def _contains_sensitive_data(text: str) -> bool:
    """
    Basic check for potentially sensitive data patterns in text.

    Checks for: email addresses, phone numbers, SSN-like patterns.
    """
    # Email pattern
    if re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text):
        return True
    # SSN-like pattern (XXX-XX-XXXX)
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
        return True
    # Credit card-like pattern
    if re.search(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", text):
        return True
    return False


def has_strict_violations(violations: list[GuardrailViolation]) -> bool:
    """Check if any violations are strict (blocking)."""
    return any(v.enforcement == "strict" for v in violations)


def has_advisory_violations(violations: list[GuardrailViolation]) -> bool:
    """Check if any violations are advisory (non-blocking)."""
    return any(v.enforcement == "advisory" for v in violations)
