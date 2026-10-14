"""Pure helpers of scripts/provider_smoke.py. The live smoke itself never runs in tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("provider_smoke", ROOT / "scripts" / "provider_smoke.py")
smoke = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = smoke  # dataclasses look their module up
_spec.loader.exec_module(smoke)


@pytest.mark.parametrize(
    ("path", "protected"),
    [
        ("D:/realization-demo", True),
        ("D:/realization-demo/RealizeOS-5", True),
        ("d:\\Realization-Demo\\RealizeOS-5\\data", True),
        ("D:/realization-demo/../elsewhere", False),
        ("D:/realization-demo-copy", False),
        ("D:/SufZen Gits/RealizeOS-5", False),
    ],
)
def test_the_live_demo_folder_is_refused(path, protected):
    assert smoke.is_protected(path) is protected


def test_a_real_payment_row_passes():
    row = [["2026-10-14", "קבלן הדגמה", "4", 360000, 342000, "PARTIAL", "אישור מפקח חתום"]]
    assert smoke.row_problems(row) == []


@pytest.mark.parametrize(
    "rows",
    [
        [["2026-10-14", "contractor", "milestone", 0, 0, "verdict", "missing evidence"]],
        [["{today}", "Demo Builders", "4", 1, 1, "PARTIAL", "ok"]],
        [["2026-10-14", "Demo Builders", "{check}", 1, 1, "PARTIAL", "ok"]],
        "not rows",
        [],
    ],
)
def test_template_rows_and_placeholders_fail(rows):
    assert smoke.row_problems(rows)
