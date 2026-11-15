"""P3 causal policy and action-transition tests."""

import json
import shutil
from pathlib import Path

import pytest

from tripathy_experiment import autonomy, baseline


def test_policy_selects_structural_change_from_canonical_evidence() -> None:
    signals, evidence = autonomy.extract_signals(Path("artifacts/runs"))
    assert signals == {
        "passed_p1_iterations": 3,
        "verified_59_count": 0,
        "minimum_working_violations": 2,
        "all_p1_minimums": [2, 2, 2],
        "p1_no_progress_iterations": 3,
        "modal_startup_overhead_dominates": True,
        "modal_faster_than_local_parallel": False,
    }
    assert autonomy.select_action(signals) == (
        "asymmetric_random_greedy_screen",
        "stopped_family_needs_structural_change",
    )
    assert len(evidence) == 4 and all(len(item["sha256"]) == 64 for item in evidence)


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"verified_59_count": 1}, "freeze_candidate"),
        ({"minimum_working_violations": 1}, "deepen_exact_repair"),
        ({"passed_p1_iterations": 2}, "collect_more_evidence"),
    ],
)
def test_policy_rule_order(updates: dict[str, object], expected: str) -> None:
    signals, _ = autonomy.extract_signals(Path("artifacts/runs"))
    signals.update(updates)
    assert autonomy.select_action(signals)[0] == expected


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_asymmetric_solver_is_deterministic_and_dual_verified(tmp_path: Path) -> None:
    solver = baseline.build_solver(Path("."), tmp_path / "build", autonomy.ASYMMETRIC_SOURCE)
    first = baseline.run_trial(str(solver["binary"]), 2400, 3, 30)
    second = baseline.run_trial(str(solver["binary"]), 2400, 3, 30)
    assert first["failure_class"] is second["failure_class"] is None
    assert first["candidate_sha256"] == second["candidate_sha256"]
    assert first["solver_version"] == "asymmetric-random-greedy-v1"
    points = {tuple(point) for point in first["points"]}
    assert any((x, 31 - y) not in points for x, y in points)


def _copy_policy_evidence(destination: Path) -> None:
    destination.mkdir()
    for run_id in (*autonomy.P1_RUNS, autonomy.P2_RUN):
        source = Path("artifacts/runs") / f"{run_id}.json"
        shutil.copy2(source, destination / source.name)


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_transition_persists_decision_before_action_and_rolls_back(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "runs"
    _copy_policy_evidence(artifact_dir)
    transition, path = autonomy.run_autonomy_transition(
        seeds=[2400, 2401],
        iters=3,
        workers=2,
        timeout_seconds=30,
        artifact_dir=artifact_dir,
        linear_issue="TRI-19",
        experiment_id="02",
    )
    assert path.exists() and transition["gate_status"] == "passed"
    assert transition["decision_precedes_action"] is True
    assert transition["action_matches_decision_spec"] is True
    assert transition["promotion"]["status"] == "rolled_back"
    assert transition["rollback"]["incumbent_unchanged"] is True
    decision = json.loads(Path(transition["decision_artifact"]).read_text(encoding="utf-8"))
    assert decision["selected_action"] == "asymmetric_random_greedy_screen"
    assert decision["experiment_spec"]["matches_preregistration"] is False


def test_reserved_confirmatory_seeds_are_refused_before_decision(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reserved"):
        autonomy.run_autonomy_transition(
            seeds=[64],
            iters=1,
            workers=1,
            timeout_seconds=1,
            artifact_dir=tmp_path,
            linear_issue="TRI-19",
            experiment_id="02",
        )
    assert list(tmp_path.iterdir()) == []
