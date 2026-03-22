"""
Git-based experiment tracking for RealizeOS.

Records experiment definitions, results, and history in a JSON log file.
Optionally creates git commits for each experiment result to enable
point-in-time rollback.

Provides:
- ExperimentTracker: Main tracking class
- File-based persistence (data/experiments/)
- Experiment listing, filtering, and history
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from realize_core.optimizer.base import (
    BaseExperiment,
    ExperimentResult,
    ExperimentStatus,
    OptimizationDomain,
    OptimizationTarget,
)

logger = logging.getLogger(__name__)

# Default directory for experiment data
DEFAULT_EXPERIMENTS_DIR = Path("data/experiments")


@dataclass
class ExperimentRecord:
    """
    Complete record of an experiment: definition + results + metadata.
    """
    experiment: BaseExperiment
    results: list[ExperimentResult] = field(default_factory=list)
    git_commit: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "experiment": {
                "id": self.experiment.id,
                "name": self.experiment.name,
                "status": str(self.experiment.status),
                "description": self.experiment.description,
                "max_samples": self.experiment.max_samples,
                "min_improvement_pct": self.experiment.min_improvement_pct,
                "tags": self.experiment.tags,
                "target": {
                    "domain": str(self.experiment.target.domain),
                    "key": self.experiment.target.key,
                    "description": self.experiment.target.description,
                },
            },
            "results": [
                {
                    "experiment_id": r.experiment_id,
                    "status": str(r.status),
                    "control_score": r.control_score,
                    "candidate_score": r.candidate_score,
                    "improvement_pct": r.improvement_pct,
                    "sample_size": r.sample_size,
                    "details": r.details,
                }
                for r in self.results
            ],
            "git_commit": self.git_commit,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ExperimentRecord:
        """Deserialize from a dict."""
        exp_data = data.get("experiment", {})
        target_data = exp_data.get("target", {})

        target = OptimizationTarget(
            domain=OptimizationDomain(target_data.get("domain", "prompt")),
            key=target_data.get("key", ""),
            description=target_data.get("description", ""),
        )
        experiment = BaseExperiment(
            id=exp_data.get("id", ""),
            name=exp_data.get("name", ""),
            target=target,
            status=ExperimentStatus(exp_data.get("status", "pending")),
            description=exp_data.get("description", ""),
            max_samples=exp_data.get("max_samples", 100),
            min_improvement_pct=exp_data.get("min_improvement_pct", 5.0),
            tags=exp_data.get("tags", []),
        )

        results = []
        for r_data in data.get("results", []):
            results.append(ExperimentResult(
                experiment_id=r_data.get("experiment_id", ""),
                status=ExperimentStatus(r_data.get("status", "pending")),
                target=target,
                control_score=r_data.get("control_score", 0.0),
                candidate_score=r_data.get("candidate_score", 0.0),
                improvement_pct=r_data.get("improvement_pct", 0.0),
                sample_size=r_data.get("sample_size", 0),
                details=r_data.get("details", {}),
            ))

        return ExperimentRecord(
            experiment=experiment,
            results=results,
            git_commit=data.get("git_commit"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class ExperimentTracker:
    """
    File-based experiment tracker with optional git integration.

    Stores experiment records in a JSON log file and optionally creates
    git commits for each experiment result.

    Usage:
        tracker = ExperimentTracker()
        tracker.register(experiment)
        tracker.record_result(result)
        history = tracker.list_experiments()
    """

    def __init__(
        self,
        experiments_dir: Path | str | None = None,
        enable_git: bool = False,
    ):
        self._dir = Path(experiments_dir or DEFAULT_EXPERIMENTS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._dir / "experiment_log.json"
        self._enable_git = enable_git
        self._records: dict[str, ExperimentRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load existing experiment records from disk."""
        if not self._log_path.exists():
            return
        try:
            data = json.loads(self._log_path.read_text(encoding="utf-8"))
            for entry in data.get("experiments", []):
                record = ExperimentRecord.from_dict(entry)
                self._records[record.experiment.id] = record
            logger.info(f"Loaded {len(self._records)} experiment records")
        except Exception as e:
            logger.warning(f"Failed to load experiment log: {e}")

    def _save(self) -> None:
        """Persist all experiment records to disk."""
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "experiments": [r.to_dict() for r in self._records.values()],
        }
        self._log_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def register(self, experiment: BaseExperiment) -> ExperimentRecord:
        """
        Register a new experiment for tracking.

        Returns the created ExperimentRecord.
        """
        if experiment.id in self._records:
            logger.warning(f"Experiment {experiment.id} already registered, updating")

        now = datetime.now().isoformat()
        record = ExperimentRecord(
            experiment=experiment,
            created_at=now,
            updated_at=now,
        )
        self._records[experiment.id] = record
        self._save()
        logger.info(f"Registered experiment: {experiment.id} ({experiment.name})")
        return record

    def record_result(self, result: ExperimentResult) -> ExperimentRecord | None:
        """
        Record a result for an existing experiment.

        Appends the result, updates the experiment status, and optionally
        creates a git commit.
        """
        record = self._records.get(result.experiment_id)
        if not record:
            logger.warning(f"No experiment found for ID: {result.experiment_id}")
            return None

        record.results.append(result)
        record.experiment.status = result.status
        record.updated_at = datetime.now().isoformat()

        # Git commit if enabled
        if self._enable_git:
            commit_sha = self._git_commit(result)
            if commit_sha:
                record.git_commit = commit_sha

        self._save()
        logger.info(
            f"Recorded result for {result.experiment_id}: "
            f"{result.status} (improvement: {result.improvement_pct:+.1f}%)"
        )
        return record

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        """Get a specific experiment record."""
        return self._records.get(experiment_id)

    def list_experiments(
        self,
        status: ExperimentStatus | None = None,
        domain: OptimizationDomain | None = None,
        tag: str | None = None,
    ) -> list[ExperimentRecord]:
        """
        List experiments with optional filters.
        """
        records = list(self._records.values())

        if status:
            records = [r for r in records if r.experiment.status == status]
        if domain:
            records = [r for r in records if r.experiment.target.domain == domain]
        if tag:
            records = [r for r in records if tag in r.experiment.tags]

        return records

    def get_latest_result(self, experiment_id: str) -> ExperimentResult | None:
        """Get the most recent result for an experiment."""
        record = self._records.get(experiment_id)
        if not record or not record.results:
            return None
        return record.results[-1]

    def get_best_result(self, experiment_id: str) -> ExperimentResult | None:
        """Get the best result (highest improvement) for an experiment."""
        record = self._records.get(experiment_id)
        if not record or not record.results:
            return None
        return max(record.results, key=lambda r: r.improvement_pct)

    def delete(self, experiment_id: str) -> bool:
        """Remove an experiment from tracking."""
        if experiment_id in self._records:
            del self._records[experiment_id]
            self._save()
            return True
        return False

    def clear_all(self) -> int:
        """Remove all experiment records. Returns count removed."""
        count = len(self._records)
        self._records.clear()
        self._save()
        return count

    def summary(self) -> dict[str, Any]:
        """Get a summary of all tracked experiments."""
        records = list(self._records.values())
        status_counts: dict[str, int] = {}
        for r in records:
            s = str(r.experiment.status)
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total": len(records),
            "by_status": status_counts,
            "total_results": sum(len(r.results) for r in records),
            "domains": list(set(
                str(r.experiment.target.domain) for r in records
            )),
        }

    # ── Git integration ─────────────────────────────────────────────────

    def _git_commit(self, result: ExperimentResult) -> str | None:
        """Create a git commit for an experiment result."""
        try:
            msg = (
                f"experiment({result.experiment_id}): "
                f"{result.status} ({result.improvement_pct:+.1f}%)"
            )
            # Stage and commit the experiment log
            subprocess.run(
                ["git", "add", str(self._log_path)],
                capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", msg, "--allow-empty"],
                capture_output=True, check=True,
            )
            # Get the commit SHA
            sha_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, check=True, text=True,
            )
            return sha_proc.stdout.strip()
        except Exception as e:
            logger.debug(f"Git commit failed (expected in non-git envs): {e}")
            return None
