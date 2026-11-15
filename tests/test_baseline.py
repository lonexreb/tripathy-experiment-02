import json
import shutil
import subprocess
from math import comb
from pathlib import Path

import pytest

from tripathy_experiment import baseline, no_isosceles, perpendicular_bisector_oracle

FAKE_SOLVER = r"""#!/bin/sh
# argv: --seed S --iters N ; behaviour is selected by the seed
tail='"counters":{},"termination_reason":"fake","solver_version":"fake"}'
ok() { echo "{\"seed\":$2,\"iters\":$4,\"grid_size\":32,\"score\":$5,\"points\":$6,$tail"; }
case "$2" in
  0) ok "$@" 2 "[[0,0],[1,0]]" ;;
  1) echo "not json" ;;
  2) echo "boom" >&2; exit 7 ;;
  3) exec /bin/sleep 30 ;;
  4) exec /usr/bin/yes ;;
  5) ok "$@" 3 "[[0,0],[1,0],[2,0]]" ;;
  6) ok "$@" 9 "[[0,0],[1,0]]" ;;
  7) ok "$@" 1 "[[0.5,1]]" ;;
esac
"""

REQUIRED_CHILD_FIELDS = {
    "run_id", "trial_id", "git", "file_sha256", "config", "config_sha256", "command", "seed",
    "iters", "wall_seconds", "cpu_seconds", "score", "oracle_distance", "oracle_bisector",
    "oracles_agree", "failure_class", "solver_termination_reason", "cost_usd", "runtime",
    "linear_issue", "solver_build",
}


def run_fake(tmp_path: Path, seeds: list[int]) -> tuple[dict[str, object], Path]:
    script = tmp_path / "fake-solver.sh"
    script.write_text(FAKE_SOLVER, encoding="utf-8")
    script.chmod(0o755)
    return baseline.run_baseline(
        seeds=seeds,
        iters=10,
        workers=4,
        artifact_dir=tmp_path / "runs",
        timeout_seconds=1.0,
        gate_label="screening",
        linear_issue="TRI-19",
        experiment_id="02",
        solver_binary=str(script),
    )


def test_every_outcome_class_becomes_an_artifact(tmp_path: Path) -> None:
    summary, summary_path = run_fake(tmp_path, list(range(8)))
    children = sorted((tmp_path / "runs").glob("*.trial-*.json"))
    assert len(children) == 8 and summary_path.exists()
    assert not list((tmp_path / "runs").glob(".tmp-*"))
    classes = {}
    for child in children:
        payload = json.loads(child.read_text(encoding="utf-8"))
        assert payload.keys() >= REQUIRED_CHILD_FIELDS
        assert payload["git"]["head"] and payload["cost_usd"] == 0.0
        classes[payload["seed"]] = payload["failure_class"]
    assert classes == {
        0: None,
        1: "malformed_output",
        2: "crash",
        3: "timeout",
        4: "output_too_large",
        5: "invalid_candidate",
        6: "score_mismatch",
        7: "malformed_output",
    }
    assert summary["score_counts"] == {"2": 1}
    assert summary["gate_status"] == "infrastructure_failure"
    assert summary["reach_target_count"] == 0 and summary["oracle_disagreements"] == 0


def test_oracle_disagreement_is_preserved_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        perpendicular_bisector_oracle,
        "verify",
        lambda points, grid_size: perpendicular_bisector_oracle.BisectorResult(
            True, len(points), "stub that accepts everything"
        ),
    )
    summary, _ = run_fake(tmp_path, [5])
    (child,) = (tmp_path / "runs").glob("*.trial-*.json")
    payload = json.loads(child.read_text(encoding="utf-8"))
    assert payload["failure_class"] == "oracle_disagreement" and payload["score"] is None
    assert payload["points"] == [[0, 0], [1, 0], [2, 0]]
    assert summary["oracle_disagreements"] == 1
    assert summary["gate_status"] == "infrastructure_failure"


def test_artifacts_are_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    baseline.write_new_artifact(path, {"value": 1})
    with pytest.raises(FileExistsError):
        baseline.write_new_artifact(path, {"value": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}
    assert [entry.name for entry in tmp_path.iterdir()] == ["artifact.json"]


def test_exact_binomial_interval_matches_closed_forms() -> None:
    low, high = baseline.exact_binomial_interval(0, 64)
    assert low == 0.0 and high == pytest.approx(1 - 0.025 ** (1 / 64), abs=1e-9)
    low, high = baseline.exact_binomial_interval(64, 64)
    assert high == 1.0 and low == pytest.approx(0.025 ** (1 / 64), abs=1e-9)
    low, high = baseline.exact_binomial_interval(15, 200)

    def tail(p: float, start: int, stop: int) -> float:
        return sum(comb(200, k) * p**k * (1 - p) ** (200 - k) for k in range(start, stop + 1))

    assert low < 15 / 200 < high
    assert tail(low, 15, 200) == pytest.approx(0.025, abs=1e-9)  # P(X >= 15 | low)
    assert tail(high, 0, 15) == pytest.approx(0.025, abs=1e-9)  # P(X <= 15 | high)


def test_parse_seeds() -> None:
    assert baseline.parse_seeds("0-63") == list(range(64))
    assert baseline.parse_seeds("3,7-9") == [3, 7, 8, 9]
    for bad in ("", "5-2", "1,1", "a"):
        with pytest.raises(ValueError):
            baseline.parse_seeds(bad)


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_real_solver_is_deterministic_valid_and_never_reads_the_certificate(
    tmp_path: Path,
) -> None:
    source = baseline.SOLVER_SOURCE.read_text(encoding="utf-8")
    assert "fopen" not in source and "benchmarks" not in source and "[11,23]" not in source
    binary = str(baseline.build_solver(Path("."), tmp_path)["binary"])
    command = [binary, "--seed", "7", "--iters", "3000"]
    first = subprocess.run(command, capture_output=True, check=True, cwd=tmp_path, env={})
    second = subprocess.run(command, capture_output=True, check=True, cwd=tmp_path, env={})
    assert first.stdout == second.stdout and first.stdout.count(b"\n") == 1
    payload = baseline.parse_candidate(first.stdout, 7, 3000)
    points = tuple((x, y) for x, y in payload["points"])
    assert payload["score"] == len(points) >= 30
    assert {(x, 31 - y) for x, y in points} == set(points)
    assert no_isosceles.verify(points, 32).valid
    assert perpendicular_bisector_oracle.verify(points, 32).valid
    other = subprocess.run([binary, "--seed", "8", "--iters", "3000"], capture_output=True)
    assert other.stdout != first.stdout
    for bad in (["--seed", "x", "--iters", "5"], ["--seed", "1"], ["--iters", "-3", "--seed", "1"]):
        assert subprocess.run([binary, *bad], capture_output=True).returncode == 2
