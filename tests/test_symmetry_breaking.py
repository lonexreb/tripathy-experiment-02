import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tripathy_experiment import baseline, symmetry_breaking

PARENT_RUN = "p0-fixture"
SOURCE_A = [[0, 0], [1, 0]]
SOURCE_B = [[0, 0], [3, 0]]

# Behaviour is selected by --seed. "near" reflects the first source point over
# the second, which creates exactly one (degenerate) isosceles triple.
FAKE_BREAKER = r"""
import json, sys
seed, iters, target = (int(sys.argv[i]) for i in (2, 4, 6))
values = [int(token) for token in sys.stdin.read().split()]
source = [[values[i], values[i + 1]] for i in range(1, len(values), 2)]
(ax, ay), (bx, by) = source
near, good = source + [[2 * bx - ax, 2 * by - ay]], source + [[5, 1]]

cap, destroy = int(sys.argv[8]), int(sys.argv[10])

def emit(score, points, violations, closest, origin="swap", depth=2, **extra):
    out = {"seed": seed, "iters": iters, "target": target, "grid_size": 32, "score": score,
           "points": points, "termination_reason": "fake", "solver_version": "fake",
           "repair_node_cap": cap, "destroy_size": destroy, "best_state_origin": origin,
           "counters": {"min_working_violations": violations, "restarts": 1,
                        "repair_attempts": 2, "repair_nodes": 9, "repair_attempts_exhausted": 2,
                        "repair_max_depth": depth, "repair_destroy_size": destroy,
                        "repair_pool_min": 2, "repair_pool_max": 7},
           "closest_approach": {"violations": violations, "points": closest}}
    out.update(extra)
    print(json.dumps(out))

if seed == 0: emit(2, source, 1, near)            # truthful negative result
elif seed == 1: emit(3, good, 0, good, "exact_repair", 3)  # truthful repaired target
elif seed == 2: emit(3, near, 0, near)            # false accept
elif seed == 3: emit(2, source, 5, near)          # lies about the closest approach
elif seed == 4: emit(2, source, 1, near, closest_approach=None)
elif seed == 5: sys.exit(7)
elif seed == 6: emit(2, [[9, 9], [9, 12]], 1, near)  # valid set that is not the source
elif seed == 7: emit(2, source, 1, near, "exact_repair")  # claims a repair it did not emit
elif seed == 8: emit(2, source, 1, near, depth=3)  # full depth without a target
elif seed == 9: emit(2, source, 1, near, "magic")  # unknown origin
elif seed == 10: emit(2, source, 1, near, destroy_size=1)  # echoes another destroy size
"""


def write_p0_fixture(runs: Path) -> None:
    """A fake passed P0 run: sources A, B, a duplicate of A, and one lower score."""
    children = []
    for seed, points in enumerate((SOURCE_A, SOURCE_B, SOURCE_A, [[4, 4]])):
        trial_id = f"{PARENT_RUN}.trial-{seed:04d}"
        child = {
            "kind": "baseline-trial",
            "run_id": PARENT_RUN,
            "trial_id": trial_id,
            "seed": seed,
            "score": len(points),
            "failure_class": None,
            "points": points,
            "candidate_sha256": baseline.canonical_sha256(sorted(points)),
        }
        baseline.write_new_artifact(runs / f"{trial_id}.json", child)
        children.append({k: v for k, v in child.items() if k not in ("points", "kind")})
    parent = {
        "kind": "baseline-summary",
        "run_id": PARENT_RUN,
        "gate_status": "passed",
        "git": {"head": "fixture"},
        "children": children,
    }
    baseline.write_new_artifact(runs / f"{PARENT_RUN}.json", parent)


def run_fake(
    tmp_path: Path, seeds: list[int], destroy_size: int = 2
) -> tuple[dict[str, Any], Path]:
    runs = tmp_path / "runs"
    if not runs.exists():
        write_p0_fixture(runs)
    script = tmp_path / "fake-breaker.py"
    script.write_text(f"#!{sys.executable}\n{FAKE_BREAKER}", encoding="utf-8")
    script.chmod(0o755)
    return symmetry_breaking.run_smoke(
        parent_run_id=PARENT_RUN,
        seeds=seeds,
        iters=10,
        workers=4,
        artifact_dir=runs,
        timeout_seconds=30.0,
        linear_issue="TRI-19",
        experiment_id="02",
        target=3,
        repair_nodes=50,
        destroy_size=destroy_size,
        breaker_binary=str(script),
    )


def test_clean_smoke_passes_and_a_target_needs_fresh_process_verification(tmp_path: Path) -> None:
    summary, summary_path = run_fake(tmp_path, [0, 1])
    before = {p.name: p.read_bytes() for p in (tmp_path / "runs").glob(f"{PARENT_RUN}*")}
    assert summary_path.exists() and summary["kind"] == "p1-smoke-summary"
    assert summary["gate_status"] == "passed" and summary["failure_counts"] == {}
    assert summary["search_outcome"] == "verified_target_found"
    assert summary["search_progress"] == "record_candidate"
    assert summary["best_state_origin_by_seed"] == {"0": "swap", "1": "exact_repair"}
    assert summary["repair"] | {"max_depth_by_seed": None} == {
        "destroy_size": 2, "node_cap_per_attempt": 50, "full_depth": 3, "max_depth": 3,
        "max_depth_by_seed": None, "attempts": 4, "attempts_exhausted": 4, "attempts_capped": 0,
        "nodes": 18,
        "pool_min": 2, "pool_max": 7,
    }  # fmt: skip
    assert summary["config"]["repair_nodes_per_attempt"] == 50
    assert summary["config"]["destroy_size"] == 2 and summary["config"]["repair_additions"] == 3
    child_zero = json.loads(Path(summary["children"][0]["artifact"]).read_text(encoding="utf-8"))
    assert child_zero["destroy_size"] == 2 and "--destroy-size" in child_zero["command"]
    assert summary["record_claim"] is False and summary["cost_usd"] == 0.0
    assert summary["score_counts"] == {"2": 1, "3": 1} and summary["best_score"] == 3
    assert summary["verified_target_seeds"] == [1]
    assert summary["min_working_violations_by_seed"] == {"0": 1, "1": 0}
    assert summary["determinism_replay"]["identical"] is True
    assert summary["source_run"]["run_id"] == PARENT_RUN and summary["git"]["head"]
    # distinct sources only (A is listed once with both of its P0 trials), round-robin
    assert [s["p0_seed"] for s in summary["sources"]] == [0, 1]
    assert summary["sources"][0]["p0_trial_ids"] == [
        f"{PARENT_RUN}.trial-0000",
        f"{PARENT_RUN}.trial-0002",
    ]
    negative, found = summary["children"]
    assert negative["source_candidate_sha256"] != found["source_candidate_sha256"]
    assert negative["output_equals_source"] is True and negative["persisted_verification"] is None
    verification = found["persisted_verification"]
    assert verification["accepted"] and verification["upstream_accepts"]
    assert verification["oracle_distance_valid"] and verification["oracle_bisector_valid"]
    child = json.loads(Path(found["artifact"]).read_text(encoding="utf-8"))
    assert verification["artifact_sha256"] == hashlib.sha256(
        Path(found["artifact"]).read_bytes()
    ).hexdigest()
    assert child["kind"] == "p1-smoke-trial" and child["source_reverification"]["accepted"]
    assert child["closest_approach"]["recounted_violations"] == 0
    assert child["record_claim"] is False
    after = {p.name: p.read_bytes() for p in (tmp_path / "runs").glob(f"{PARENT_RUN}*")}
    assert after == before  # the P0 parent and children are never rewritten


def test_every_failure_class_becomes_an_artifact_and_fails_the_gate(tmp_path: Path) -> None:
    summary, _ = run_fake(tmp_path, list(range(11)))
    classes = {child["seed"]: child["failure_class"] for child in summary["children"]}
    assert classes == {
        0: None,
        1: None,
        2: "invalid_candidate",
        3: "closest_approach_mismatch",
        4: "malformed_output",
        5: "crash",
        6: "unexpected_candidate",
        7: "repair_counter_mismatch",
        8: "repair_counter_mismatch",
        9: "malformed_output",
        10: "repair_counter_mismatch",
    }
    assert all(Path(child["artifact"]).exists() for child in summary["children"])
    assert summary["gate_status"] == "infrastructure_failure"
    assert summary["verified_target_count"] == 1 and summary["score_counts"] == {"2": 1, "3": 1}
    false_accept = json.loads(Path(summary["children"][2]["artifact"]).read_text(encoding="utf-8"))
    assert false_accept["score"] is None and false_accept["claimed_score"] == 3


def test_search_progress_uses_the_three_plan_classes(tmp_path: Path) -> None:
    # (three lattice points cannot have exactly two isosceles triples, so the
    # no-progress class is checked on the classifier, not through the fake)
    classify = symmetry_breaking.classify_progress
    assert classify(1, 0, True) == "record_candidate"
    assert classify(0, 1, False) == "operator_progress"  # below iteration 1's two violations
    assert classify(0, 2, True) == "operator_progress"  # full depth, e.g. rejected later
    assert classify(0, 2, False) == classify(0, None, False) == "no_progress"
    one, _ = run_fake(tmp_path / "one", [0])  # one violation, repair depth 2 of 3
    assert one["search_progress"] == "operator_progress"
    assert one["gate_status"] == "passed" and one["record_claim"] is False


def test_a_target_rejected_after_persistence_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        symmetry_breaking,
        "verify_persisted_in_fresh_process",
        lambda path, root: {"accepted": False, "detail": "stub rejection"},
    )
    summary, _ = run_fake(tmp_path, [1])
    assert summary["verified_target_count"] == 0 and summary["best_score"] is None
    assert summary["failure_counts"] == {"persisted_verification_failed": 1}
    assert summary["gate_status"] == "infrastructure_failure"
    assert summary["search_outcome"] == "no_target_found"


def test_tampered_or_reserved_inputs_stop_the_run(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_p0_fixture(runs)
    with pytest.raises(ValueError, match="reserved"):
        run_fake(tmp_path, [64])
    for bad_destroy in (0, 3, -1):  # the fixture sources have 2 points
        with pytest.raises(ValueError, match="destroy_size"):
            run_fake(tmp_path, [0], destroy_size=bad_destroy)
    child_path = runs / f"{PARENT_RUN}.trial-0001.json"
    child = json.loads(child_path.read_text(encoding="utf-8"))
    child["points"] = [[0, 0], [2, 0]]  # still valid, but no longer what P0 hashed
    child_path.write_text(json.dumps(child), encoding="utf-8")
    with pytest.raises(ValueError, match="failed source re-verification"):
        run_fake(tmp_path, [0])
    assert not list(runs.glob("*-*-*-*-*.json"))  # no P1 artifact was written


def test_verify_persisted_rejects_an_isosceles_set(tmp_path: Path) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({"score": 3, "points": [[0, 0], [1, 0], [2, 0]]}), encoding="utf-8")
    result = symmetry_breaking.verify_persisted(path)
    assert result["upstream_verifier_pinned"] and not result["upstream_accepts"]
    assert not result["accepted"]
    assert symmetry_breaking.isosceles_count(((0, 0), (1, 0), (2, 0), (1, 1))) == 4


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_real_breaker_is_deterministic_exact_and_never_emits_an_invalid_set(
    tmp_path: Path,
) -> None:
    source = symmetry_breaking.BREAKER_SOURCE.read_text(encoding="utf-8")
    assert "fopen" not in source and "benchmarks" not in source and "[11,23]" not in source
    built = baseline.build_solver(Path("."), tmp_path, symmetry_breaking.BREAKER_SOURCE)
    binary = str(built["binary"])

    def run(stdin: str, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [binary, *arguments], input=stdin.encode(), capture_output=True, cwd=tmp_path, env={}
        )

    # The published 58 is development data here; the breaker gets it only as stdin.
    public = json.loads(Path("benchmarks/no_isosceles_n32.json").read_text(encoding="utf-8"))
    points = tuple((x, y) for x, y in public["points"])
    stdin = f"{len(points)}\n" + "".join(f"{x} {y}\n" for x, y in points)
    arguments = (
        "--seed", "7", "--iters", "45000", "--target", "59", "--repair-nodes", "20000",
        "--destroy-size", "8",
    )  # fmt: skip
    first, second = run(stdin, *arguments), run(stdin, *arguments)
    assert first.returncode == 0 and first.stdout == second.stdout
    assert run(stdin, *("--seed", "8", *arguments[2:])).stdout != first.stdout
    payload = baseline.parse_candidate(first.stdout, 7, 45000)
    counters = payload["counters"]
    # exit 0 means every internal brute-force recount agreed, including across restarts
    assert counters["restarts"] >= 1 and counters["brute_force_checks"] >= 3
    emitted = tuple((x, y) for x, y in payload["points"])
    near = tuple((x, y) for x, y in payload["closest_approach"]["points"])
    assert symmetry_breaking.dual_verify(emitted)["accepted"]
    if payload["score"] == 58:  # the expected outcome: an honest negative result
        assert sorted(emitted) == sorted(points)
        assert payload["termination_reason"] == "iterations_exhausted"
        assert not symmetry_breaking.dual_verify(near)["accepted"]
    assert len(set(near)) == 59
    assert (
        symmetry_breaking.isosceles_count(near)
        == payload["closest_approach"]["violations"]
        == counters["min_working_violations"]
    )

    # exact repair: one attempt at startup and one per restart, never past the node cap
    assert counters["repair_attempts"] == counters["restarts"] + 1
    assert counters["repair_destroy_size"] == payload["destroy_size"] == 8
    assert payload["repair_node_cap"] == 20000
    assert 0 < counters["repair_nodes"] <= counters["repair_attempts"] * 20000
    assert counters["repair_pool_min"] >= 8  # the eight destroyed points always fit back
    assert (counters["repair_max_depth"] == 9) == (payload["best_state_origin"] == "exact_repair")
    assert (payload["score"] == 59) or payload["best_state_origin"] == "swap"

    # A 3-point input is destroyed completely; the repair must rebuild 4 points exactly.
    small_in = "3\n0 0\n1 0\n3 1\n"
    small = json.loads(
        run(small_in, "--seed", "1", "--iters", "9", "--target", "4", "--repair-nodes", "99",
            "--destroy-size", "3").stdout
    )  # fmt: skip
    assert small["destroy_size"] == small["counters"]["repair_destroy_size"] == 3
    assert small["score"] == 4 and small["termination_reason"] == "target_reached"
    assert small["best_state_origin"] == "exact_repair"
    assert small["counters"]["repair_max_depth"] == 4 and small["counters"]["swaps"] == 0
    assert symmetry_breaking.dual_verify(tuple((x, y) for x, y in small["points"]))["accepted"]
    # With a zero node cap the repair cannot branch and the swap fallback finds the target.
    capped = json.loads(
        run(small_in, "--seed", "1", "--iters", "9", "--target", "4", "--repair-nodes", "0",
            "--destroy-size", "1").stdout
    )  # fmt: skip
    assert capped["score"] == 4 and capped["best_state_origin"] == "swap"
    assert capped["counters"]["repair_nodes"] == capped["counters"]["repair_max_depth"] == 0
    assert capped["counters"]["repair_attempts_exhausted"] == 0
    assert {(0, 0), (1, 0), (3, 1)} < {(x, y) for x, y in capped["points"]}

    ok = ("--seed", "1", "--iters", "5", "--target", "4", "--repair-nodes", "9",
          "--destroy-size", "2")  # fmt: skip
    for bad_stdin in (
        "3\n0 0\n1 0\n2 0\n",  # isosceles input
        "3\n0 0\n1 0\n1 0\n",  # duplicate
        "3\n0 0\n1 0\n32 1\n",  # outside the grid
        "3\n0 0\n1 0\n3 1\n9\n",  # trailing data
        "2\n0 0\n1 0\n",  # count is not target-1
        "",
    ):
        assert run(bad_stdin, *ok).returncode == 2
    assert run(small_in, "--seed", "x", *ok[2:]).returncode == 2
    assert run(small_in, *ok[:6], *ok[8:]).returncode == 2  # --repair-nodes is required
    assert run(small_in, *ok[:8]).returncode == 2  # --destroy-size is required
    for bad_destroy in ("0", "4", "-1", "x"):  # must be 1..3 for a 3-point input
        assert run(small_in, *ok[:9], bad_destroy).returncode == 2
    assert run(small_in, *ok[:9], "1").returncode == 0
