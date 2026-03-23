"""
Enhanced prompt injection detection for RealizeOS.

Provides multi-layer injection detection:
- Pattern matching (regex-based, categorized)
- Scoring model (weighted categories)
- Structural analysis (instruction-like markers)
- Configurable sensitivity levels

Threat categories:
- instruction_override: Attempts to replace system instructions
- role_manipulation: Asks the model to assume a different identity
- context_leakage: Tries to extract system prompts or internal state
- encoding_bypass: Uses encoding tricks to evade detection
- delimiter_injection: Injects fake message boundaries
"""

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ThreatCategory(StrEnum):
    """Categories of prompt injection attacks."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLE_MANIPULATION = "role_manipulation"
    CONTEXT_LEAKAGE = "context_leakage"
    ENCODING_BYPASS = "encoding_bypass"
    DELIMITER_INJECTION = "delimiter_injection"


class Severity(StrEnum):
    """Severity levels for injection threats."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ThreatPattern:
    """A single detection pattern."""

    pattern: str
    category: ThreatCategory
    severity: Severity
    description: str
    weight: float = 1.0
    is_regex: bool = True


@dataclass
class InjectionResult:
    """Result of an injection scan."""

    is_suspicious: bool
    risk_score: float  # 0.0 - 1.0
    threats: list[dict] = field(default_factory=list)
    categories: set[str] = field(default_factory=set)
    max_severity: str = "low"
    sanitized_text: str = ""
    details: str = ""

    @property
    def should_block(self) -> bool:
        """Whether the input should be blocked based on risk."""
        return self.risk_score >= 0.7

    @property
    def needs_review(self) -> bool:
        """Whether the input needs human review."""
        return 0.4 <= self.risk_score < 0.7


# ---------------------------------------------------------------------------
# Threat patterns
# ---------------------------------------------------------------------------

_THREAT_PATTERNS: list[ThreatPattern] = [
    # --- instruction_override (CRITICAL) ---
    ThreatPattern(
        r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+(instructions|prompts|rules|directives|context)",
        ThreatCategory.INSTRUCTION_OVERRIDE,
        Severity.CRITICAL,
        "Attempts to override system instructions",
        weight=2.0,
    ),
    ThreatPattern(
        r"disregard\s+(all\s+)?(above|previous|prior|earlier|your)",
        ThreatCategory.INSTRUCTION_OVERRIDE,
        Severity.CRITICAL,
        "Disregard instruction attempt",
        weight=2.0,
    ),
    ThreatPattern(
        r"forget\s+(everything|all|your\s+(instructions|rules|training))",
        ThreatCategory.INSTRUCTION_OVERRIDE,
        Severity.CRITICAL,
        "Memory reset attempt",
        weight=2.0,
    ),
    ThreatPattern(
        r"new\s+(instructions|system\s+prompt|rules)\s*:",
        ThreatCategory.INSTRUCTION_OVERRIDE,
        Severity.HIGH,
        "Injecting new instructions",
        weight=1.5,
    ),
    ThreatPattern(
        r"override\s+(the\s+)?(system|safety|content)\s*(prompt|filter|rules)",
        ThreatCategory.INSTRUCTION_OVERRIDE,
        Severity.CRITICAL,
        "Explicit override attempt",
        weight=2.0,
    ),
    # --- role_manipulation (HIGH) ---
    ThreatPattern(
        r"you\s+are\s+now\s+(a|an|the)\s+",
        ThreatCategory.ROLE_MANIPULATION,
        Severity.HIGH,
        "Identity reassignment attempt",
        weight=1.5,
    ),
    ThreatPattern(
        r"pretend\s+(you\s+are|to\s+be)\s+",
        ThreatCategory.ROLE_MANIPULATION,
        Severity.MEDIUM,
        "Pretend/roleplay attempt",
        weight=1.0,
    ),
    ThreatPattern(
        r"(act|behave)\s+(as\s+if|like)\s+you\s+(are|were)",
        ThreatCategory.ROLE_MANIPULATION,
        Severity.MEDIUM,
        "Behavioral manipulation attempt",
        weight=1.0,
    ),
    ThreatPattern(
        r"(?:jailbreak|do\s+anything\s+now|dan\s+mode|developer\s+mode|god\s+mode)",
        ThreatCategory.ROLE_MANIPULATION,
        Severity.CRITICAL,
        "Known jailbreak technique",
        weight=2.5,
    ),
    ThreatPattern(
        r"from\s+now\s+on\s+(you|your)\s+(will|should|must|are)",
        ThreatCategory.ROLE_MANIPULATION,
        Severity.HIGH,
        "Persistent behavioral override attempt",
        weight=1.5,
    ),
    # --- context_leakage (MEDIUM-HIGH) ---
    ThreatPattern(
        r"(print|show|display|reveal|output|repeat)\s+(\w+\s+)?(the\s+)?(system\s+prompt|initial\s+instructions|hidden\s+instructions|your\s+instructions)",
        ThreatCategory.CONTEXT_LEAKAGE,
        Severity.HIGH,
        "System prompt extraction attempt",
        weight=1.5,
    ),
    ThreatPattern(
        r"what\s+(are|were)\s+your\s+(initial|original|system)\s+(instructions|prompt|rules)",
        ThreatCategory.CONTEXT_LEAKAGE,
        Severity.MEDIUM,
        "Instructions inquiry",
        weight=1.0,
    ),
    ThreatPattern(
        r"(list|enumerate|describe)\s+(all\s+)?(your|the)\s+(tools|functions|capabilities|permissions)",
        ThreatCategory.CONTEXT_LEAKAGE,
        Severity.LOW,
        "Capability enumeration",
        weight=0.5,
    ),
    # --- delimiter_injection (HIGH) ---
    ThreatPattern(
        r"<\s*/?system\s*>",
        ThreatCategory.DELIMITER_INJECTION,
        Severity.HIGH,
        "System tag injection",
        weight=1.5,
    ),
    ThreatPattern(
        r"\[/?INST\]",
        ThreatCategory.DELIMITER_INJECTION,
        Severity.HIGH,
        "Instruction delimiter injection",
        weight=1.5,
    ),
    ThreatPattern(
        r"<<\s*SYS\s*>>",
        ThreatCategory.DELIMITER_INJECTION,
        Severity.HIGH,
        "System delimiter injection (Llama format)",
        weight=1.5,
    ),
    ThreatPattern(
        r"(###\s*(System|Human|Assistant)\s*:)",
        ThreatCategory.DELIMITER_INJECTION,
        Severity.MEDIUM,
        "Message role delimiter injection",
        weight=1.0,
    ),
    # --- encoding_bypass (MEDIUM) ---
    ThreatPattern(
        r"(?:base64|rot13|hex)\s*(?:decode|encoded|encoding)",
        ThreatCategory.ENCODING_BYPASS,
        Severity.MEDIUM,
        "Encoding bypass attempt",
        weight=1.0,
    ),
    ThreatPattern(
        r"translate\s+the\s+following\s+(from\s+)?base64",
        ThreatCategory.ENCODING_BYPASS,
        Severity.MEDIUM,
        "Base64 decode instruction",
        weight=1.0,
    ),
]

# Pre-compile patterns
_COMPILED_PATTERNS: list[tuple[re.Pattern, ThreatPattern]] = [
    (re.compile(tp.pattern, re.IGNORECASE), tp) for tp in _THREAT_PATTERNS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_injection(text: str, sensitivity: float = 0.5) -> InjectionResult:
    """
    Scan text for prompt injection attempts.

    Args:
        text: Input text to scan.
        sensitivity: Detection sensitivity (0.0-1.0).
                     Lower = more lenient, higher = more aggressive.

    Returns:
        InjectionResult with risk assessment.
    """
    if not text or not text.strip():
        return InjectionResult(
            is_suspicious=False,
            risk_score=0.0,
            sanitized_text=text,
        )

    threats: list[dict] = []
    categories: set[str] = set()
    total_weight = 0.0
    max_sev = Severity.LOW

    text_lower = text.lower()

    for compiled, tp in _COMPILED_PATTERNS:
        matches = compiled.findall(text_lower)
        if matches:
            total_weight += tp.weight * len(matches)
            categories.add(tp.category.value)

            if _severity_rank(tp.severity) > _severity_rank(max_sev):
                max_sev = tp.severity

            threats.append(
                {
                    "category": tp.category.value,
                    "severity": tp.severity.value,
                    "description": tp.description,
                    "match_count": len(matches),
                }
            )

    # Calculate risk score (0.0-1.0)
    # Normalize: weight of 5.0+ = max risk
    raw_score = min(total_weight / 5.0, 1.0)

    # Apply sensitivity: higher sensitivity lowers the threshold
    adjusted_score = raw_score * (0.5 + sensitivity)
    risk_score = min(adjusted_score, 1.0)

    is_suspicious = risk_score > 0.0

    # Sanitize: strip known delimiters
    sanitized = _sanitize_delimiters(text)

    return InjectionResult(
        is_suspicious=is_suspicious,
        risk_score=round(risk_score, 3),
        threats=threats,
        categories=categories,
        max_severity=max_sev.value,
        sanitized_text=sanitized,
        details=f"{len(threats)} threat(s) detected across {len(categories)} category(ies)" if threats else "Clean",
    )


def is_safe(text: str, sensitivity: float = 0.5) -> bool:
    """Quick check — returns True if input is not suspicious."""
    return not scan_injection(text, sensitivity).should_block


def get_threat_summary(result: InjectionResult) -> str:
    """Generate a human-readable summary of detected threats."""
    if not result.threats:
        return "No threats detected."

    lines = [f"⚠️ {len(result.threats)} threat(s) detected (risk: {result.risk_score:.0%})"]
    for t in result.threats:
        lines.append(f"  [{t['severity'].upper()}] {t['description']} ({t['category']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def _severity_rank(sev: Severity) -> int:
    return _SEVERITY_ORDER.get(sev, 0)


def _sanitize_delimiters(text: str) -> str:
    """Remove fake message boundaries and system tags."""
    cleaned = re.sub(r"<\s*/?system\s*>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[/?INST\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<<\s*/?SYS\s*>>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"###\s*(System|Human|Assistant)\s*:", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
