from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .model import ExperimentManifest
from .no_isosceles import Candidate
from .ports import CandidateExecutor, ResearchSearch, SharedMemory
from .swarm import EvoHive, SwarmConfig


@dataclass(frozen=True)
class RunResult:
    run_id: str
    experiment_id: str
    status: str
    started_at: str
    dry_run: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ExperimentRunner:
    """Provider-neutral orchestration boundary for one experiment run."""

    def run(self, manifest: ExperimentManifest, *, dry_run: bool) -> RunResult:
        manifest.validate()
        return RunResult(
            run_id=str(uuid4()),
            experiment_id=manifest.experiment_id,
            status="validated" if dry_run else "completed",
            started_at=datetime.now(UTC).isoformat(),
            dry_run=dry_run,
        )


def run_evohive(
    *,
    manifest: ExperimentManifest,
    initial: Candidate,
    config: SwarmConfig,
    search: ResearchSearch,
    memory: SharedMemory,
    executor: CandidateExecutor,
    artifact_directory: Path,
) -> tuple[dict[str, Any], Path]:
    manifest.validate()
    evidence = EvoHive(search=search, memory=memory, executor=executor).run(initial, config)
    artifact_directory.mkdir(parents=True, exist_ok=True)
    path = artifact_directory / f"{evidence['run_id']}.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence, path
