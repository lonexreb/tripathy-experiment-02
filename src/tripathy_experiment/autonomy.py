"""P3 evidence-to-decision-to-action transition with explicit rollback."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import baseline
from .symmetry_breaking import CONFIRMATORY_SEEDS

P1_RUNS = (
    "418e67a9-dca8-4d0d-ac3d-1b5355bf6a45",
    "ff52f29c-b4e5-4620-993d-5236b324991e",
    "e46d5be6-98e0-43ae-848b-3a439246c249",
)
P2_RUN = "eaacf19f-08a7-46c3-8b89-6486492c601f"
ASYMMETRIC_SOURCE = Path("solver/asymmetric_greedy.c")
PLAN = Path("docs/P3_CAUSAL_AUTONOMY_PLAN.md")
PREREGISTERED = {
    "seeds": [1400, 1401, 1402, 1403],
    "iters": 250,
    "workers": 4,
    "timeout_seconds": 120.0,
}
INCUMBENT_SCORE = 58


def _read_parent(artifact_dir: Path, run_id: str, kind: str) -> tuple[dict[str, Any], Path]:
    path = artifact_dir / f"{run_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read evidence {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("run_id") != run_id:
        raise ValueError(f"{path} does not contain run {run_id}")
    if payload.get("kind") != kind or payload.get("gate_status") != "passed":
        raise ValueError(f"{path} is not a passed {kind}")
    return payload, path


def extract_signals(artifact_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read registered signals and return them with hashed provenance."""
    evidence = []
    p1 = []
    for run_id in P1_RUNS:
        parent, path = _read_parent(artifact_dir, run_id, "p1-smoke-summary")
        p1.append(parent)
        evidence.append(
            {
                "run_id": run_id,
                "kind": parent["kind"],
                "path": str(path),
                "sha256": baseline.sha256_file(path),
            }
        )
    p2, p2_path = _read_parent(artifact_dir, P2_RUN, "p2-comparison")
    evidence.append(
        {
            "run_id": P2_RUN,
            "kind": p2["kind"],
            "path": str(p2_path),
            "sha256": baseline.sha256_file(p2_path),
        }
    )
    minimums = [int(run["min_working_violations"]) for run in p1]
    return (
        {
            "passed_p1_iterations": len(p1),
            "verified_59_count": sum(int(run["verified_target_count"]) for run in p1),
            "minimum_working_violations": min(minimums),
            "all_p1_minimums": minimums,
            "p1_no_progress_iterations": sum(
                run.get("search_outcome") == "no_target_found" for run in p1
            ),
            "modal_startup_overhead_dominates": bool(
                p2["latency"]["startup_overhead_dominates"]
            ),
            "modal_faster_than_local_parallel": bool(
                p2["latency"]["sandbox_faster_than_local_parallel"]
            ),
        },
        evidence,
    )


def select_action(signals: dict[str, Any]) -> tuple[str, str]:
    """Apply the preregistered rule order; return action and reason code."""
    if int(signals["verified_59_count"]) > 0:
        return "freeze_candidate", "verified_59_exists"
    if int(signals["minimum_working_violations"]) < 2:
        return "deepen_exact_repair", "operator_progress_below_two_conflicts"
    if (
        int(signals["passed_p1_iterations"]) >= 3
        and int(signals["p1_no_progress_iterations"]) >= 3
        and list(signals["all_p1_minimums"]) == [2, 2, 2]
    ):
        return "asymmetric_random_greedy_screen", "stopped_family_needs_structural_change"
    return "collect_more_evidence", "insufficient_stopping_evidence"


def _decision(
    *,
    artifact_dir: Path,
    seeds: list[int],
    iters: int,
    workers: int,
    timeout_seconds: float,
    root: Path,
) -> tuple[dict[str, Any], Path]:
    signals, evidence = extract_signals(artifact_dir)
    action, reason = select_action(signals)
    decision_id = str(uuid4())
    spec = {
        "solver_source": str(ASYMMETRIC_SOURCE),
        "initialization": "empty grid; no certificate or incumbent candidate",
        "seeds": seeds,
        "iters": iters,
        "workers": workers,
        "timeout_seconds": timeout_seconds,
        "promotion_score": INCUMBENT_SCORE,
        "reserved_confirmatory_seeds": "64..127 untouched",
        "matches_preregistration": {
            "seeds": seeds,
            "iters": iters,
            "workers": workers,
            "timeout_seconds": timeout_seconds,
        }
        == PREREGISTERED,
    }
    candidates = [
        {
            "action": "freeze_candidate",
            "eligible": int(signals["verified_59_count"]) > 0,
            "reason": "requires a verified 59",
        },
        {
            "action": "deepen_exact_repair",
            "eligible": int(signals["minimum_working_violations"]) < 2,
            "reason": "requires measured progress below two conflicts",
        },
        {
            "action": "continue_destroy_repair",
            "eligible": False,
            "reason": "forbidden by the P1 preregistered stopping boundary",
        },
        {
            "action": "modal_scale_same_short_solver",
            "eligible": False,
            "reason": "P2 startup overhead dominated and P1 showed no algorithmic progress",
        },
        {
            "action": "asymmetric_random_greedy_screen",
            "eligible": action == "asymmetric_random_greedy_screen",
            "reason": "structurally different from the stopped seeded-repair family",
        },
    ]
    payload = {
        "schema_version": 1,
        "kind": "causal-decision",
        "decision_id": decision_id,
        "linear_issue": "TRI-19",
        "created_at": datetime.now(UTC).isoformat(),
        "git": baseline.git_identity(root),
        "input_evidence": evidence,
        "signals": signals,
        "candidates": candidates,
        "selected_action": action,
        "reason_code": reason,
        "experiment_spec": spec if action == "asymmetric_random_greedy_screen" else None,
        "budget": {"cost_usd": 0.0, "provider_calls": 0, "trials": len(seeds)},
        "rollback_rule": (
            "retain solver/solver.c unless the canary reaches 58 with a passed gate; "
            "screening never overwrites the incumbent"
        ),
        "record_claim": False,
        "file_sha256": {
            str(path): baseline.sha256_file(root / path)
            for path in (PLAN, ASYMMETRIC_SOURCE, Path("src/tripathy_experiment/autonomy.py"))
        },
    }
    path = artifact_dir / f"{decision_id}.decision.json"
    baseline.write_new_artifact(path, payload)
    return payload, path


def run_autonomy_transition(
    *,
    seeds: list[int],
    iters: int,
    workers: int,
    timeout_seconds: float,
    artifact_dir: Path,
    linear_issue: str,
    experiment_id: str,
    root: Path = Path("."),
) -> tuple[dict[str, Any], Path]:
    """Persist a decision, execute its selected canary, and persist rollback."""
    if not seeds or iters < 1 or workers < 1 or timeout_seconds <= 0:
        raise ValueError("positive seeds, iters, workers and timeout are required")
    if set(seeds) & set(CONFIRMATORY_SEEDS):
        raise ValueError("seeds 64..127 are reserved and must stay untouched")
    incumbent_before = baseline.sha256_file(root / baseline.SOLVER_SOURCE)
    decision, decision_path = _decision(
        artifact_dir=artifact_dir,
        seeds=seeds,
        iters=iters,
        workers=workers,
        timeout_seconds=timeout_seconds,
        root=root,
    )
    if decision["selected_action"] != "asymmetric_random_greedy_screen":
        raise RuntimeError(f"policy selected non-executable action {decision['selected_action']}")
    action, action_path = baseline.run_baseline(
        seeds=seeds,
        iters=iters,
        workers=workers,
        artifact_dir=artifact_dir,
        timeout_seconds=timeout_seconds,
        gate_label="p3-autonomy-canary",
        linear_issue=linear_issue,
        experiment_id=experiment_id,
        root=root,
        solver_source=ASYMMETRIC_SOURCE,
    )
    best = int(action.get("best_score") or 0)
    eligible = (
        action["gate_status"] == "passed"
        and action["oracle_disagreements"] == 0
        and best >= INCUMBENT_SCORE
    )
    incumbent_after = baseline.sha256_file(root / baseline.SOLVER_SOURCE)
    spec = decision["experiment_spec"]
    action_matches = all(
        action["config"][key] == spec[key]
        for key in ("seeds", "iters", "workers", "timeout_seconds")
    ) and action["solver_build"]["source"] == spec["solver_source"]
    transition = {
        "schema_version": 1,
        "kind": "autonomy-transition",
        "transition_id": decision["decision_id"],
        "linear_issue": linear_issue,
        "experiment_id": experiment_id,
        "completed_at": datetime.now(UTC).isoformat(),
        "decision_artifact": str(decision_path),
        "decision_sha256": baseline.sha256_file(decision_path),
        "decision_created_at": decision["created_at"],
        "selected_action": decision["selected_action"],
        "reason_code": decision["reason_code"],
        "action_run_id": action["run_id"],
        "action_artifact": str(action_path),
        "action_sha256": baseline.sha256_file(action_path),
        "action_started_at": action["started_at"],
        "decision_precedes_action": decision["created_at"] <= action["started_at"],
        "action_matches_decision_spec": action_matches,
        "gate_status": (
            "passed"
            if action["gate_status"] in ("passed", "failed")
            and action["oracle_disagreements"] == 0
            else "infrastructure_failure"
        ),
        "action_search_gate_status": action["gate_status"],
        "trials": action["trials"],
        "score_counts": action["score_counts"],
        "best_score": best,
        "oracle_disagreements": action["oracle_disagreements"],
        "promotion": {
            "threshold": INCUMBENT_SCORE,
            "status": "eligible_for_confirmation" if eligible else "rolled_back",
            "reason": (
                "matched incumbent under a passed screening gate; confirmation still required"
                if eligible
                else "screening result did not match the incumbent"
            ),
        },
        "rollback": {
            "incumbent_source": str(baseline.SOLVER_SOURCE),
            "sha256_before": incumbent_before,
            "sha256_after": incumbent_after,
            "incumbent_unchanged": incumbent_before == incumbent_after,
            "negative_evidence_retained": not eligible,
        },
        "cost_usd": 0.0,
        "record_claim": False,
    }
    if (
        not transition["decision_precedes_action"]
        or not action_matches
        or incumbent_before != incumbent_after
    ):
        transition["gate_status"] = "infrastructure_failure"
    path = artifact_dir / f"{decision['decision_id']}.transition.json"
    baseline.write_new_artifact(path, transition)
    return transition, path
