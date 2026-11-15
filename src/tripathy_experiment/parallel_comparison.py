"""Trusted local controller for the P2 local-vs-sandbox comparison (TRI-19).

The same frozen ``solver/solver.c``, seeds and iteration budget run in two arms:
local subprocesses and remote sandboxes reached through the narrow
``SandboxGateway`` port. This module never imports a provider. Everything a
sandbox returns is untrusted: it is size-limited, parsed strictly and accepted
only by ``baseline.judge_stdout`` (both local oracles). Every trial, including
gateway errors, becomes one immutable artifact, and every sandbox that was
created is terminated in ``finally``. This is systems evidence, not a record
attempt.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, Protocol
from uuid import uuid4

from . import baseline
from .symmetry_breaking import CONFIRMATORY_SEEDS

PREREGISTERED = {"seeds": [1300, 1301, 1302, 1303], "iters": 100_000, "workers": 4}
# Fixed by docs/P2_MODAL_CAUSAL_PLAN.md; deliberately not configurable.
ISOLATION: dict[str, Any] = {
    "runtime": "vm",
    "block_network": True,
    "cpu": 1.0,
    "memory_mib": 512,
    "timeout_seconds": 120,
    "secrets": [],
    "mounts": [],
}
SOURCE_NAME = "solver.c"
COMPILE_COMMAND = ["cc", *baseline.COMPILE_FLAGS, "-o", "solver", SOURCE_NAME]
MAX_PROBE_BYTES = 1 << 16
# Runs inside the sandbox after the solver; its answer is evidence, not a control.
PROBE_COMMAND = [
    "python3",
    "-c",
    "import json,os,socket\n"
    "env_names=sorted(os.environ)\n"
    "def blocked(check):\n"
    "    try: check(); return False\n"
    "    except OSError: return True\n"
    "print(json.dumps({'network_blocked': all(blocked(c) for c in ("
    "lambda: socket.create_connection(('1.1.1.1', 443), timeout=3).close(),"
    "lambda: socket.create_connection(('8.8.8.8', 53), timeout=3).close(),"
    "lambda: socket.getaddrinfo('example.com', 443))),"
    "'env_names': env_names[:200], 'env_name_count': len(env_names),"
    "'kernel': open('/proc/version').read()[:200],"
    "'mount_points': [l.split()[1] for l in open('/proc/mounts')][:64]}))",
]
CREDENTIAL_NAME = re.compile(r"TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL", re.IGNORECASE)
# GPG_KEY is the public release-signing fingerprint that the upstream python base image
# sets (next to PYTHON_VERSION and PYTHON_SHA256). The probe reads names only, never values.
ALLOWLISTED_ENV_NAMES = frozenset({"GPG_KEY"})
INFRASTRUCTURE_FAILURES = baseline.INFRASTRUCTURE_FAILURES | {
    "gateway_error",
    "build_failure",
    "source_mismatch",
}
HASHED_FILES = (
    *baseline.HASHED_FILES,
    "docs/P2_MODAL_CAUSAL_PLAN.md",
    "src/tripathy_experiment/parallel_comparison.py",
    "src/tripathy_experiment/modal_gateway.py",
)
COST_UNKNOWN = "unknown: the provider exposes no authoritative per-sandbox cost to this client"


class ExecResult(NamedTuple):
    exit_code: int | None
    stdout: bytes  # at most the requested limit plus one byte
    stderr: str


class Sandbox(Protocol):
    sandbox_id: str

    def write_file(self, name: str, data: bytes) -> None: ...

    def exec(self, command: list[str], timeout_seconds: int, max_stdout_bytes: int) -> ExecResult:
        """Run in the sandbox working directory; raise TimeoutError on expiry."""
        ...

    def terminate(self) -> int | None:
        """Stop the sandbox, wait for it and return its exit status."""
        ...


class SandboxGateway(Protocol):
    def describe(self) -> dict[str, Any]: ...

    def prepare(self) -> None:
        """One-time provider setup (for example the image build)."""
        ...

    def create(self, isolation: dict[str, Any]) -> Sandbox: ...


def _parse_probe(result: ExecResult) -> dict[str, Any]:
    """Strictly decode the untrusted isolation probe; raise ValueError on any defect."""
    if result.exit_code != 0 or len(result.stdout) > MAX_PROBE_BYTES:
        raise ValueError(f"probe exited {result.exit_code} with {len(result.stdout)} bytes")
    payload = json.loads(result.stdout.decode("utf-8"))
    if not isinstance(payload, dict) or type(payload.get("network_blocked")) is not bool:
        raise ValueError("probe did not report network_blocked")
    names = payload.get("env_names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("probe did not report env_names")
    name_count = payload.get("env_name_count")
    if not isinstance(name_count, int) or name_count < len(names):
        raise ValueError("probe did not report a valid env_name_count")
    return {
        "network_blocked": payload["network_blocked"],
        "env_names": [name[:100] for name in names[:200]],
        "env_name_count": name_count,
        "env_names_truncated": name_count > len(names),
        "credential_like_env_names": [
            n[:100]
            for n in names
            if CREDENTIAL_NAME.search(n) and n not in ALLOWLISTED_ENV_NAMES
        ],
        "allowlisted_env_names": sorted(ALLOWLISTED_ENV_NAMES & set(names)),
        "kernel": str(payload.get("kernel"))[:200],
        "mount_points": [str(m)[:200] for m in list(payload.get("mount_points") or [])[:64]],
    }


def run_sandbox_trial(
    gateway: SandboxGateway, source: bytes, seed: int, iters: int
) -> dict[str, Any]:
    """Compile and run one seed in one fresh sandbox. Never raises."""
    timeout = int(ISOLATION["timeout_seconds"])
    record = baseline.empty_trial(seed, iters)
    record.update(
        started_at=datetime.now(UTC).isoformat(),
        failure_class=None,
        detail="",
        exit_code=None,
        cpu_seconds=None,  # not observable from the controller
        isolation_requested=dict(ISOLATION),
        isolation_probe=None,
        isolation_verified=False,
        sandbox_id=None,
        source_readback_sha256=None,
        termination={"attempted": False, "ok": None, "exit_code": None, "detail": ""},
        cost_usd=None,
        cost_status=COST_UNKNOWN,
    )
    phases: dict[str, float] = {}
    started = time.monotonic()
    stdout = b""

    def timed(name: str, action: Callable[[], Any]) -> Any:
        phase_started = time.monotonic()
        try:
            return action()
        finally:
            phases[name] = time.monotonic() - phase_started

    def remaining() -> int:
        return max(1, int(timeout - (time.monotonic() - started)))

    def fail(failure_class: str, detail: str) -> None:
        record["failure_class"] = failure_class
        record["detail"] = detail[:2000]

    sandbox: Sandbox | None = None
    try:
        sandbox = timed("create", lambda: gateway.create(dict(ISOLATION)))
        box = sandbox
        record["sandbox_id"] = str(box.sandbox_id)[:200]
        timed("upload", lambda: box.write_file(SOURCE_NAME, source))
        readback = timed(
            "readback", lambda: box.exec(["cat", SOURCE_NAME], remaining(), len(source))
        )
        record["source_readback_sha256"] = hashlib.sha256(readback.stdout).hexdigest()
        compiled = None
        if readback.stdout != source:
            fail("source_mismatch", "the sandbox did not hold the exact solver source")
        else:
            compiled = timed("compile", lambda: box.exec(COMPILE_COMMAND, remaining(), 4096))
            if compiled.exit_code != 0:
                fail("build_failure", f"exit {compiled.exit_code}: {compiled.stderr}")
        if record["failure_class"] is None:
            solved = timed(
                "solve",
                lambda: box.exec(
                    ["./solver", *record["command"][1:]], remaining(), baseline.MAX_STDOUT_BYTES
                ),
            )
            stdout = solved.stdout
            record["exit_code"] = solved.exit_code
            if len(stdout) > baseline.MAX_STDOUT_BYTES:
                fail("output_too_large", "")
            elif solved.exit_code != 0:
                fail("crash", solved.stderr)
        phases["time_to_result"] = time.monotonic() - started
        try:  # evidence only: a failed probe never changes the trial outcome
            probe = _parse_probe(
                timed("probe", lambda: box.exec(PROBE_COMMAND, 30, MAX_PROBE_BYTES))
            )
        except Exception as error:  # untrusted sandbox, any defect is "unknown"
            probe = {"error": f"{type(error).__name__}: {error}"[:500]}
        record["isolation_probe"] = probe
    except TimeoutError as error:
        fail("timeout", str(error))
    except Exception as error:  # provider errors must become artifacts
        fail("gateway_error", f"{type(error).__name__}: {error}")
    finally:
        if sandbox is not None:
            termination = record["termination"]
            termination["attempted"] = True
            terminate_started = time.monotonic()
            try:
                termination["exit_code"] = sandbox.terminate()
                termination["ok"] = True
            except Exception as error:  # recorded, never masks the trial
                termination["ok"] = False
                termination["detail"] = f"{type(error).__name__}: {error}"[:500]
            phases["terminate"] = time.monotonic() - terminate_started

    record["wall_seconds"] = time.monotonic() - started
    record["completed_at"] = datetime.now(UTC).isoformat()
    record["phase_seconds"] = phases
    record["stdout_bytes"] = min(len(stdout), baseline.MAX_STDOUT_BYTES)
    record["stdout_sha256"] = hashlib.sha256(stdout).hexdigest()
    probe = record["isolation_probe"] or {}
    record["isolation_verified"] = (
        probe.get("network_blocked") is True
        and probe.get("credential_like_env_names") == []
        and probe.get("env_names_truncated") is False
        and record["termination"]["ok"] is True
    )
    if record["failure_class"] is None:
        baseline.judge_stdout(record, stdout, seed, iters)
    return record


def _run_arm(
    arm: str,
    seeds: list[int],
    workers: int,
    run_one: Callable[[int], dict[str, Any]],
    shared: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Run one arm in parallel, write a child per trial and the arm's parent summary."""
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        trials = list(pool.map(run_one, seeds))
    wall = time.monotonic() - started
    children = []
    for trial in trials:
        trial_id = f"{shared['run_id']}.{arm}-{trial['seed']:04d}"
        path = artifact_dir / f"{trial_id}.json"
        trial.setdefault("cost_usd", 0.0)
        child = {**shared, "kind": "p2-trial", "arm": arm, "trial_id": trial_id, **trial}
        baseline.write_new_artifact(path, child)
        children.append({**trial, "trial_id": trial_id, "artifact": str(path)})
    failures = Counter(str(t["failure_class"]) for t in children if t["failure_class"])
    accepted = [t for t in children if t["failure_class"] is None]
    summary = {
        **shared,
        "kind": "p2-arm-summary",
        "arm": arm,
        "started_at": started_at,
        "wall_seconds": wall,
        "trial_wall_seconds_sum": sum(t["wall_seconds"] for t in children),
        "trials": len(children),
        "accepted_trials": len(accepted),
        "score_counts": {
            str(score): count
            for score, count in sorted(Counter(t["score"] for t in accepted).items())
        },
        "failure_counts": dict(sorted(failures.items())),
        "infrastructure_failure_classes": sorted(set(failures) & INFRASTRUCTURE_FAILURES),
        "oracle_disagreements": failures.get("oracle_disagreement", 0),
        "false_accepts": sum(
            1
            for t in accepted
            if not (t["oracle_distance"]["valid"] and t["oracle_bisector"]["valid"])
        ),
        "children": [
            {
                key: t.get(key)
                for key in (
                    "trial_id", "seed", "score", "failure_class", "wall_seconds", "cpu_seconds",
                    "candidate_sha256", "stdout_sha256", "artifact", "phase_seconds",
                    "sandbox_id", "isolation_verified", "termination",
                )
                if key in t
            }
            for t in children
        ],
    }
    path = artifact_dir / f"{shared['run_id']}.{arm}.json"
    baseline.write_new_artifact(path, summary)
    return {**summary, "artifact": str(path)}


def run_comparison(
    *,
    gateway: SandboxGateway,
    seeds: list[int],
    iters: int,
    workers: int,
    artifact_dir: Path,
    linear_issue: str,
    experiment_id: str,
    root: Path = Path("."),
    backend: str = "modal",
) -> tuple[dict[str, Any], Path]:
    """Run both arms on the same seeds and write the parent comparison artifact."""
    if not seeds or iters < 1 or workers < 1:
        raise ValueError("at least one seed, iters >= 1 and workers >= 1 are required")
    if set(seeds) & set(CONFIRMATORY_SEEDS):
        raise ValueError("seeds 64..127 are reserved and must stay untouched")
    timeout = int(ISOLATION["timeout_seconds"])
    run_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    source = (root / baseline.SOLVER_SOURCE).read_bytes()
    build_started = time.monotonic()
    solver = baseline.build_solver(root, root / "build")
    local_build_seconds = time.monotonic() - build_started
    if solver["source_sha256"] != hashlib.sha256(source).hexdigest():
        raise RuntimeError("solver source changed while the run was starting")
    config = {
        "trial_definition": "one from-scratch seeded solver invocation, once per arm",
        "seeds": seeds,
        "iters": iters,
        "workers": workers,
        "timeout_seconds": timeout,
        "max_stdout_bytes": baseline.MAX_STDOUT_BYTES,
        "grid_size": baseline.GRID_SIZE,
        "backend": backend,
        "isolation": ISOLATION,
        "sandbox_compile_command": COMPILE_COMMAND,
        "matches_preregistration": {"seeds": seeds, "iters": iters, "workers": workers}
        == PREREGISTERED,
    }
    shared = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "linear_issue": linear_issue,
        "git": baseline.git_identity(root),
        "file_sha256": {
            name: baseline.sha256_file(root / name)
            for name in HASHED_FILES
            if (root / name).exists()
        },
        "solver_build": solver,
        "config": config,
        "config_sha256": baseline.canonical_sha256(config),
        "runtime": baseline.runtime_fingerprint(),
        "initialization": "empty state; the public 58-point certificate is never read",
        "record_claim": False,
    }

    local = _run_arm(
        "local",
        seeds,
        workers,
        lambda seed: baseline.run_trial(str(solver["binary"]), seed, iters, timeout),
        shared,
        artifact_dir,
    )
    provider: dict[str, Any] = {"prepare_seconds": None, "prepare_error": None}
    prepare_started = time.monotonic()
    try:
        provider.update(gateway.describe())
        gateway.prepare()
    except Exception as error:  # every sandbox trial will then record its own error
        provider["prepare_error"] = f"{type(error).__name__}: {error}"[:500]
    provider["prepare_seconds"] = time.monotonic() - prepare_started
    remote = _run_arm(
        backend,
        seeds,
        workers,
        lambda seed: run_sandbox_trial(gateway, source, seed, iters),
        {**shared, "provider": provider},
        artifact_dir,
    )

    remote_by_seed = {child["seed"]: child for child in remote["children"]}
    pairs = []
    for mine in local["children"]:
        theirs = remote_by_seed[mine["seed"]]
        both = mine["candidate_sha256"] is not None and theirs["candidate_sha256"] is not None
        pairs.append(
            {
                "seed": mine["seed"],
                "local": {k: mine[k] for k in ("trial_id", "artifact", "score", "failure_class",
                                               "candidate_sha256", "stdout_sha256")},
                backend: {k: theirs[k] for k in ("trial_id", "artifact", "score", "failure_class",
                                                 "candidate_sha256", "stdout_sha256")},
                "candidate_agreement": (
                    mine["candidate_sha256"] == theirs["candidate_sha256"] if both else None
                ),
                "stdout_byte_identical": (
                    mine["stdout_sha256"] == theirs["stdout_sha256"] if both else None
                ),
            }
        )
    phase_sums: Counter[str] = Counter()
    for child in remote["children"]:
        phase_sums.update(child["phase_seconds"])
    count = len(seeds)
    solve_mean = phase_sums["solve"] / count
    overhead_mean = (remote["trial_wall_seconds_sum"] - phase_sums["solve"]) / count
    all_children = [*local["children"], *remote["children"]]
    infrastructure = sorted(
        set(local["infrastructure_failure_classes"]) | set(remote["infrastructure_failure_classes"])
    )
    agree = [pair["candidate_agreement"] for pair in pairs]
    isolation_ok = all(child["isolation_verified"] for child in remote["children"])
    terminated = sum(1 for child in remote["children"] if child["termination"]["ok"] is True)
    if infrastructure:
        gate_status = "infrastructure_failure"
    elif not isolation_ok:
        gate_status = "isolation_unverified"
    elif all(value is True for value in agree):
        gate_status = "passed"
    else:
        gate_status = "passed_with_retained_mismatches"
    summary: dict[str, Any] = {
        **shared,
        "kind": "p2-comparison",
        "provider": provider,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "arm_artifacts": {"local": local["artifact"], backend: remote["artifact"]},
        "pairs": pairs,
        "trials": len(all_children),
        "accepted_trials": local["accepted_trials"] + remote["accepted_trials"],
        "failure_counts": {"local": local["failure_counts"], backend: remote["failure_counts"]},
        "score_counts": {"local": local["score_counts"], backend: remote["score_counts"]},
        "oracle_disagreements": local["oracle_disagreements"] + remote["oracle_disagreements"],
        "false_accepts": local["false_accepts"] + remote["false_accepts"],
        "agreement": {
            "seeds": count,
            "candidate_hash_agree": agree.count(True),
            "candidate_hash_mismatch": agree.count(False),
            "not_comparable": agree.count(None),
            "stdout_byte_identical": [p["stdout_byte_identical"] for p in pairs].count(True),
        },
        "isolation": {
            "requested": ISOLATION,
            "all_trials_verified": isolation_ok,
            "sandboxes_created": sum(1 for c in remote["children"] if c["sandbox_id"]),
            "sandboxes_terminated": terminated,
            "evidence": "per-trial isolation_probe and termination in each sandbox child artifact",
        },
        "latency": {
            "local_build_seconds": local_build_seconds,
            "local_parallel_wall_seconds": local["wall_seconds"],
            "local_serial_equivalent_seconds": local["trial_wall_seconds_sum"],
            "local_serial_equivalent_note": "sum of per-trial wall seconds measured under the "
            "parallel local run; no separate serial run was executed",
            "local_cpu_seconds_total": sum(c["cpu_seconds"] or 0.0 for c in local["children"]),
            "sandbox_prepare_seconds": provider["prepare_seconds"],
            "sandbox_wall_seconds": remote["wall_seconds"],
            "sandbox_wall_note": "create through terminate for all sandboxes, excluding prepare",
            "sandbox_phase_seconds_mean": {
                name: total / count for name, total in sorted(phase_sums.items())
            },
            "sandbox_solve_seconds_mean": solve_mean,
            "sandbox_overhead_seconds_mean": overhead_mean,
            "sandbox_cpu_seconds_total": None,
            "startup_overhead_dominates": overhead_mean > solve_mean,
            "sandbox_faster_than_local_serial": remote["wall_seconds"]
            < local["trial_wall_seconds_sum"],
            "sandbox_faster_than_local_parallel": remote["wall_seconds"] < local["wall_seconds"],
        },
        "cost_usd": None,
        "cost_status": COST_UNKNOWN,
        "billable_inputs": {
            "sandbox_seconds_total": remote["trial_wall_seconds_sum"],
            "cpu_cores_requested": ISOLATION["cpu"],
            "memory_mib_requested": ISOLATION["memory_mib"],
        },
        "gate_status": gate_status,
        "infrastructure_failure_classes": infrastructure,
        "mathematical_claim": "none; this is systems evidence",
    }
    path = artifact_dir / f"{run_id}.json"
    baseline.write_new_artifact(path, summary)
    return summary, path
