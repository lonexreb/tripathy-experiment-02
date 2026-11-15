"""Trusted controller for the P1 symmetry-breaking development smoke (TRI-19).

One trial = one seeded invocation of ``solver/symmetry_breaker.c`` on one
dual-verified, from-scratch P0 candidate, in an isolated subprocess. Breaker
stdout is untrusted. A target-size candidate counts only after both
controller-side oracles accept it AND a fresh process re-reads the persisted
child artifact and both oracles plus the pinned upstream verifier accept it.
No provider (Exa, past.dev, Modal) and no public certificate is involved, and
a smoke never supports a record claim.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import itertools
import json
import math
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import baseline, no_isosceles, perpendicular_bisector_oracle

Point = tuple[int, int]

GRID_SIZE = baseline.GRID_SIZE
BREAKER_SOURCE = Path("solver/symmetry_breaker.c")
UPSTREAM = Path("benchmarks/upstream")
CONFIRMATORY_SEEDS = range(64, 128)  # reserved by the plan until P1 is frozen
ITERATION_1_MIN_VIOLATIONS = 2  # run 418e67a9: the level later iterations must beat
REPAIR_COUNTERS = (
    "repair_attempts",
    "repair_nodes",
    "repair_attempts_exhausted",
    "repair_max_depth",
    "repair_destroy_size",
    "repair_pool_min",
    "repair_pool_max",
)
STATE_ORIGINS = ("exact_repair", "swap")
HASHED_FILES = (
    *baseline.HASHED_FILES,
    str(BREAKER_SOURCE),
    "src/tripathy_experiment/symmetry_breaking.py",
    "benchmarks/upstream/verify_construction.py.txt",
    "docs/P1_SYMMETRY_BREAKING_PLAN.md",
)


def dual_verify(points: tuple[Point, ...]) -> dict[str, Any]:
    distance = no_isosceles.verify(points, GRID_SIZE)
    bisector = perpendicular_bisector_oracle.verify(points, GRID_SIZE)
    return {
        "oracle_distance": distance.to_dict(),
        "oracle_bisector": bisector.to_dict(),
        "oracles_agree": distance.valid == bisector.valid,
        "accepted": distance.valid and bisector.valid,
    }


def isosceles_count(points: tuple[Point, ...]) -> int:
    """Controller-side recount: unordered pairs equidistant from each apex."""
    return sum(
        math.comb(count, 2)
        for apex in points
        for count in Counter(
            (apex[0] - other[0]) ** 2 + (apex[1] - other[1]) ** 2
            for other in points
            if other != apex
        ).values()
    )


def _int_points(raw: object, expected: int) -> tuple[Point, ...]:
    if not isinstance(raw, list) or len(raw) != expected:
        raise ValueError(f"expected a list of {expected} points")
    for point in raw:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(type(coordinate) is not int for coordinate in point)
        ):
            raise ValueError("each point must be a pair of integers")
    return tuple((point[0], point[1]) for point in raw)


def load_sources(
    artifact_dir: Path, parent_run_id: str, source_score: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select the distinct, freshly dual-verified P0 candidates of ``source_score``.

    Raises ValueError if the parent is not a passed baseline summary or any
    selected child fails re-verification; a tampered source stops the run.
    """
    parent_path = artifact_dir / f"{parent_run_id}.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if (
        parent.get("kind") != "baseline-summary"
        or parent.get("run_id") != parent_run_id
        or parent.get("gate_status") != "passed"
    ):
        raise ValueError(f"{parent_path} is not a passed baseline summary")
    sources: dict[str, dict[str, Any]] = {}
    for child in sorted(parent["children"], key=lambda entry: int(entry["seed"])):
        if child["failure_class"] is not None or child["score"] != source_score:
            continue
        trial_id = str(child["trial_id"])
        if not trial_id.startswith(f"{parent_run_id}.trial-") or "/" in trial_id:
            raise ValueError(f"unexpected P0 trial id {trial_id!r}")
        path = artifact_dir / f"{trial_id}.json"
        trial = json.loads(path.read_text(encoding="utf-8"))
        points = _int_points(trial.get("points"), source_score)
        digest = baseline.canonical_sha256(sorted(points))
        if (
            trial.get("kind") != "baseline-trial"
            or trial.get("run_id") != parent_run_id
            or trial.get("score") != source_score
            or trial.get("failure_class") is not None
            or digest != trial.get("candidate_sha256")
            or digest != child.get("candidate_sha256")
            or not dual_verify(points)["accepted"]
        ):
            raise ValueError(f"P0 child {trial_id} failed source re-verification")
        entry = sources.setdefault(
            digest,
            {
                "candidate_sha256": digest,
                "p0_trial_id": trial_id,
                "p0_seed": child["seed"],
                "p0_trial_ids": [],
                "artifact": str(path),
                "artifact_sha256": baseline.sha256_file(path),
                "points": [list(point) for point in sorted(points)],
            },
        )
        entry["p0_trial_ids"].append(trial_id)
    if not sources:
        raise ValueError(f"parent run has no verified {source_score}-point candidates")
    lineage = {
        "run_id": parent_run_id,
        "artifact": str(parent_path),
        "artifact_sha256": baseline.sha256_file(parent_path),
        "git": parent.get("git"),
        "initialization": parent.get("initialization"),
    }
    return lineage, list(sources.values())


def classify_progress(verified_targets: int, min_violations: int | None, full_depth: bool) -> str:
    """The plan's three search-progress classes (iterations 2 and 3)."""
    if verified_targets > 0:
        return "record_candidate"
    if full_depth or (min_violations is not None and min_violations < ITERATION_1_MIN_VIOLATIONS):
        return "operator_progress"
    return "no_progress"


def run_trial(
    binary: str,
    source: dict[str, Any],
    seed: int,
    iters: int,
    target: int,
    repair_nodes: int,
    destroy_size: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Re-verify the source, run one breaker process, classify. Never raises."""
    source_points = tuple((point[0], point[1]) for point in source["points"])
    arguments = [
        "--seed", str(seed), "--iters", str(iters), "--target", str(target),
        "--repair-nodes", str(repair_nodes), "--destroy-size", str(destroy_size),
    ]  # fmt: skip
    destroy = destroy_size
    record: dict[str, Any] = {
        "seed": seed,
        "iters": iters,
        "target": target,
        "repair_node_cap": repair_nodes,
        "destroy_size": destroy_size,
        "grid_size": GRID_SIZE,
        "command": ["<symmetry-breaker>", *arguments],
        "source": {key: value for key, value in source.items() if key != "points"},
        "source_reverification": dual_verify(source_points),
        "failure_class": None,
        "score": None,
        "claimed_score": None,
        "points": None,
        "candidate_sha256": None,
        "output_equals_source": None,
        "oracle_distance": None,
        "oracle_bisector": None,
        "oracles_agree": None,
        "min_working_violations": None,
        "closest_approach": None,
        "repair": None,
        "best_state_origin": None,
        "solver_termination_reason": None,
        "solver_counters": None,
        "solver_version": None,
        "cpu_seconds": None,
        "wall_seconds": 0.0,
        "exit_code": None,
        "stdout_sha256": None,
        "detail": "",
    }
    if not record["source_reverification"]["accepted"] or len(source_points) != target - 1:
        record["failure_class"] = "source_rejected"
        return record
    stdin = f"{len(source_points)}\n" + "".join(f"{x} {y}\n" for x, y in source_points)
    process, stdout = baseline.run_process([binary, *arguments], timeout_seconds, stdin.encode())
    record.update(process)
    if record["failure_class"] is not None:
        return record

    try:
        payload = baseline.parse_candidate(stdout, seed, iters)
        if type(payload.get("target")) is not int or payload["target"] != target:
            raise ValueError(f"breaker echoed target={payload.get('target')!r}")
        closest = payload.get("closest_approach")
        if not isinstance(closest, dict) or type(closest.get("violations")) is not int:
            raise ValueError("closest_approach must report integer violations")
        near_points = _int_points(closest.get("points"), target)
        counters = payload["counters"]
        repair = {name.removeprefix("repair_"): counters.get(name) for name in REPAIR_COUNTERS}
        if any(type(value) is not int or value < 0 for value in repair.values()):
            raise ValueError("repair counters must be non-negative integers")
        if type(counters.get("restarts")) is not int:
            raise ValueError("restarts must be an integer")
        if payload.get("best_state_origin") not in STATE_ORIGINS:
            raise ValueError(f"best_state_origin must be one of {STATE_ORIGINS}")
        for echoed in ("repair_node_cap", "destroy_size"):
            if type(payload.get(echoed)) is not int:
                raise ValueError(f"{echoed} must be an integer")
    except (ValueError, UnicodeDecodeError) as error:
        record["failure_class"] = "malformed_output"
        record["detail"] = str(error)[:500]
        return record

    points = tuple((point[0], point[1]) for point in payload["points"])
    claimed_violations: int = closest["violations"]
    verdict = dual_verify(points)
    near = dual_verify(near_points)
    recount = isosceles_count(near_points)
    unchanged = sorted(points) == sorted(source_points)
    record.update(
        points=[list(point) for point in points],
        candidate_sha256=baseline.canonical_sha256(sorted(points)),
        claimed_score=payload["score"],
        output_equals_source=unchanged,
        oracle_distance=verdict["oracle_distance"],
        oracle_bisector=verdict["oracle_bisector"],
        oracles_agree=verdict["oracles_agree"],
        closest_approach={
            "label": "lowest-violation working state; NOT an accepted candidate unless 0",
            "claimed_violations": claimed_violations,
            "recounted_violations": recount,
            "points": [list(point) for point in near_points],
            "oracle_distance_valid": near["oracle_distance"]["valid"],
            "oracle_bisector_valid": near["oracle_bisector"]["valid"],
        },
        repair={**repair, "node_cap": payload["repair_node_cap"]},
        best_state_origin=payload["best_state_origin"],
        solver_termination_reason=payload["termination_reason"],
        solver_counters=payload["counters"],
        solver_version=payload["solver_version"],
    )
    if not verdict["oracles_agree"] or not near["oracles_agree"]:
        record["failure_class"] = "oracle_disagreement"
    elif not verdict["accepted"]:
        record["failure_class"] = "invalid_candidate"  # the breaker false-accepted
    elif payload["score"] != len(points):
        record["failure_class"] = "score_mismatch"
    elif len(points) != target and not unchanged:
        record["failure_class"] = "unexpected_candidate"
    elif (
        recount != claimed_violations
        or payload["counters"].get("min_working_violations") != claimed_violations
        or near["accepted"] != (claimed_violations == 0)
        or (len(points) == target) != (claimed_violations == 0)
        or len(set(near_points)) != target
    ):
        record["failure_class"] = "closest_approach_mismatch"
    elif (
        payload["repair_node_cap"] != repair_nodes
        or payload["destroy_size"] != destroy
        or repair["destroy_size"] != destroy
        or repair["attempts"] != counters["restarts"] + 1  # startup plus one per restart
        or repair["nodes"] > repair["attempts"] * repair_nodes
        or repair["attempts_exhausted"] > repair["attempts"]
        or repair["max_depth"] > destroy + 1
        # full depth is a completed repair, which must be the emitted target-size set
        or (repair["max_depth"] == destroy + 1) != (payload["best_state_origin"] == "exact_repair")
        or (payload["best_state_origin"] == "exact_repair" and len(points) != target)
    ):
        record["failure_class"] = "repair_counter_mismatch"
    else:
        record["score"] = len(points)  # in-memory acceptance; a target still needs persistence
        record["min_working_violations"] = claimed_violations
    return record


def verify_persisted(path: Path) -> dict[str, Any]:
    """Reload a persisted artifact; both oracles and pinned upstream must accept."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = _int_points(payload.get("points"), int(payload.get("score") or 0))
    verdict = dual_verify(points)
    provenance = json.loads((UPSTREAM / "PROVENANCE.json").read_text(encoding="utf-8"))
    source = (UPSTREAM / "verify_construction.py.txt").read_bytes()
    pinned = hashlib.sha256(source).hexdigest() == provenance["vendored_verifier"]["sha256"]
    upstream = False
    if pinned:
        namespace: dict[str, Any] = {"itertools": itertools, "sqrt": math.sqrt}
        exec(compile(source, "upstream_verify_construction", "exec"), namespace)
        with contextlib.redirect_stdout(io.StringIO()):
            upstream = namespace["verify_construction"](list(points)) is True
    return {
        "artifact_sha256": baseline.sha256_file(path),
        "score": len(points),
        "oracle_distance_valid": verdict["oracle_distance"]["valid"],
        "oracle_bisector_valid": verdict["oracle_bisector"]["valid"],
        "upstream_verifier_pinned": pinned,
        "upstream_accepts": upstream,
        "accepted": verdict["accepted"] and upstream,
    }


def verify_persisted_in_fresh_process(path: Path, root: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", __name__, str(path.resolve())]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=300, check=False, cwd=root
        )
        result = json.loads(completed.stdout)
        if not isinstance(result, dict) or (completed.returncode == 0) != result.get("accepted"):
            raise ValueError("verifier exit code and verdict disagree")
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return {"accepted": False, "detail": f"fresh-process verification failed: {error}"[:500]}


def run_smoke(
    *,
    parent_run_id: str,
    seeds: list[int],
    iters: int,
    workers: int,
    artifact_dir: Path,
    timeout_seconds: float,
    linear_issue: str,
    experiment_id: str,
    repair_nodes: int,
    destroy_size: int,
    target: int = 59,
    root: Path = Path("."),
    breaker_binary: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run every breaker seed; write one child artifact per trial and one parent."""
    if iters < 1 or workers < 1 or timeout_seconds <= 0 or repair_nodes < 0:
        raise ValueError("iters >= 1, workers >= 1, repair_nodes >= 0 and a timeout are required")
    if not 1 <= destroy_size <= target - 1:
        raise ValueError(f"destroy_size must be between 1 and {target - 1} (the source size)")
    if set(seeds) & set(CONFIRMATORY_SEEDS):
        raise ValueError("seeds 64..127 are reserved for the confirmatory P1 run")
    run_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    lineage, sources = load_sources(artifact_dir, parent_run_id, target - 1)
    breaker = (
        baseline.build_solver(root, root / "build", BREAKER_SOURCE)
        if breaker_binary is None
        else {"binary": breaker_binary, "binary_sha256": baseline.sha256_file(Path(breaker_binary))}
    )
    binary = str(breaker["binary"])
    assigned = {seed: sources[index % len(sources)] for index, seed in enumerate(seeds)}
    config = {
        "trial_definition": "one seeded symmetry-breaker invocation on one verified P0 candidate",
        "seeds": seeds,
        "iters": iters,
        "repair_nodes_per_attempt": repair_nodes,
        "destroy_size": destroy_size,
        "repair_additions": destroy_size + 1,
        "repair_attempt_schedule": "once at startup and after each stall restart",
        "workers": workers,
        "timeout_seconds": timeout_seconds,
        "max_stdout_bytes": baseline.MAX_STDOUT_BYTES,
        "grid_size": GRID_SIZE,
        "target_score": target,
        "source_policy": "round-robin across distinct P0 candidates, ordered by lowest P0 seed",
        "gate_label": "p1-development-smoke",
    }
    shared = {
        "schema_version": 2,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "linear_issue": linear_issue,
        "git": baseline.git_identity(root),
        "file_sha256": {
            name: baseline.sha256_file(root / name)
            for name in HASHED_FILES
            if (root / name).exists()
        },
        "solver_build": breaker,
        "config": config,
        "config_sha256": baseline.canonical_sha256(config),
        "runtime": baseline.runtime_fingerprint(),
        "source_run": lineage,
        "initialization": "dual-verified from-scratch P0 candidates passed on stdin; "
        "the public certificate is never read",
        "cost_usd": 0.0,
        "record_claim": False,
    }

    children: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                run_trial, binary, assigned[seed], seed, iters, target, repair_nodes,
                destroy_size, timeout_seconds,
            )  # fmt: skip
            for seed in seeds
        ]
        for future in as_completed(futures):
            trial = future.result()
            trial_id = f"{run_id}.trial-{trial['seed']:04d}"
            artifact = artifact_dir / f"{trial_id}.json"
            baseline.write_new_artifact(
                artifact, {**shared, "kind": "p1-smoke-trial", "trial_id": trial_id, **trial}
            )
            trial["persisted_verification"] = None
            if trial["score"] == target:
                # The child is immutable, so a rejection here is recorded in the parent only.
                trial["persisted_verification"] = verify_persisted_in_fresh_process(artifact, root)
                if not trial["persisted_verification"]["accepted"]:
                    trial["failure_class"] = "persisted_verification_failed"
                    trial["score"] = None
            children.append({**trial, "trial_id": trial_id, "artifact": str(artifact)})

    children.sort(key=lambda trial: int(trial["seed"]))
    first = children[0]
    replay = run_trial(
        binary, assigned[first["seed"]], first["seed"], iters, target, repair_nodes,
        destroy_size, timeout_seconds,
    )  # fmt: skip
    determinism = {
        "seed": first["seed"],
        "stdout_sha256": first["stdout_sha256"],
        "replay_stdout_sha256": replay["stdout_sha256"],
        "identical": first["stdout_sha256"] is not None
        and first["stdout_sha256"] == replay["stdout_sha256"],
    }
    accepted = [trial for trial in children if trial["failure_class"] is None]
    failures = Counter(str(trial["failure_class"]) for trial in children if trial["failure_class"])
    verified = [trial for trial in accepted if trial["score"] == target]
    closest = {
        str(trial["seed"]): trial["min_working_violations"]
        for trial in children
        if trial["min_working_violations"] is not None
    }
    repairs = [trial["repair"] for trial in children if trial["repair"] is not None]
    full_depth = destroy_size + 1
    max_depth = max((repair["max_depth"] for repair in repairs), default=None)
    gate_passed = (
        not failures
        and determinism["identical"]
        and len(children) == len(seeds)
        and len(closest) == len(children)
    )
    summary: dict[str, Any] = {
        **shared,
        "kind": "p1-smoke-summary",
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "wall_seconds": time.monotonic() - started,
        "cpu_seconds_total": sum(trial["cpu_seconds"] or 0.0 for trial in children),
        "trials": len(children),
        "accepted_trials": len(accepted),
        "score_counts": {
            str(score): count
            for score, count in sorted(Counter(trial["score"] for trial in accepted).items())
        },
        "failure_counts": dict(sorted(failures.items())),
        "oracle_disagreements": failures.get("oracle_disagreement", 0),
        "best_score": max((trial["score"] for trial in accepted), default=None),
        "best_score_note": "a score below the target is the unchanged P0 source, not a new set",
        "verified_target_count": len(verified),
        "verified_target_seeds": [trial["seed"] for trial in verified],
        "min_working_violations": min(closest.values(), default=None),
        "min_working_violations_by_seed": closest,
        "repair": {
            "destroy_size": destroy_size,
            "node_cap_per_attempt": repair_nodes,
            "full_depth": full_depth,
            "max_depth": max_depth,
            "max_depth_by_seed": {
                str(t["seed"]): t["repair"]["max_depth"] for t in children if t["repair"]
            },
            "attempts": sum(repair["attempts"] for repair in repairs),
            "attempts_exhausted": sum(repair["attempts_exhausted"] for repair in repairs),
            "attempts_capped": sum(
                repair["attempts"] - repair["attempts_exhausted"] for repair in repairs
            ),
            "nodes": sum(repair["nodes"] for repair in repairs),
            "pool_min": min((repair["pool_min"] for repair in repairs), default=None),
            "pool_max": max((repair["pool_max"] for repair in repairs), default=None),
        },
        "best_state_origin_by_seed": {
            str(t["seed"]): t["best_state_origin"] for t in children if t["best_state_origin"]
        },
        "search_progress": classify_progress(
            len(verified), min(closest.values(), default=None), max_depth == full_depth
        ),
        "search_progress_baseline": "iteration 1 (run 418e67a9): minimum working violations 2",
        "sources": [{k: v for k, v in source.items() if k != "points"} for source in sources],
        "determinism_replay": determinism,
        "gate_status": "passed" if gate_passed else "infrastructure_failure",
        "search_outcome": "verified_target_found" if verified else "no_target_found",
        "record_claim_note": "a development smoke cannot support a record claim by itself",
        "children": [
            {
                key: trial[key]
                for key in (
                    "trial_id",
                    "seed",
                    "score",
                    "failure_class",
                    "min_working_violations",
                    "best_state_origin",
                    "repair",
                    "output_equals_source",
                    "wall_seconds",
                    "cpu_seconds",
                    "candidate_sha256",
                    "persisted_verification",
                    "artifact",
                )
            }
            | {"source_candidate_sha256": trial["source"]["candidate_sha256"]}
            for trial in children
        ],
    }
    summary_path = artifact_dir / f"{run_id}.json"
    baseline.write_new_artifact(summary_path, summary)
    return summary, summary_path


if __name__ == "__main__":  # fresh-process verification of one persisted artifact
    outcome = verify_persisted(Path(sys.argv[1]))
    print(json.dumps(outcome, sort_keys=True))
    raise SystemExit(0 if outcome["accepted"] else 1)
