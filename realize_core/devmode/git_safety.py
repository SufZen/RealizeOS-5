"""
Git safety net for Developer Mode.

Provides snapshot/rollback/diff operations so users can safely
let AI tools modify files with easy recovery.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Snapshot(NamedTuple):
    """A devmode git snapshot."""

    tag: str
    timestamp: str
    message: str


class GitSafety:
    """
    Git-based safety net for Developer Mode.

    Creates tagged snapshots before AI sessions and supports
    rollback to any previous snapshot.
    """

    TAG_PREFIX = "devmode/"

    def __init__(self, repo_root: Path | None = None):
        self.root = repo_root or Path.cwd()

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repo root."""
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=check,
        )

    def is_git_repo(self) -> bool:
        """Check if the current directory is a git repository."""
        result = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return result.returncode == 0

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        result = self._run("status", "--porcelain", check=False)
        return bool(result.stdout.strip())

    def create_snapshot(self, label: str = "", tool: str = "manual") -> str:
        """
        Create a git snapshot (commit + tag) of the current state.

        Args:
            label: Optional label for the snapshot.
            tool: Name of the AI tool about to be used.

        Returns:
            The tag name created.
        """
        if not self.is_git_repo():
            raise RuntimeError("Not a git repository")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag_name = f"{self.TAG_PREFIX}before-{tool}-{timestamp}"
        message = label or f"DevMode snapshot before {tool} session"

        # Stage and commit any uncommitted changes
        if self.has_changes():
            self._run("add", "-A")
            self._run("commit", "-m", f"[devmode] {message}", check=False)

        # Create the tag
        self._run("tag", "-a", tag_name, "-m", message, check=False)
        logger.info("Created snapshot: %s", tag_name)
        return tag_name

    def list_snapshots(self) -> list[Snapshot]:
        """List all devmode snapshots."""
        result = self._run(
            "tag", "-l", f"{self.TAG_PREFIX}*",
            "--sort=-creatordate",
            "--format=%(refname:short)|%(creatordate:iso-strict)|%(subject)",
            check=False,
        )
        snapshots = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                snapshots.append(Snapshot(tag=parts[0], timestamp=parts[1], message=parts[2]))
        return snapshots

    def rollback_to(self, tag: str) -> str:
        """
        Rollback the working tree to a snapshot.

        Creates a new snapshot of the current state first, then resets.

        Args:
            tag: The tag name to rollback to.

        Returns:
            The backup tag created before rollback.
        """
        # Safety: snapshot current state first
        backup_tag = self.create_snapshot(
            label=f"Auto-backup before rollback to {tag}",
            tool="rollback",
        )

        # Reset to the target tag
        self._run("reset", "--hard", tag)
        logger.info("Rolled back to: %s (backup: %s)", tag, backup_tag)
        return backup_tag

    def diff_since(self, tag: str | None = None) -> str:
        """
        Show changes since a snapshot.

        Args:
            tag: Tag to diff against. If None, uses the latest snapshot.

        Returns:
            Git diff output as string.
        """
        if tag is None:
            snapshots = self.list_snapshots()
            if not snapshots:
                return "No snapshots found."
            tag = snapshots[0].tag

        result = self._run("diff", tag, "--stat", check=False)
        return result.stdout or "No changes since snapshot."

    def files_changed_since(self, tag: str) -> list[str]:
        """List files changed since a snapshot."""
        result = self._run("diff", tag, "--name-only", check=False)
        return [f for f in result.stdout.strip().splitlines() if f]
