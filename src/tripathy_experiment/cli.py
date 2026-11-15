from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import perpendicular_bisector_oracle
from .adapters import (
    ExaResearchSearch,
    FixtureResearchSearch,
    InMemorySharedMemory,
    LocalCandidateExecutor,
    ModalCandidateExecutor,
    PastSharedMemory,
)
from .baseline import parse_seeds, run_baseline, sha256_file
from .judge_report import build_report, write_report
from .modal_gateway import ModalSandboxGateway
from .model import ExperimentManifest, ValidationError
from .no_isosceles import Candidate, greedy_seed, load_public_baseline, verify
from .parallel_comparison import PREREGISTERED, run_comparison
from .runner import ExperimentRunner, run_evohive
from .swarm import SwarmConfig
from .symmetry_breaking import run_smoke


def load_manifest(path: Path) -> ExperimentManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ExperimentManifest.from_dict(payload)


def verify_benchmark(path: Path | None) -> int:
    """Check a benchmark JSON with both oracles; exit 0 only if both accept."""
    if path is None:
        raise ValidationError("verify requires a benchmark JSON path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = tuple((int(point[0]), int(point[1])) for point in payload["points"])
    grid_size = int(payload["grid_size"])
    distance = verify(points, grid_size)
    bisector = perpendicular_bisector_oracle.verify(points, grid_size)
    accepted = distance.valid and bisector.valid and len(points) == payload.get("score")
    print(
        json.dumps(
            {
                "benchmark": str(path),
                "benchmark_sha256": sha256_file(path),
                "grid_size": grid_size,
                "declared_score": payload.get("score"),
                "score": len(points),
                "oracle_distance": distance.to_dict(),
                "oracle_bisector": bisector.to_dict(),
                "oracles_agree": distance.valid == bisector.valid,
                "witness": distance.witness or bisector.witness,
                "accepted": accepted,
            },
            sort_keys=True,
        )
    )
    return 0 if accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="EvoHive verification-first autoresearch runner")
    parser.add_argument(
        "command",
        choices=(
            "validate", "run", "verify", "baseline", "p1-smoke", "p2-compare", "judge-report"
        ),
    )
    parser.add_argument("benchmark", nargs="?", type=Path, help="benchmark JSON for verify")
    parser.add_argument("--seeds", default="0-63", help="baseline seeds, e.g. 0-63")
    parser.add_argument("--iters", type=int, help="baseline: fixed ruin/repair iterations")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--parent-run", help="p1-smoke: run ID of the passed P0 baseline")
    parser.add_argument("--target", type=int, default=59, help="p1-smoke: target cardinality")
    parser.add_argument("--repair-nodes", type=int, help="p1-smoke: exact-repair node cap")
    parser.add_argument("--destroy-size", type=int, help="p1-smoke: points removed per repair")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--gate-label", choices=("reproduction", "screening"), default=None)
    parser.add_argument("--manifest", type=Path, default=Path("experiment/manifest.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--grid-size", type=int, default=12)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--agents", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--backend", choices=("local", "modal"), default="local")
    parser.add_argument("--search", choices=("fixture", "exa"), default="fixture")
    parser.add_argument("--memory", choices=("local", "past"), default="local")
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/runs"))
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts/judge"))
    parser.add_argument("--check-report", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "verify":
            return verify_benchmark(args.benchmark)

        manifest = load_manifest(args.manifest)
        if args.command == "validate":
            manifest.validate()
            print(json.dumps({"status": "valid", "experiment_id": manifest.experiment_id}))
            return 0

        if args.command == "judge-report":
            report = build_report(artifact_dir=args.artifact_dir)
            json_path, markdown_path = write_report(
                report, args.report_dir, check=args.check_report
            )
            print(
                json.dumps(
                    {
                        "status": "current" if args.check_report else "written",
                        "json": str(json_path),
                        "markdown": str(markdown_path),
                        "source_artifacts": report["integrity"]["source_artifact_count"],
                        "fresh_dual_verifications": report["integrity"][
                            "fresh_dual_verifications"
                        ],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "baseline":
            manifest.validate()
            if args.iters is None:
                raise ValidationError("baseline requires --iters")
            summary, summary_path = run_baseline(
                seeds=parse_seeds(args.seeds),
                iters=args.iters,
                workers=args.workers,
                artifact_dir=args.artifact_dir,
                timeout_seconds=args.timeout_seconds,
                gate_label=args.gate_label or "reproduction",
                linear_issue=manifest.linear_issue,
                experiment_id=manifest.experiment_id,
            )
            keys = (
                "run_id", "gate_label", "gate_status", "trials", "score_counts", "failure_counts",
                "best_score", "reach_target_count", "reach_target_ci95_exact",
                "oracle_disagreements", "wall_seconds", "cost_usd",
            )
            report = {key: summary.get(key, summary["config"].get(key)) for key in keys}
            print(json.dumps({**report, "artifact": str(summary_path)}, sort_keys=True))
            return 2 if summary["gate_status"] == "infrastructure_failure" else 0

        if args.command == "p1-smoke":
            manifest.validate()
            required = (args.iters, args.parent_run, args.repair_nodes, args.destroy_size)
            if any(value is None for value in required):
                raise ValidationError(
                    "p1-smoke requires --parent-run, --iters, --repair-nodes and --destroy-size"
                )
            summary, summary_path = run_smoke(
                parent_run_id=args.parent_run,
                seeds=parse_seeds(args.seeds),
                iters=args.iters,
                workers=args.workers,
                artifact_dir=args.artifact_dir,
                timeout_seconds=args.timeout_seconds,
                linear_issue=manifest.linear_issue,
                experiment_id=manifest.experiment_id,
                target=args.target,
                repair_nodes=args.repair_nodes,
                destroy_size=args.destroy_size,
            )
            smoke_keys = (
                "run_id", "gate_status", "search_outcome", "search_progress", "repair",
                "best_state_origin_by_seed", "trials", "score_counts",
                "failure_counts", "best_score", "verified_target_count",
                "min_working_violations", "min_working_violations_by_seed",
                "oracle_disagreements", "determinism_replay", "wall_seconds",
                "cpu_seconds_total", "cost_usd", "record_claim",
            )
            report = {key: summary[key] for key in smoke_keys}
            print(json.dumps({**report, "artifact": str(summary_path)}, sort_keys=True))
            return 2 if summary["gate_status"] == "infrastructure_failure" else 0

        if args.command == "p2-compare":
            manifest.validate()
            if args.iters is None:
                raise ValidationError("p2-compare requires --iters")
            seeds = parse_seeds(args.seeds)
            requested = {"seeds": seeds, "iters": args.iters, "workers": args.workers}
            if requested != PREREGISTERED:
                raise ValidationError(
                    "p2-compare is frozen to --seeds 1300-1303 --iters 100000 --workers 4"
                )
            summary, summary_path = run_comparison(
                gateway=ModalSandboxGateway(),
                seeds=seeds,
                iters=args.iters,
                workers=args.workers,
                artifact_dir=args.artifact_dir,
                linear_issue=manifest.linear_issue,
                experiment_id=manifest.experiment_id,
            )
            compare_keys = (
                "run_id", "gate_status", "trials", "accepted_trials", "score_counts",
                "failure_counts", "oracle_disagreements", "false_accepts", "agreement",
                "isolation", "latency", "cost_usd", "cost_status", "record_claim",
            )
            report = {key: summary[key] for key in compare_keys}
            print(json.dumps({**report, "artifact": str(summary_path)}, sort_keys=True))
            return 0 if summary["gate_status"].startswith("passed") else 2

        if args.dry_run:
            result = ExperimentRunner().run(manifest, dry_run=True)
            print(json.dumps(result.to_dict(), sort_keys=True))
            return 0

        if args.grid_size < 3 or args.generations < 1 or args.agents < 1:
            raise ValidationError("grid-size >= 3, generations >= 1 and agents >= 1 are required")

        if args.grid_size == 32:
            initial = load_public_baseline(Path("benchmarks/no_isosceles_n32.json"))
            target_score = 58
        else:
            initial = Candidate(
                points=greedy_seed(args.grid_size, args.seed),
                agent_id="local-baseline",
                strategy="greedy-seed",
            )
            target_score = initial.score
        verification = verify(initial.points, args.grid_size)
        if not verification.valid:
            raise ValidationError(f"baseline failed verifier: {verification.reason}")

        search = ExaResearchSearch() if args.search == "exa" else FixtureResearchSearch()
        memory = PastSharedMemory() if args.memory == "past" else InMemorySharedMemory()
        executor = ModalCandidateExecutor() if args.backend == "modal" else LocalCandidateExecutor()
        config = SwarmConfig(
            grid_size=args.grid_size,
            generations=args.generations,
            agents=args.agents,
            seed=args.seed,
            target_score=target_score,
            backend=args.backend,
            search_mode=args.search,
            memory_mode=args.memory,
        )
        evidence, artifact_path = run_evohive(
            manifest=manifest,
            initial=initial,
            config=config,
            search=search,
            memory=memory,
            executor=executor,
            artifact_directory=args.artifact_dir,
        )
        print(
            json.dumps(
                {
                    "status": "completed",
                    "run_id": evidence["run_id"],
                    "best_score": evidence["best"]["score"],
                    "beat_target": evidence["beat_target"],
                    "trials": evidence["trials"],
                    "artifact": str(artifact_path),
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
