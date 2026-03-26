"""
End-to-End Evaluation Harness — Behavioral testing for agents.

Provides a YAML-based eval framework for testing agent quality:
- Define eval cases: input prompt, expected tools, expected output patterns
- Run evaluations against agent configurations
- Score results per eval + per dimension
- Integrate with experiment tracker

CLI commands:
- ``realize eval run [--suite <path>]`` — run an eval suite
- ``realize eval report`` — show latest results
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eval models
# ---------------------------------------------------------------------------


class EvalDimension:
    """A scoring dimension for evaluation."""

    def __init__(self, name: str, weight: float = 1.0, description: str = ""):
        self.name = name
        self.weight = weight
        self.description = description


class EvalCase:
    """
    A single evaluation test case.

    Defined in YAML with:
    - prompt: input to send to agent
    - expected_tools: tools the agent should use
    - expected_patterns: regex patterns to match in output
    - dimensions: scoring dimensions and their expected behavior
    """

    def __init__(
        self,
        name: str,
        prompt: str,
        expected_tools: list[str] | None = None,
        expected_patterns: list[str] | None = None,
        dimensions: list[EvalDimension] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.name = name
        self.prompt = prompt
        self.expected_tools = expected_tools or []
        self.expected_patterns = expected_patterns or []
        self.dimensions = dimensions or []
        self.tags = tags or []
        self.metadata = metadata or {}


class EvalResult:
    """Result of running a single eval case."""

    def __init__(self, case: EvalCase):
        self.case = case
        self.output: str = ""
        self.tools_used: list[str] = []
        self.scores: dict[str, float] = {}
        self.passed: bool = False
        self.duration_ms: float = 0
        self.errors: list[str] = []
        self.created_at = datetime.now(timezone.utc)

    @property
    def overall_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.name,
            "passed": self.passed,
            "overall_score": round(self.overall_score, 3),
            "scores": self.scores,
            "tools_used": self.tools_used,
            "duration_ms": round(self.duration_ms, 1),
            "errors": self.errors,
            "created_at": self.created_at.isoformat(),
        }


class EvalSuite:
    """A collection of eval cases (loaded from YAML)."""

    def __init__(self, name: str, cases: list[EvalCase] | None = None, metadata: dict[str, Any] | None = None):
        self.name = name
        self.cases = cases or []
        self.metadata = metadata or {}

    def add_case(self, case: EvalCase):
        self.cases.append(case)


class EvalReport:
    """Aggregated results from running an eval suite."""

    def __init__(self, suite_name: str, results: list[EvalResult] | None = None):
        self.suite_name = suite_name
        self.results = results or []
        self.created_at = datetime.now(timezone.utc)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.overall_score for r in self.results) / len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite_name,
            "total_cases": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "pass_rate": round(self.pass_rate, 3),
            "avg_score": round(self.avg_score, 3),
            "results": [r.to_dict() for r in self.results],
            "created_at": self.created_at.isoformat(),
        }

    def summary(self) -> str:
        return (
            f"📊 Eval Report: {self.suite_name}\n"
            f"  Cases: {len(self.results)} | "
            f"Passed: {sum(1 for r in self.results if r.passed)} | "
            f"Failed: {sum(1 for r in self.results if not r.passed)}\n"
            f"  Pass Rate: {self.pass_rate:.1%} | Avg Score: {self.avg_score:.3f}"
        )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_eval_suite(path: Path) -> EvalSuite | None:
    """
    Load an eval suite from a YAML file.

    Expected format:
    ```yaml
    name: My Eval Suite
    cases:
      - name: test_greeting
        prompt: "Say hello"
        expected_patterns: ["hello", "hi"]
        expected_tools: []
        dimensions:
          - name: friendliness
            weight: 1.0
    ```
    """
    try:
        import yaml  # noqa: F811
    except ImportError:
        logger.error("PyYAML required for eval suite loading")
        return None

    if not path.exists():
        logger.warning("Eval suite not found: %s", path)
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            logger.warning("Invalid eval suite format: %s", path)
            return None

        suite = EvalSuite(
            name=data.get("name", path.stem),
            metadata=data.get("metadata", {}),
        )

        for case_data in data.get("cases", []):
            dimensions = []
            for dim in case_data.get("dimensions", []):
                dimensions.append(EvalDimension(
                    name=dim.get("name", "unknown"),
                    weight=dim.get("weight", 1.0),
                    description=dim.get("description", ""),
                ))

            case = EvalCase(
                name=case_data.get("name", "unnamed"),
                prompt=case_data.get("prompt", ""),
                expected_tools=case_data.get("expected_tools", []),
                expected_patterns=case_data.get("expected_patterns", []),
                dimensions=dimensions,
                tags=case_data.get("tags", []),
                metadata=case_data.get("metadata", {}),
            )
            suite.add_case(case)

        return suite

    except Exception as e:
        logger.error("Failed to load eval suite: %s", e)
        return None


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def score_eval_case(
    case: EvalCase,
    output: str,
    tools_used: list[str] | None = None,
) -> EvalResult:
    """
    Score a single eval case against actual output.

    Scoring dimensions:
    1. tool_accuracy: Did the agent use the expected tools?
    2. pattern_match: Does the output match expected patterns?
    3. completeness: Overall assessment based on all criteria
    """
    result = EvalResult(case)
    result.output = output
    result.tools_used = tools_used or []

    # Dimension 1: Tool accuracy
    if case.expected_tools:
        expected_set = set(case.expected_tools)
        used_set = set(result.tools_used)
        if expected_set:
            tool_score = len(expected_set & used_set) / len(expected_set)
        else:
            tool_score = 1.0
        result.scores["tool_accuracy"] = tool_score
    else:
        result.scores["tool_accuracy"] = 1.0

    # Dimension 2: Pattern matching
    if case.expected_patterns:
        matched = 0
        for pattern in case.expected_patterns:
            try:
                if re.search(pattern, output, re.IGNORECASE):
                    matched += 1
            except re.error:
                if pattern.lower() in output.lower():
                    matched += 1
        result.scores["pattern_match"] = matched / len(case.expected_patterns)
    else:
        result.scores["pattern_match"] = 1.0

    # Custom dimensions
    for dim in case.dimensions:
        if dim.name not in result.scores:
            result.scores[dim.name] = 1.0  # Default to pass

    # Determine pass/fail
    result.passed = result.overall_score >= 0.6

    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class EvalRunner:
    """
    Runs eval suites against agent configurations.

    Usage:
        runner = EvalRunner()
        report = runner.run_suite(suite, agent_fn)
    """

    def __init__(self):
        self._reports: list[EvalReport] = []

    def run_suite(
        self,
        suite: EvalSuite,
        agent_fn=None,
    ) -> EvalReport:
        """
        Run all cases in an eval suite.

        If agent_fn is provided, it will be called with each case prompt.
        If agent_fn is None, cases are scored against empty output
        (useful for testing the eval harness itself).
        """
        report = EvalReport(suite_name=suite.name)

        for case in suite.cases:
            start = time.monotonic()

            try:
                if agent_fn:
                    output = agent_fn(case.prompt)
                    tools_used = getattr(output, "tools_used", [])
                    output_text = str(output)
                else:
                    output_text = ""
                    tools_used = []

                result = score_eval_case(case, output_text, tools_used)
            except Exception as e:
                result = EvalResult(case)
                result.errors.append(str(e))
                result.passed = False

            result.duration_ms = (time.monotonic() - start) * 1000
            report.results.append(result)

        self._reports.append(report)
        return report

    @property
    def latest_report(self) -> EvalReport | None:
        return self._reports[-1] if self._reports else None

    @property
    def all_reports(self) -> list[EvalReport]:
        return list(self._reports)
