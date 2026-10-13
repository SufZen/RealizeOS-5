"""The trust matrix shows where packs tightened a venture's trust (spec 010 §3.1).

``GET /api/trust`` with ``features.packs`` on adds, per visible venture and
action, the ladder's decision, the effective one and the pack or firm
default that tightened it; values that would loosen it are ignored and
listed as warnings. The matrix and the gate share one implementation
(:func:`realize_core.packs.trust.explain_with`), so they can't disagree.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

VENTURE = "acme-co"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yaml(path: Path, data) -> None:
    _write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


@pytest.fixture
def kb(tmp_path: Path, monkeypatch) -> Path:
    from realize_core.packs import clear_cache, loader

    packs_root = tmp_path / "packs"
    acme = packs_root / "profession" / "acme"
    _yaml(acme / "pack.yaml", {"id": "acme", "kind": "profession", "version": "0.1.0", "title": "Acme"})
    _yaml(acme / "trust.yaml", {"ledger_append": "approve", "gmail_send": "auto", "drive_move": "sometimes"})
    zz = packs_root / "market" / "zz"
    _yaml(zz / "pack.yaml", {"id": "zz", "kind": "market", "version": "0.2.0", "verification": {"level": 1}})
    _yaml(zz / "trust.yaml", {"ledger_read": "block", "send_email": "approve"})

    monkeypatch.delenv("REALIZE_PACKS_PATH", raising=False)
    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    monkeypatch.setattr(loader, "_warned", set())
    clear_cache()
    root = tmp_path / "kb"
    venture = root / "systems" / VENTURE
    _yaml(venture / "packs.yaml", {"profession": ["acme"], "market": ["zz"]})
    _yaml(venture / "F-foundations" / "overrides" / "trust.yaml", {"data_write": "block"})
    (root / "systems" / "plain").mkdir(parents=True)
    yield root
    clear_cache()


def _config(packs: bool, level: int = 5) -> dict:
    config = {
        "systems": [
            {"key": VENTURE, "directory": f"systems/{VENTURE}"},
            {"key": "plain", "directory": "systems/plain"},
        ],
        "trust": {"level": level},
    }
    if packs:
        config["features"] = {"packs": True}
    return config


def _rows(matrix: dict) -> dict[str, dict]:
    return {r["action"]: r for r in matrix["actions"]}


# ---------------------------------------------------------------------------
# The matrix for one venture
# ---------------------------------------------------------------------------


def test_each_action_shows_the_ladder_the_effective_decision_and_its_source(kb):
    from realize_core.packs.trust import venture_trust_matrix

    rows = _rows(venture_trust_matrix(_config(True, level=5), kb / "systems" / VENTURE))

    # A tool action the ladder has no rule for: shown as a write, tightened by the profession pack.
    ledger = rows["ledger_append"]
    assert (ledger["ladder"], ledger["effective"], ledger["tightened"]) == ("auto", "approve", True)
    assert ledger["governed_by"] == "unknown_write"
    assert ledger["source"] == {
        "layer": "profession",
        "pack": "acme@0.1.0",
        "key": "ledger_append",
        "value": "approve",
        "label": "profession pack acme@0.1.0",
    }
    # The market pack blocks a read tool outright.
    assert rows["ledger_read"]["effective"] == "block"
    assert rows["ledger_read"]["source"]["label"] == "market pack zz@0.2.0"
    # A governance action: the firm's own override blocks every data write.
    assert (rows["data_write"]["ladder"], rows["data_write"]["effective"]) == ("auto", "block")
    assert rows["data_write"]["source"]["label"] == "firm overrides"
    assert rows["data_write"]["source"]["pack"] is None
    # The market pack makes sending email need approval at level 5.
    assert (rows["send_email"]["ladder"], rows["send_email"]["effective"]) == ("auto", "approve")
    # gmail_send falls under send_email: the market pack's governance default reaches it too.
    assert rows["gmail_send"]["governed_by"] == "send_email"
    assert rows["gmail_send"]["effective"] == "approve"
    # Untouched actions keep the ladder's decision, with no source.
    assert rows["phone_call"] == {
        "action": "phone_call",
        "governed_by": None,
        "ladder": "approve",
        "effective": "approve",
        "tightened": False,
        "source": None,
        "ignored": [],
    }


def test_ignored_loosenings_and_unusable_values_are_warnings(kb):
    from realize_core.packs.trust import venture_trust_matrix

    matrix = venture_trust_matrix(_config(True, level=3), kb / "systems" / VENTURE)
    rows = _rows(matrix)

    # At level 3 sending email needs approval; the profession pack's "auto" is ignored.
    gmail = rows["gmail_send"]
    assert (gmail["ladder"], gmail["effective"]) == ("approve", "approve")
    assert gmail["ignored"] == [
        {
            "layer": "profession",
            "pack": "acme@0.1.0",
            "key": "gmail_send",
            "value": "auto",
            "label": "profession pack acme@0.1.0",
            "reason": "loosen",
        }
    ]
    assert (
        "profession pack acme@0.1.0 would loosen gmail_send from approve to auto; ignored (packs only tighten trust)"
        in matrix["warnings"]
    )
    assert any("sets trust 'sometimes' for drive_move" in w for w in matrix["warnings"])
    assert len(matrix["warnings"]) == len(set(matrix["warnings"]))  # each once


def test_a_firm_disable_returns_the_action_to_the_ladder(kb):
    from realize_core.packs import clear_cache
    from realize_core.packs.trust import venture_trust_matrix

    _yaml(kb / "systems" / VENTURE / "F-foundations" / "overrides" / "disable.yaml", ["ledger_append"])
    clear_cache()
    rows = _rows(venture_trust_matrix(_config(True, level=5), kb / "systems" / VENTURE))
    assert (rows["ledger_append"]["effective"], rows["ledger_append"]["source"]) == ("auto", None)


def test_the_matrix_agrees_with_the_gate(kb, tmp_path):
    """Same answer as the ToolGate for every row: one implementation, no drift."""
    from realize_core.db.migrations import run_migrations
    from realize_core.db.schema import init_schema, set_db_path
    from realize_core.governance.context import tool_call_context
    from realize_core.governance.tool_gate import ToolGate
    from realize_core.packs.trust import venture_trust_matrix

    db = tmp_path / "ops.db"
    init_schema(db)
    run_migrations(db)
    set_db_path(db)
    outcome = {"auto": "allow", "approve": "needs_approval", "block": "block"}
    try:
        for level in (1, 3, 5):
            config = _config(True, level=level)
            gate = ToolGate(config=config, kb_path=kb)
            for row in venture_trust_matrix(config, kb / "systems" / VENTURE)["actions"]:
                with tool_call_context(system_key=VENTURE, agent_key="estimator", user_id="dana"):
                    decided = gate.decide(row["action"], {}, is_destructive=True).outcome.value
                assert decided == outcome[row["effective"]], (level, row["action"])
    finally:
        set_db_path(None)


def test_the_gate_still_logs_what_it_ignores(kb, caplog):
    from realize_core.packs.trust import tighten

    caplog.set_level(logging.WARNING)
    assert tighten("approve", ["gmail_send", "send_email"], kb / "systems" / VENTURE) == "approve"
    assert "would loosen gmail_send from approve to auto; ignored" in caplog.text


# ---------------------------------------------------------------------------
# GET /api/trust
# ---------------------------------------------------------------------------


def _client(kb: Path, *, packs: bool, scopes: tuple[str, ...] = (), level: int = 5) -> TestClient:
    from realize_api.main import create_app
    from realize_core.config import build_systems_dict

    config = _config(packs, level=level)
    app = create_app()
    app.state.systems = build_systems_dict(config, kb)
    app.state.kb_path = kb
    app.state.config = config

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = "owner@acme.io"
        request.state.role = "owner"
        request.state.scopes = list(scopes)
        return await call_next(request)

    return TestClient(app)


def test_flag_off_the_trust_api_is_unchanged(kb):
    from realize_core.governance.trust_ladder import get_trust_matrix

    body = _client(kb, packs=False).get("/api/trust").json()
    assert set(body) == {"level", "actions"}
    assert body == {
        "level": 5,
        "actions": {
            k: {str(n): v for n, v in r.items()} for k, r in get_trust_matrix(_config(False))["actions"].items()
        },
    }


def test_flag_on_the_trust_api_shows_each_ventures_effective_decisions(kb):
    body = _client(kb, packs=True, level=3).get("/api/trust").json()

    assert body["level"] == 3
    assert set(body["ventures"]) == {VENTURE, "plain"}
    acme = body["ventures"][VENTURE]
    rows = _rows(acme)
    # At level 3 an unmapped write already needs approval: the pack's "approve" changes nothing.
    assert (rows["ledger_append"]["effective"], rows["ledger_append"]["source"]) == ("approve", None)
    assert rows["ledger_read"]["source"]["label"] == "market pack zz@0.2.0"
    assert rows["data_write"]["effective"] == "block"
    assert any("would loosen gmail_send" in w for w in acme["warnings"])
    assert {"layer": "market", "pack": "zz@0.2.0"} in acme["layers"]
    # A venture without packs: the ladder alone.
    plain = body["ventures"]["plain"]
    assert all(not r["tightened"] for r in plain["actions"])
    assert plain["warnings"] == []


def test_a_venture_limited_caller_gets_no_trust_matrix(kb):
    """The trust ladder spans every venture: the venture guard closes it to scoped callers."""
    assert _client(kb, packs=True, scopes=("venture:plain",)).get("/api/trust").status_code == 403
