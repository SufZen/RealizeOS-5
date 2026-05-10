"""Installation package smoke tests for RealizeOS V5."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from realize_core.scaffold import scaffold_venture

REPO_ROOT = Path(__file__).resolve().parents[1]
LITE_ROOT = REPO_ROOT / "realize_lite"

FABRIC_DIRS = [
    "F-foundations",
    "A-agents",
    "B-brain",
    "R-routines",
    "R-routines/skills",
    "I-insights",
    "C-creations",
]

REQUIRED_FILES = [
    "F-foundations/venture-identity.md",
    "F-foundations/venture-voice.md",
    "A-agents/_README.md",
    "A-agents/orchestrator.md",
    "A-agents/writer.md",
    "A-agents/reviewer.md",
    "A-agents/analyst.md",
    "B-brain/domain-knowledge.md",
    "B-brain/market-notes.md",
    "R-routines/state-map.md",
    "R-routines/skills/client-proposal.yaml",
    "R-routines/skills/content-pipeline.yaml",
    "R-routines/skills/email-campaign.yaml",
    "R-routines/skills/research-workflow.yaml",
    "R-routines/skills/social-media.yaml",
    "R-routines/skills/weekly-review.yaml",
    "I-insights/learning-log.md",
    "C-creations/README.md",
]


def assert_full_venture_structure(venture_dir: Path):
    for relative in FABRIC_DIRS:
        assert (venture_dir / relative).is_dir(), f"Missing directory: {relative}"
    for relative in REQUIRED_FILES:
        assert (venture_dir / relative).is_file(), f"Missing file: {relative}"


def test_lite_package_contains_legacy_starter_ventures():
    for key in ("my-business-1", "my-business-2", "my-business-3"):
        assert_full_venture_structure(LITE_ROOT / "systems" / key)


def test_python_init_installs_full_lite_payload(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "init",
            "--template",
            "consulting",
            "--directory",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert_full_venture_structure(tmp_path / "systems" / "my-business-1")


def test_python_init_is_safe_under_windows_console_encoding(tmp_path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "init",
            "--template",
            "consulting",
            "--directory",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Created .env" in result.stdout
    assert_full_venture_structure(tmp_path / "systems" / "my-business-1")


def test_scaffold_venture_uses_user_defined_safe_folder_slug(tmp_path):
    (tmp_path / "realize-os.yaml").write_text("systems: []\n", encoding="utf-8")

    stats = scaffold_venture(
        project_root=tmp_path,
        key="my-saas",
        name="My SaaS",
        description="Custom named venture",
    )

    assert stats["created"] is True
    assert stats["files_created"] >= len(REQUIRED_FILES)
    assert_full_venture_structure(tmp_path / "systems" / "my-saas")

    config = yaml.safe_load((tmp_path / "realize-os.yaml").read_text(encoding="utf-8"))
    system = next(system for system in config["systems"] if system["key"] == "my-saas")
    assert system["name"] == "My SaaS"
    assert system["directory"] == "systems/my-saas"


@pytest.mark.parametrize("key", ["My SaaS", "../escape", "client_work", "-bad", "bad-", "con"])
def test_scaffold_venture_rejects_unsafe_folder_slugs(tmp_path, key):
    (tmp_path / "realize-os.yaml").write_text("systems: []\n", encoding="utf-8")

    with pytest.raises(ValueError):
        scaffold_venture(project_root=tmp_path, key=key, name="Unsafe")

    assert not (tmp_path / "systems").exists()
