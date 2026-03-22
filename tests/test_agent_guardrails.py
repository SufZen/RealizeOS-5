"""
Tests for the guardrails module — safety constraints and verdict parsing.
"""

from realize_core.agents.base import GuardrailConfig
from realize_core.agents.guardrails import (
    Verdict,
    check_guardrails,
    has_advisory_violations,
    has_strict_violations,
    parse_verdict,
)

# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------

class TestParseVerdict:
    """Test PASS/FAIL parsing from free-text agent output."""

    # ---- PASS patterns ----

    def test_pass_keyword(self):
        result = parse_verdict("PASS — great work!")
        assert result.verdict == Verdict.PASS

    def test_approved_keyword(self):
        result = parse_verdict("Verdict: APPROVED\nExcellent quality.")
        assert result.verdict == Verdict.PASS

    def test_lgtm(self):
        result = parse_verdict("LGTM, ship it!")
        assert result.verdict == Verdict.PASS

    def test_verdict_pass_label(self):
        result = parse_verdict("Status: pass\nAll checks green.")
        assert result.verdict == Verdict.PASS

    # ---- FAIL patterns ----

    def test_fail_keyword(self):
        result = parse_verdict("FAIL — needs more detail in section 3.")
        assert result.verdict == Verdict.FAIL

    def test_rejected_keyword(self):
        result = parse_verdict("Verdict: REJECTED\nMissing citations.")
        assert result.verdict == Verdict.FAIL

    def test_revisions_needed(self):
        result = parse_verdict("REVISIONS NEEDED in paragraph 2.")
        assert result.verdict == Verdict.FAIL

    def test_not_approved(self):
        result = parse_verdict("NOT APPROVED — tone is too casual.")
        assert result.verdict == Verdict.FAIL

    # ---- UNKNOWN ----

    def test_empty_text(self):
        result = parse_verdict("")
        assert result.verdict == Verdict.UNKNOWN

    def test_ambiguous_text(self):
        result = parse_verdict("The content looks okay but could be improved.")
        assert result.verdict == Verdict.UNKNOWN

    # ---- FAIL takes precedence ----

    def test_fail_wins_over_pass_when_both_present(self):
        """If both PASS and FAIL appear, FAIL should win (conservative)."""
        text = "Initially I thought PASS but actually FAIL."
        result = parse_verdict(text)
        assert result.verdict == Verdict.FAIL

    # ---- Feedback extraction ----

    def test_extracts_feedback_after_verdict(self):
        result = parse_verdict("PASS\nGood job. Voice is consistent.")
        assert result.feedback  # Should have feedback text
        assert "Voice" in result.feedback or "Good" in result.feedback

    def test_confidence_is_set(self):
        result = parse_verdict("PASS")
        assert result.confidence > 0.5


# ---------------------------------------------------------------------------
# Guardrail checking
# ---------------------------------------------------------------------------

class TestCheckGuardrails:
    """Test guardrail violation detection."""

    def test_no_violations_clean_text(self):
        guardrails = [
            GuardrailConfig(
                name="no-sensitive-data",
                description="Never share confidential data externally",
                enforcement="strict",
            ),
        ]
        violations = check_guardrails("This is a clean response.", guardrails)
        assert len(violations) == 0

    def test_detects_email_in_sensitive_guardrail(self):
        guardrails = [
            GuardrailConfig(
                name="no-sensitive-data",
                description="Never share confidential or sensitive data",
                enforcement="strict",
            ),
        ]
        text = "Contact john@example.com for details."
        violations = check_guardrails(text, guardrails)
        assert len(violations) == 1
        assert violations[0].enforcement == "strict"

    def test_detects_ssn_pattern(self):
        guardrails = [
            GuardrailConfig(
                name="no-pii",
                description="Never include sensitive personal data",
                enforcement="strict",
            ),
        ]
        text = "SSN: 123-45-6789"
        violations = check_guardrails(text, guardrails)
        assert len(violations) == 1

    def test_detects_credit_card_pattern(self):
        guardrails = [
            GuardrailConfig(
                name="no-pii",
                description="Never include confidential financial data",
                enforcement="strict",
            ),
        ]
        text = "Card: 4111-1111-1111-1111"
        violations = check_guardrails(text, guardrails)
        assert len(violations) == 1

    def test_confirm_before_guardrail_does_not_trigger(self):
        """Advisory guardrails about confirmation should not block."""
        guardrails = [
            GuardrailConfig(
                name="confirm-external",
                description="Always confirm before sending external communications",
                enforcement="advisory",
            ),
        ]
        violations = check_guardrails("Send this email now.", guardrails)
        assert len(violations) == 0

    def test_empty_guardrails_no_violations(self):
        violations = check_guardrails("Any text here.", [])
        assert violations == []


# ---------------------------------------------------------------------------
# Violation helpers
# ---------------------------------------------------------------------------

class TestViolationHelpers:
    def test_has_strict_violations(self):
        from realize_core.agents.guardrails import GuardrailViolation
        violations = [
            GuardrailViolation("r1", "d1", "strict"),
            GuardrailViolation("r2", "d2", "advisory"),
        ]
        assert has_strict_violations(violations)

    def test_no_strict_violations(self):
        from realize_core.agents.guardrails import GuardrailViolation
        violations = [
            GuardrailViolation("r1", "d1", "advisory"),
        ]
        assert not has_strict_violations(violations)

    def test_has_advisory_violations(self):
        from realize_core.agents.guardrails import GuardrailViolation
        violations = [
            GuardrailViolation("r1", "d1", "advisory"),
        ]
        assert has_advisory_violations(violations)

    def test_empty_list(self):
        assert not has_strict_violations([])
        assert not has_advisory_violations([])
