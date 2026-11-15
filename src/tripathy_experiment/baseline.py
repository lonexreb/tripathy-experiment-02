"""Trusted controller for the from-scratch compiled baseline (TRI-19 P0 gate).

One trial = one seeded invocation of ``solver/solver.c`` from an empty state in
an isolated subprocess. Solver stdout is untrusted: it is size-limited, parsed
strictly, and accepted only when both controller-side oracles agree. Every
trial, including crashes and timeouts, becomes one immutable JSON artifact.
No provider (Exa, past.dev, Modal) and no public certificate is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from math import comb
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import no_isosceles, perpendicular_bisector_oracle

GRID_SIZE = 32
TARGET_SCORE = 58
MAX_STDOUT_BYTES = 1 << 20
COMPILE_FLAGS = ("-O2", "-std=c99", "-Wall", "-Wextra", "-Werror")
SOLVER_SOURCE = Path("solver/solver.c")
HASHED_FILES = (
    "solver/solver.c",
    "experiment/manifest.json",
    "project.yaml",
    "benchmarks/no_isosceles_n32.json",
    "benchmarks/upstream/PROVENANCE.json",
    "src/tripathy_experiment/no_isosceles.py",
    "src/tripathy_experiment/perpendicular_bisector_oracle.py",
    "src/tripathy_experiment/baseline.py",
    "src/tripathy_experiment/cli.py",
)
INFRASTRUCTURE_FAILURES = frozenset(
    {"crash", "timeout", "output_too_large", "malformed_output", "oracle_disagreement"}
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_seeds(spec: str) -> list[int]:
    """Parse ``0-63`` or ``1,5,9-11`` into an ordered list of distinct seeds."""
    seeds: list[int] = []
    for part in spec.split(","):
        low, _, high = part.partition("-")
        start, stop = int(low), int(high or low)
        if start < 0 or stop < start:
            raise ValueError(f"bad seed range: {part!r}")
        seeds.extend(range(start, stop + 1))
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty list without repeats")
    return seeds


def exact_binomial_interval(
    successes: int, trials: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Clopper-Pearson interval by bisection on exact binomial tail sums."""
    if not 0 <= successes <= trials or trials < 1:
        raise ValueError("need 0 <= successes <= trials and trials >= 1")
    alpha = (1.0 - confidence) / 2.0

    def at_least(count: int, p: float) -> float:  # P(X >= count), increasing in p
        return sum(
            comb(trials, k) * p**k * (1 - p) ** (trials - k) for k in range(count, trials + 1)
        )

    def root(count: int, level: float) -> float:  # p with P(X >= count) == level
        low, high = 0.0, 1.0
        for _ in range(100):
            mid = (low + high) / 2
            if at_least(count, mid) < level:
                low = mid
            else:
                high = mid
        return (low + high) / 2

    lower = 0.0 if successes == 0 else root(successes, alpha)
    upper = 1.0 if successes == trials else root(successes + 1, 1.0 - alpha)
    return lower, upper


def write_new_artifact(path: Path, payload: dict[str, Any]) -> None:
    """Atomically create ``path``; raise FileExistsError rather than overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)  # fails if the artifact already exists
    finally:
        os.unlink(temp_name)


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return (completed.stdout or completed.stderr).strip()


def git_identity(root: Path) -> dict[str, object]:
    head = _command_output(["git", "-C", str(root), "rev-parse", "HEAD"])
    status = _command_output(["git", "-C", str(root), "status", "--porcelain"])
    return {"head": head, "dirty": status != "", "dirty_paths": len(status.splitlines())}


def runtime_fingerprint() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_brand": _command_output(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "compiler": _command_output(["cc", "--version"]).splitlines()[:1],
    }


def build_solver(root: Path, build_dir: Path) -> dict[str, object]:
    """Compile the solver to a path keyed by its source hash, or reuse it."""
    source = root / SOLVER_SOURCE
    source_hash = sha256_file(source)
    binary = (build_dir / f"solver-{source_hash[:16]}").resolve()
    if not binary.exists():
        build_dir.mkdir(parents=True, exist_ok=True)
        command = ["cc", *COMPILE_FLAGS, "-o", str(binary), str(source)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"solver build failed: {completed.stderr[-2000:]}")
    return {
        "source": str(SOLVER_SOURCE),
        "source_sha256": source_hash,
        "binary": str(binary),
        "binary_sha256": sha256_file(binary),
        "compile_command": ["cc", *COMPILE_FLAGS, "-o", "<binary>", str(SOLVER_SOURCE)],
    }


def parse_candidate(stdout: bytes, seed: int, iters: int) -> dict[str, Any]:
    """Strictly decode untrusted solver stdout; raise ValueError on any defect."""
    payload = json.loads(stdout.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("solver output is not a JSON object")
    for key, expected in (("seed", seed), ("iters", iters), ("grid_size", GRID_SIZE)):
        if type(payload.get(key)) is not int or payload[key] != expected:
            raise ValueError(f"solver echoed {key}={payload.get(key)!r}, expected {expected}")
    points = payload.get("points")
    if not isinstance(points, list) or len(points) > GRID_SIZE * GRID_SIZE:
        raise ValueError("points must be a bounded list")
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(type(coordinate) is not int for coordinate in point)
        ):
            raise ValueError("each point must be a pair of integers")
    if type(payload.get("score")) is not int:
        raise ValueError("score must be an integer")
    if not isinstance(payload.get("counters"), dict):
        raise ValueError("counters must be an object")
    for key in ("termination_reason", "solver_version"):
        if not isinstance(payload.get(key), str) or len(payload[key]) > 200:
            raise ValueError(f"{key} must be a short string")
    return payload


def run_trial(binary: str, seed: int, iters: int, timeout_seconds: float) -> dict[str, Any]:
    """Run one isolated solver process and classify the outcome. Never raises."""
    command = [binary, "--seed", str(seed), "--iters", str(iters)]
    record: dict[str, Any] = {
        "seed": seed,
        "iters": iters,
        "command": ["<solver>", *command[1:]],
        "started_at": datetime.now(UTC).isoformat(),
        "failure_class": None,
        "score": None,
        "claimed_score": None,
        "points": None,
        "candidate_sha256": None,
        "oracle_distance": None,
        "oracle_bisector": None,
        "oracles_agree": None,
        "solver_termination_reason": None,
        "solver_counters": None,
        "solver_version": None,
        "cpu_seconds": None,
        "exit_code": None,
        "detail": "",
    }
    started = time.monotonic()
    timed_out = threading.Event()
    stdout = b""
    try:
        with (
            tempfile.TemporaryDirectory(prefix="evohive-trial-") as scratch,
            tempfile.TemporaryFile() as stderr_file,
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                cwd=scratch,
                env={},
            ) as process,
        ):

            def expire() -> None:
                timed_out.set()
                process.kill()

            timer = threading.Timer(timeout_seconds, expire)
            timer.start()
            try:
                assert process.stdout is not None
                stdout = process.stdout.read(MAX_STDOUT_BYTES + 1)
                if len(stdout) > MAX_STDOUT_BYTES:
                    process.kill()
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
            finally:
                timer.cancel()
            record["cpu_seconds"] = usage.ru_utime + usage.ru_stime
            record["exit_code"] = process.returncode
            stderr_file.seek(0)
            record["detail"] = stderr_file.read(2000).decode("utf-8", errors="replace")
    except OSError as error:
        record["failure_class"] = "crash"
        record["detail"] = f"could not run solver: {error}"
    record["wall_seconds"] = time.monotonic() - started
    record["completed_at"] = datetime.now(UTC).isoformat()
    record["stdout_bytes"] = min(len(stdout), MAX_STDOUT_BYTES)
    record["stdout_sha256"] = hashlib.sha256(stdout).hexdigest()

    if record["failure_class"] is None:
        if timed_out.is_set():
            record["failure_class"] = "timeout"
        elif len(stdout) > MAX_STDOUT_BYTES:
            record["failure_class"] = "output_too_large"
        elif record["exit_code"] != 0:
            record["failure_class"] = "crash"
    if record["failure_class"] is not None:
        return record

    try:
        payload = parse_candidate(stdout, seed, iters)
    except (ValueError, UnicodeDecodeError) as error:
        record["failure_class"] = "malformed_output"
        record["detail"] = str(error)[:500]
        return record

    points = tuple((point[0], point[1]) for point in payload["points"])
    distance = no_isosceles.verify(points, GRID_SIZE)
    bisector = perpendicular_bisector_oracle.verify(points, GRID_SIZE)
    record.update(
        points=[list(point) for point in points],
        candidate_sha256=canonical_sha256(sorted(points)),
        claimed_score=payload["score"],
        oracle_distance=distance.to_dict(),
        oracle_bisector=bisector.to_dict(),
        oracles_agree=distance.valid == bisector.valid,
        solver_termination_reason=payload["termination_reason"],
        solver_counters=payload["counters"],
        solver_version=payload["solver_version"],
    )
    if distance.valid != bisector.valid:
        record["failure_class"] = "oracle_disagreement"
    elif not distance.valid:
        record["failure_class"] = "invalid_candidate"
    elif payload["score"] != len(points):
        record["failure_class"] = "score_mismatch"
    else:
        record["score"] = len(points)  # accepted: both oracles agree it is valid
    return record


def run_baseline(
    *,
    seeds: list[int],
    iters: int,
    workers: int,
    artifact_dir: Path,
    timeout_seconds: float,
    gate_label: str,
    linear_issue: str,
    experiment_id: str,
    root: Path = Path("."),
    solver_binary: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run every seed, write one child artifact per trial and one parent summary."""
    if iters < 1 or workers < 1 or timeout_seconds <= 0:
        raise ValueError("iters >= 1, workers >= 1 and a positive timeout are required")
    run_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    solver = (
        build_solver(root, root / "build")
        if solver_binary is None
        else {"binary": solver_binary, "binary_sha256": sha256_file(Path(solver_binary))}
    )
    config = {
        "trial_definition": "one from-scratch seeded solver invocation in its own subprocess",
        "seeds": seeds,
        "iters": iters,
        "workers": workers,
        "timeout_seconds": timeout_seconds,
        "max_stdout_bytes": MAX_STDOUT_BYTES,
        "grid_size": GRID_SIZE,
        "target_score": TARGET_SCORE,
        "gate_label": gate_label,
    }
    shared = {
        "schema_version": 2,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "linear_issue": linear_issue,
        "git": git_identity(root),
        "file_sha256": {
            name: sha256_file(root / name) for name in HASHED_FILES if (root / name).exists()
        },
        "solver_build": solver,
        "config": config,
        "config_sha256": canonical_sha256(config),
        "runtime": runtime_fingerprint(),
        "initialization": "empty state; the public 58-point certificate is never read",
        "cost_usd": 0.0,
    }

    children: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(run_trial, str(solver["binary"]), seed, iters, timeout_seconds)
            for seed in seeds
        ]
        for future in as_completed(futures):
            trial = future.result()
            trial_id = f"{run_id}.trial-{trial['seed']:04d}"
            artifact = artifact_dir / f"{trial_id}.json"
            write_new_artifact(
                artifact, {**shared, "kind": "baseline-trial", "trial_id": trial_id, **trial}
            )
            children.append({**trial, "trial_id": trial_id, "artifact": str(artifact)})

    children.sort(key=lambda trial: int(trial["seed"]))
    accepted = [trial for trial in children if trial["failure_class"] is None]
    failures = Counter(str(trial["failure_class"]) for trial in children if trial["failure_class"])
    reached = sum(1 for trial in accepted if trial["score"] >= TARGET_SCORE)
    low, high = exact_binomial_interval(reached, len(children))
    infrastructure = sorted(set(failures) & INFRASTRUCTURE_FAILURES)
    if infrastructure:
        gate_status = "infrastructure_failure"
    elif reached > 0:
        gate_status = "passed"
    else:
        gate_status = "failed"
    summary: dict[str, Any] = {
        **shared,
        "kind": "baseline-summary",
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
        "reach_target_count": reached,
        "reach_target_seeds": [t["seed"] for t in accepted if t["score"] >= TARGET_SCORE],
        "reach_target_rate": reached / len(children),
        "reach_target_ci95_exact": [low, high],
        "distinct_target_candidates": len(
            {t["candidate_sha256"] for t in accepted if t["score"] >= TARGET_SCORE}
        ),
        "gate_status": gate_status,
        "infrastructure_failure_classes": infrastructure,
        "record_claim": False,
        "children": [
            {
                key: trial[key]
                for key in (
                    "trial_id",
                    "seed",
                    "score",
                    "failure_class",
                    "wall_seconds",
                    "cpu_seconds",
                    "candidate_sha256",
                    "artifact",
                )
            }
            for trial in children
        ],
    }
    summary_path = artifact_dir / f"{run_id}.json"
    write_new_artifact(summary_path, summary)
    return summary, summary_path
