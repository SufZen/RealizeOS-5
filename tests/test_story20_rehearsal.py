"""STORY-20 rehearsal kit: Google ids, the read-only preflight and the Google sign-in helpers."""

from __future__ import annotations

import csv
import json
import urllib.parse
from pathlib import Path

import pytest
import yaml
from realize_core.demo_rehearsal import PLACEHOLDER, STORYLINE, preflight, set_demo_ids
from realize_core.demo_seed import DEMO_KEY, seed_webinar_demo
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema
from realize_core.tools.google_signin import (
    SignInError,
    build_auth_url,
    parse_callback,
    pkce_pair,
    token_file_data,
)

SHEET = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
DOC = "1ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"
KIT = Path(__file__).resolve().parent.parent / "templates" / "demos" / "tower-b-he-google"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "realize-os.yaml").write_text(
        "features:\n  agent_tools: true\n  enforce_gates: true\n  cite_sources: true\nsystems: []\n",
        encoding="utf-8",
    )
    seed_webinar_demo(tmp_path)
    return tmp_path


def _skill_vars(project) -> dict:
    out = {}
    for path in (project / "systems" / DEMO_KEY / "R-routines" / "skills").glob("*.yaml"):
        out.update(yaml.safe_load(path.read_text(encoding="utf-8"))["variables"])
    return out


class TestSetIds:
    def test_fills_every_google_id_and_keeps_the_rest(self, project):
        changed = set_demo_ids(project, SHEET, DOC)
        assert len(changed) == 3
        variables = _skill_vars(project)
        assert variables["tender_doc_id"] == DOC
        for name in ("register_sheet_id", "milestones_sheet_id", "payments_sheet_id", "budget_sheet_id"):
            assert variables[name] == SHEET
        assert variables["payments_range"] == "Payments"
        text = (project / "systems" / DEMO_KEY / "R-routines" / "skills" / "payment-milestone-check.yaml").read_text(
            encoding="utf-8"
        )
        assert PLACEHOLDER not in text
        assert text.startswith("# Contractor payment request")  # comments survive

    def test_running_twice_replaces_the_old_ids(self, project):
        set_demo_ids(project, SHEET, DOC)
        set_demo_ids(project, SHEET[::-1], DOC)
        assert _skill_vars(project)["milestones_sheet_id"] == SHEET[::-1]

    @pytest.mark.parametrize("bad", ["", "short", 'x" injected', "https://docs.google.com/x"])
    def test_rejects_values_that_are_not_ids(self, project, bad):
        with pytest.raises(ValueError):
            set_demo_ids(project, bad, DOC)

    def test_needs_a_seeded_venture(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            set_demo_ids(tmp_path, SHEET, DOC)


class FakeGoogle(BaseTool):
    """Reads return text; records every call so the test can prove nothing was written."""

    name = "fake_google"
    description = "fake"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self, unreadable_doc=False):
        self.calls: list[tuple[str, dict]] = []
        self.unreadable_doc = unreadable_doc

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [ToolSchema(n, n, obj) for n in ("sheets_read", "sheets_append", "drive_read_content")]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append((action, params))
        if action == "drive_read_content" and self.unreadable_doc:
            return ToolResult.ok(output='{"error": "Cannot read content of this file type"}')
        return ToolResult.ok(output=f"{action} {params}")


@pytest.fixture
def google(monkeypatch):
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    monkeypatch.setattr("realize_core.tools.google_auth.has_stored_credentials", lambda: True)
    tool = FakeGoogle()
    tr.get_tool_registry().register(tool)
    return tool


@pytest.fixture
def presenter(project):
    (project / "users.yaml").write_text(
        f'users:\n  - email: dana@demo.io\n    role: operator\n    ventures: [{DEMO_KEY}]\n    password_hash: "$2b$12$x"\n',
        encoding="utf-8",
    )


def _by_name(checks):
    return {c.name: c for c in checks}


class TestPreflight:
    @pytest.mark.asyncio
    async def test_everything_ready(self, project, google, presenter, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        set_demo_ids(project, SHEET, DOC)
        checks = await preflight(project)
        assert [c.name for c in checks if not c.ok] == []
        assert {a for a, _ in google.calls} == {"sheets_read", "drive_read_content"}  # read-only

    @pytest.mark.asyncio
    async def test_reports_what_to_fix(self, project, google, monkeypatch):
        for name in ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        checks = _by_name(await preflight(project))
        assert not checks["LLM API key"].ok
        assert not checks["Google ids set in skills"].ok
        assert not checks["Presenter account"].ok
        assert not checks["Tab: Milestones"].ok
        assert "set-ids" in checks["Google ids set in skills"].fix
        assert google.calls == []  # nothing is called before the ids are set

    @pytest.mark.asyncio
    async def test_storyline_triggers_the_expected_skills(self, project, google):
        checks = _by_name(await preflight(project))
        for case, _message, _expected in STORYLINE:
            assert checks[f"Storyline: {case}"].ok, checks[f"Storyline: {case}"].detail

    @pytest.mark.asyncio
    async def test_flags_off_are_reported(self, project, google):
        (project / "realize-os.yaml").write_text(
            (project / "realize-os.yaml")
            .read_text(encoding="utf-8")
            .replace("enforce_gates: true", "enforce_gates: false"),
            encoding="utf-8",
        )
        checks = _by_name(await preflight(project))
        assert not checks["Feature flags"].ok
        assert "enforce_gates" in checks["Feature flags"].detail

    @pytest.mark.asyncio
    async def test_unreadable_tender_file(self, project, google):
        google.unreadable_doc = True
        set_demo_ids(project, SHEET, DOC)
        checks = _by_name(await preflight(project))
        assert not checks["Tender document"].ok
        assert "Google Doc" in checks["Tender document"].detail

    @pytest.mark.asyncio
    async def test_no_google_token(self, project, google, monkeypatch):
        monkeypatch.setattr("realize_core.tools.google_auth.has_stored_credentials", lambda: False)
        checks = _by_name(await preflight(project))
        assert not checks["Google sign-in"].ok
        assert "google_signin.py" in checks["Google sign-in"].fix

    @pytest.mark.asyncio
    async def test_missing_venture_stops_early(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "realize-os.yaml").write_text("systems: []\n", encoding="utf-8")
        checks = await preflight(tmp_path)
        assert not checks[0].ok
        assert not any(c.name.startswith(("Storyline", "Tab", "LLM")) for c in checks)


@pytest.fixture
def packs_project(tmp_path, monkeypatch):
    """The demo created with features.packs on: it links the developer pack (STORY-43)."""
    from realize_core.packs import clear_cache
    from realize_core.skills import detector

    clear_cache()
    monkeypatch.setattr(detector, "_loaded_skills", {})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "realize-os.yaml").write_text(
        "features:\n  agent_tools: true\n  enforce_gates: true\n  cite_sources: true\n  packs: true\nsystems: []\n",
        encoding="utf-8",
    )
    seed_webinar_demo(tmp_path)
    yield tmp_path
    clear_cache()


class TestWithPacksOn:
    """The rehearsal kit works when the demo's skills come from the developer pack."""

    def test_set_ids_writes_the_firm_settings(self, packs_project):
        venture = packs_project / "systems" / DEMO_KEY
        assert list((venture / "R-routines" / "skills").glob("*.yaml")) == []
        assert set_demo_ids(packs_project, SHEET, DOC) == ["skill-settings.yaml"]
        settings = yaml.safe_load(
            (venture / "F-foundations" / "overrides" / "skill-settings.yaml").read_text(encoding="utf-8")
        )
        assert settings["tender_requirements_register"]["variables"] == {
            "tender_doc_id": DOC,
            "register_sheet_id": SHEET,
        }
        assert settings["payment_milestone_check"]["variables"]["payments_sheet_id"] == SHEET
        assert "דרישת תשלום" in settings["payment_milestone_check"]["triggers"]

    @pytest.mark.asyncio
    async def test_everything_ready(self, packs_project, google, monkeypatch):
        (packs_project / "users.yaml").write_text(
            f"users:\n  - email: dana@demo.io\n    role: operator\n    ventures: [{DEMO_KEY}]\n"
            f'    password_hash: "$2b$12$x"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert not _by_name(await preflight(packs_project))["Google ids set in skills"].ok
        set_demo_ids(packs_project, SHEET, DOC)
        checks = await preflight(packs_project)
        assert [c.name for c in checks if not c.ok] == []
        # The pack's ranges with the firm's ids, read-only.
        assert ("sheets_read", {"spreadsheet_id": SHEET, "range": "Milestones"}) in google.calls
        assert {a for a, _ in google.calls} == {"sheets_read", "drive_read_content"}


class TestSheetKit:
    """The import files match what the skills read and write."""

    def test_tabs_named_like_the_skill_ranges(self):
        ranges = {"Requirements", "Milestones", "Payments", "Summary"}
        assert {p.stem for p in KIT.glob("*.csv")} == ranges

    def test_milestones_match_the_contract(self):
        rows = list(csv.reader((KIT / "Milestones.csv").open(encoding="utf-8")))
        milestones = [r for r in rows[1:] if r[0].isdigit()]
        assert len(milestones) == 8
        assert sum(int(r[3]) for r in milestones) == 3_600_000
        assert milestones[3][3] == "360000"

    def test_summary_totals_add_up(self):
        rows = list(csv.reader((KIT / "Summary.csv").open(encoding="utf-8")))
        lines, total = rows[1:8], rows[8]
        for col in (1, 2, 3):
            assert sum(int(r[col]) for r in lines) == int(total[col])

    def test_output_tabs_have_the_columns_the_skills_write(self):
        payments = next(csv.reader((KIT / "Payments.csv").open(encoding="utf-8")))
        requirements = next(csv.reader((KIT / "Requirements.csv").open(encoding="utf-8")))
        assert len(payments) == 7  # date, contractor, milestone, requested, supported, verdict, missing
        assert len(requirements) == 6  # section, requirement, mandatory, owner, due, source

    def test_tender_fits_what_drive_returns(self):
        text = (KIT / "tender-document.txt").read_text(encoding="utf-8")
        assert len(text) < 8000  # drive_read_content truncates at 8,000 characters
        assert "נתוני הדגמה" in text


class TestGoogleSignIn:
    def test_auth_url_asks_for_an_offline_pkce_grant(self):
        verifier, challenge = pkce_pair()
        assert verifier != challenge
        assert "=" not in challenge
        url = build_auth_url("cid.apps", "http://127.0.0.1:5555/", "st8", challenge)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert query["access_type"] == ["offline"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == ["http://127.0.0.1:5555/"]
        assert "https://www.googleapis.com/auth/spreadsheets" in query["scope"][0]

    def test_callback_returns_the_code(self):
        assert parse_callback("/?state=st8&code=abc", "st8") == "abc"

    @pytest.mark.parametrize(
        ("path", "message"),
        [
            ("/?state=other&code=abc", "state"),
            ("/?error=access_denied&state=st8", "refused"),
            ("/?state=st8", "no authorization"),
        ],
    )
    def test_callback_refusals(self, path, message):
        with pytest.raises(SignInError, match=message):
            parse_callback(path, "st8")

    def test_token_file_matches_what_google_auth_reads(self):
        data = token_file_data({"access_token": "a", "refresh_token": "r", "expires_in": 3600}, now=1000)
        assert data["access_token"] == "a"
        assert data["refresh_token"] == "r"
        assert data["expiry_date"] == (1000 + 3600) * 1000
        json.dumps(data)

    def test_missing_refresh_token_is_an_error(self):
        with pytest.raises(SignInError, match="refresh token"):
            token_file_data({"access_token": "a"})

    def test_sign_in_needs_client_secrets(self, tmp_path, monkeypatch):
        from realize_core.tools import google_signin

        monkeypatch.setattr(google_signin, "_load_client_config", lambda: {})
        with pytest.raises(SignInError, match="client_secrets"):
            google_signin.sign_in(tokens_path=tmp_path / "t.json", open_browser=False, timeout=0.1)


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX permission bits")
def test_token_file_is_owner_only(tmp_path):
    import os
    import stat

    from realize_core.tools.google_signin import write_private

    path = tmp_path / "creds" / "tokens.json"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    os.chmod(path, 0o644)
    write_private(path, "{}")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8") == "{}"


def test_write_private_creates_the_folder(tmp_path):
    from realize_core.tools.google_signin import write_private

    path = tmp_path / "new" / "tokens.json"
    write_private(path, '{"a": 1}')
    assert path.read_text(encoding="utf-8") == '{"a": 1}'
