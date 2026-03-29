"""
Tests for End-to-End Eval Harness — Intent 4.2.

Covers:
- EvalCase, EvalSuite, EvalReport models
- YAML loading from sample suites
- Score calculations and pattern matching
- EvalRunner execution
"""

from __future__ import annotations

from pathlib import Path

import pytest
from realize_core.eval.harness import (
    EvalCase,
    EvalDimension,
    EvalReport,
    EvalResult,
    EvalRunner,
    EvalSuite,
    load_eval_suite,
    score_eval_case,
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestEvalCase:
    def test_create_minimal(self):
        case = EvalCase(name="test", prompt="Hello")
        assert case.name == "test"
        assert case.prompt == "Hello"
        assert case.expected_tools == []
        assert case.expected_patterns == []

    def test_create_full(self):
        case = EvalCase(
            name="full_test",
            prompt="Do thing",
            expected_tools=["web_search"],
            expected_patterns=["result.*found"],
            dimensions=[EvalDimension("accuracy", 2.0)],
            tags=["integration"],
        )
        assert len(case.expected_tools) == 1
        assert len(case.dimensions) == 1
        assert case.dimensions[0].weight == 2.0


class TestEvalResult:
    def test_overall_score(self):
        case = EvalCase(name="t", prompt="p")
        result = EvalResult(case)
        result.scores = {"a": 0.8, "b": 1.0}
        assert result.overall_score == pytest.approx(0.9)

    def test_serialization(self):
        case = EvalCase(name="t", prompt="p")
        result = EvalResult(case)
        result.passed = True
        d = result.to_dict()
        assert d["case"] == "t"
        assert d["passed"] is True


class TestEvalReport:
    def test_pass_rate(self):
        case1 = EvalCase(name="c1", prompt="p1")
        case2 = EvalCase(name="c2", prompt="p2")
        r1 = EvalResult(case1)
        r1.passed = True
        r2 = EvalResult(case2)
        r2.passed = False
        report = EvalReport("suite", [r1, r2])
        assert report.pass_rate == 0.5

    def test_summary(self):
        report = EvalReport("test_suite")
        s = report.summary()
        assert "test_suite" in s

    def test_empty_report(self):
        report = EvalReport("empty")
        assert report.pass_rate == 0.0
        assert report.avg_score == 0.0


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestLoadEvalSuite:
    def test_load_agency_suite(self):
        path = Path(__file__).parent.parent / "realize_core" / "eval" / "suites" / "agency_eval.yaml"
        if not path.exists():
            pytest.skip("Agency suite not found")
        suite = load_eval_suite(path)
        assert suite is not None
        assert suite.name == "Agency Eval Suite"
        assert len(suite.cases) == 3

    def test_load_saas_suite(self):
        path = Path(__file__).parent.parent / "realize_core" / "eval" / "suites" / "saas_eval.yaml"
        if not path.exists():
            pytest.skip("SaaS suite not found")
        suite = load_eval_suite(path)
        assert suite is not None
        assert suite.name == "SaaS Eval Suite"
        assert len(suite.cases) == 3

    def test_load_custom(self, tmp_path):
        import yaml

        suite_yaml = tmp_path / "eval.yaml"
        suite_yaml.write_text(
            yaml.dump(
                {
                    "name": "Test Suite",
                    "cases": [
                        {
                            "name": "greeting",
                            "prompt": "Say hi",
                            "expected_patterns": ["hi", "hello"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        suite = load_eval_suite(suite_yaml)
        assert suite is not None
        assert len(suite.cases) == 1
        assert suite.cases[0].expected_patterns == ["hi", "hello"]

    def test_missing_file(self, tmp_path):
        assert load_eval_suite(tmp_path / "missing.yaml") is None

    def test_invalid_yaml(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("[[[bad", encoding="utf-8")
        assert load_eval_suite(p) is None


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class TestScorer:
    def test_pattern_match(self):
        case = EvalCase(
            name="test",
            prompt="Hello",
            expected_patterns=["hello", "world"],
        )
        result = score_eval_case(case, "Hello World!")
        assert result.scores["pattern_match"] == 1.0
        assert result.passed is True

    def test_partial_match(self):
        case = EvalCase(
            name="test",
            prompt="Hello",
            expected_patterns=["hello", "mars"],
        )
        result = score_eval_case(case, "Hello Earth")
        assert result.scores["pattern_match"] == 0.5

    def test_tool_accuracy(self):
        case = EvalCase(
            name="test",
            prompt="Search",
            expected_tools=["web_search", "crm"],
        )
        result = score_eval_case(case, "Found it", ["web_search"])
        assert result.scores["tool_accuracy"] == 0.5

    def test_no_expectations(self):
        case = EvalCase(name="test", prompt="Hello")
        result = score_eval_case(case, "Hi there")
        assert result.scores["tool_accuracy"] == 1.0
        assert result.scores["pattern_match"] == 1.0
        assert result.passed is True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestEvalRunner:
    def test_run_empty_suite(self):
        runner = EvalRunner()
        suite = EvalSuite("empty")
        report = runner.run_suite(suite)
        assert len(report.results) == 0
        assert report.pass_rate == 0.0

    def test_run_with_mock_agent(self):
        runner = EvalRunner()
        suite = EvalSuite(
            "test",
            cases=[
                EvalCase(
                    name="greeting",
                    prompt="Hello",
                    expected_patterns=["hello", "hi"],
                ),
            ],
        )
        report = runner.run_suite(suite, agent_fn=lambda p: f"hi there, you said: {p}")
        assert len(report.results) == 1
        assert report.results[0].passed is True

    def test_latest_report(self):
        runner = EvalRunner()
        assert runner.latest_report is None
        suite = EvalSuite("test")
        runner.run_suite(suite)
        assert runner.latest_report is not None

    def test_agent_error_handling(self):
        runner = EvalRunner()
        suite = EvalSuite(
            "fail",
            cases=[
                EvalCase(name="crash", prompt="Fail"),
            ],
        )

        def bad_agent(prompt):
            raise RuntimeError("Agent crashed")

        report = runner.run_suite(suite, agent_fn=bad_agent)
        assert len(report.results) == 1
        assert report.results[0].passed is False
        assert len(report.results[0].errors) > 0
