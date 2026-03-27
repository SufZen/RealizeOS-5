"""Tests for the structured audit workflow."""

from __future__ import annotations

import json
from types import SimpleNamespace


def test_discover_workspace_state_flags_partial_init(tmp_path):
    systems_dir = tmp_path / "systems" / "alpha" / "A-agents"
    systems_dir.mkdir(parents=True)
    (systems_dir / "orchestrator.md").write_text("# Orchestrator", encoding="utf-8")

    from realize_core.config import discover_workspace_state

    state = discover_workspace_state(tmp_path)

    assert state["config_exists"] is False
    assert state["partially_initialized"] is True
    assert state["discovered_system_dirs"] == ["alpha"]
    assert state["unconfigured_system_dirs"] == ["alpha"]


def test_build_audit_report_has_all_blocks(tmp_path):
    (tmp_path / "systems" / "alpha").mkdir(parents=True)

    from realize_core.devmode.audit import build_audit_report

    report = build_audit_report(root=tmp_path, quick=True)

    assert len(report.blocks) == 8
    foundation = next(block for block in report.blocks if block.key == "foundation")
    assert any("realize-os.yaml" in finding for finding in foundation.current_failures)


def test_cmd_audit_json_output(tmp_path, capsys):
    (tmp_path / "systems" / "alpha").mkdir(parents=True)

    import cli

    cli.cmd_audit(SimpleNamespace(directory=str(tmp_path), quick=True, format="json"))

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["summary"]["partial_initialization"] is True
    assert len(payload["blocks"]) == 8
