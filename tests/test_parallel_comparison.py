"""P2 controller tests against fake sandboxes; no Modal credentials or network."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tripathy_experiment import cli, perpendicular_bisector_oracle
from tripathy_experiment import parallel_comparison as pc
from tripathy_experiment.parallel_comparison import ExecResult

PROBE_OK = json.dumps(
    {
        "network_blocked": True, "env_names": ["GPG_KEY", "HOME", "PATH"], "kernel": "fake",
        "env_name_count": 3, "mount_points": [],
    }
).encode()


def solver_json(seed: int, iters: int, points: list[list[int]], score: int | None = None) -> bytes:
    return json.dumps(
        {
            "seed": seed, "iters": iters, "grid_size": 32, "points": points,
            "score": len(points) if score is None else score, "counters": {},
            "termination_reason": "fake", "solver_version": "fake",
        }
    ).encode()


class FakeSandbox:
    """Scripted sandbox: ``mode`` selects one failure, anything else succeeds."""

    def __init__(self, gateway: "FakeGateway", mode: str) -> None:
        self.gateway, self.mode, self.sandbox_id = gateway, mode, f"sb-fake-{mode}"
        self.files: dict[str, bytes] = {}

    def write_file(self, name: str, data: bytes) -> None:
        self.files[name] = b"tampered" if self.mode == "source_mismatch" else data

    def exec(self, command: list[str], timeout_seconds: int, max_stdout_bytes: int) -> ExecResult:
        mode = self.mode
        if command[0] == "cat":
            return ExecResult(0, self.files[command[1]], "")
        if command[0] == "cc":
            return ExecResult(1 if mode == "build_failure" else 0, b"", "error: nope")
        if command == pc.PROBE_COMMAND:
            if mode == "network_open":
                return ExecResult(0, PROBE_OK.replace(b"true", b"false"), "")
            if mode == "secret_env":
                return ExecResult(0, PROBE_OK.replace(b'"HOME"', b'"EXA_API_KEY"'), "")
            if mode == "env_truncated":
                payload = PROBE_OK.replace(b'"env_name_count": 3', b'"env_name_count": 4')
                return ExecResult(0, payload, "")
            return ExecResult(0, b"garbage" if mode == "bad_probe" else PROBE_OK, "")
        seed, iters = int(command[2]), int(command[4])
        if mode == "timeout":
            raise TimeoutError("fake exec timeout")
        if mode == "provider_error":
            raise ConnectionError("fake provider outage")
        outputs = {
            "crash": ExecResult(7, b"", "boom"),
            "malformed": ExecResult(0, b"not json", ""),
            "too_large": ExecResult(None, b"y" * (max_stdout_bytes + 1), ""),
            "invalid": ExecResult(0, solver_json(seed, iters, [[0, 0], [1, 0], [2, 0]]), ""),
            "score_mismatch": ExecResult(0, solver_json(seed, iters, [[0, 0], [1, 0]], 9), ""),
            "wrong_seed": ExecResult(0, solver_json(seed + 1, iters, [[0, 0], [1, 0]]), ""),
        }
        return outputs.get(mode, ExecResult(0, solver_json(seed, iters, [[0, 0], [1, 0]]), ""))

    def terminate(self) -> int | None:
        self.gateway.terminated.append(self.sandbox_id)
        if self.mode == "terminate_error":
            raise RuntimeError("fake terminate failure")
        return 137


class FakeGateway:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.created: list[dict[str, Any]] = []
        self.terminated: list[str] = []

    def describe(self) -> dict[str, Any]:
        return {"provider": "fake"}

    def prepare(self) -> None:
        if self.mode == "prepare_error":
            raise RuntimeError("fake image build failure")

    def create(self, isolation: dict[str, Any]) -> FakeSandbox:
        if self.mode in ("create_error", "prepare_error"):
            raise RuntimeError("fake create failure")
        self.created.append(isolation)
        return FakeSandbox(self, self.mode)


@pytest.mark.parametrize(
    ("mode", "failure_class"),
    [
        ("ok", None),
        ("create_error", "gateway_error"),
        ("provider_error", "gateway_error"),
        ("source_mismatch", "source_mismatch"),
        ("build_failure", "build_failure"),
        ("crash", "crash"),
        ("timeout", "timeout"),
        ("too_large", "output_too_large"),
        ("malformed", "malformed_output"),
        ("wrong_seed", "malformed_output"),
        ("invalid", "invalid_candidate"),
        ("score_mismatch", "score_mismatch"),
        ("terminate_error", None),
    ],
)
def test_every_sandbox_outcome_is_classified_and_terminated(
    mode: str, failure_class: str | None
) -> None:
    gateway = FakeGateway(mode)
    record = pc.run_sandbox_trial(gateway, b"int main(void){return 0;}\n", 5, 10)
    assert record["failure_class"] == failure_class
    assert (record["score"] == 2) == (failure_class is None)
    assert record["cost_usd"] is None and record["cost_status"].startswith("unknown")
    created = mode != "create_error"
    assert len(gateway.terminated) == int(created)  # exactly once, on every path
    assert record["termination"]["attempted"] is created
    assert record["termination"]["ok"] is (None if not created else mode != "terminate_error")
    assert record["isolation_verified"] is (
        mode not in ("create_error", "provider_error", "timeout", "terminate_error")
    )
    if created:
        assert gateway.created == [pc.ISOLATION]
        assert gateway.created[0]["runtime"] == "vm" and gateway.created[0]["block_network"]
        assert gateway.created[0]["secrets"] == [] and gateway.created[0]["mounts"] == []


@pytest.mark.parametrize("mode", ["network_open", "secret_env", "env_truncated", "bad_probe"])
def test_isolation_probe_defects_are_reported_not_trusted(mode: str) -> None:
    record = pc.run_sandbox_trial(FakeGateway(mode), b"source", 5, 10)
    assert record["failure_class"] is None and record["isolation_verified"] is False


def test_oracle_disagreement_from_a_sandbox_is_preserved_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        perpendicular_bisector_oracle,
        "verify",
        lambda points, grid_size: perpendicular_bisector_oracle.BisectorResult(
            True, len(points), "stub that accepts everything"
        ),
    )
    record = pc.run_sandbox_trial(FakeGateway("invalid"), b"source", 5, 10)
    assert record["failure_class"] == "oracle_disagreement" and record["score"] is None
    assert record["points"] == [[0, 0], [1, 0], [2, 0]]


class LocalProcessSandbox(FakeSandbox):
    """Really compiles and runs the frozen solver, in a scratch directory."""

    def __init__(self, gateway: FakeGateway, directory: Path) -> None:
        super().__init__(gateway, "replay")
        self.directory = directory

    def write_file(self, name: str, data: bytes) -> None:
        (self.directory / name).write_bytes(data)

    def exec(self, command: list[str], timeout_seconds: int, max_stdout_bytes: int) -> ExecResult:
        if command == pc.PROBE_COMMAND:
            return ExecResult(0, PROBE_OK, "")
        done = subprocess.run(
            command, cwd=self.directory, capture_output=True, timeout=timeout_seconds, check=False
        )
        stdout = done.stdout[: max_stdout_bytes + 1]
        return ExecResult(done.returncode, stdout, done.stderr.decode())


class LocalProcessGateway(FakeGateway):
    def create(self, isolation: dict[str, Any]) -> FakeSandbox:
        self.created.append(isolation)
        return LocalProcessSandbox(self, Path(tempfile.mkdtemp(prefix="p2-replay-")))


def run(tmp_path: Path, gateway: FakeGateway, seeds: list[int]) -> tuple[dict[str, Any], Path]:
    return pc.run_comparison(
        gateway=gateway, seeds=seeds, iters=2000, workers=2, artifact_dir=tmp_path / "runs",
        linear_issue="TRI-19", experiment_id="02", backend="fake",
    )


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_deterministic_replay_agrees_across_arms_and_writes_linked_artifacts(
    tmp_path: Path,
) -> None:
    gateway = LocalProcessGateway()
    summary, path = run(tmp_path, gateway, [900, 901])
    assert path.exists() and summary["gate_status"] == "passed"
    assert summary["agreement"] == {
        "seeds": 2, "candidate_hash_agree": 2, "candidate_hash_mismatch": 0,
        "not_comparable": 0, "stdout_byte_identical": 2,
    }
    assert summary["oracle_disagreements"] == 0 and summary["false_accepts"] == 0
    assert summary["cost_usd"] is None and summary["cost_status"].startswith("unknown")
    assert summary["config"]["matches_preregistration"] is False
    assert summary["isolation"]["sandboxes_terminated"] == len(gateway.terminated) == 2
    names = sorted(p.name.split(".", 1)[1] for p in (tmp_path / "runs").iterdir())
    assert names == [
        "fake-0900.json", "fake-0901.json", "fake.json", "json",
        "local-0900.json", "local-0901.json", "local.json",
    ]
    for pair in summary["pairs"]:
        local = json.loads(Path(pair["local"]["artifact"]).read_text(encoding="utf-8"))
        remote = json.loads(Path(pair["fake"]["artifact"]).read_text(encoding="utf-8"))
        assert local["points"] == remote["points"] and local["cost_usd"] == 0.0
        assert remote["source_readback_sha256"] == remote["solver_build"]["source_sha256"]
        assert remote["isolation_requested"] == pc.ISOLATION and remote["cost_usd"] is None
    second, _ = run(tmp_path, LocalProcessGateway(), [900, 901])  # replay: new immutable run
    assert [p["local"]["candidate_sha256"] for p in second["pairs"]] == [
        p["fake"]["candidate_sha256"] for p in summary["pairs"]
    ]


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
@pytest.mark.parametrize("mode", ["prepare_error", "crash", "network_open"])
def test_partial_artifacts_survive_sandbox_failures(tmp_path: Path, mode: str) -> None:
    summary, path = run(tmp_path, FakeGateway(mode), [900, 901])
    assert len(list((tmp_path / "runs").glob("*.json"))) == 7 and path.exists()
    assert summary["failure_counts"]["local"] == {}
    expected = {
        "prepare_error": ("infrastructure_failure", {"gateway_error": 2}),
        "crash": ("infrastructure_failure", {"crash": 2}),
        "network_open": ("isolation_unverified", {}),
    }[mode]
    assert (summary["gate_status"], summary["failure_counts"]["fake"]) == expected
    assert summary["agreement"]["candidate_hash_agree"] == 0


def test_reserved_seeds_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reserved"):
        run(tmp_path, FakeGateway(), [63, 64])
    assert not (tmp_path / "runs").exists()


def test_empty_seed_list_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one seed"):
        run(tmp_path, FakeGateway(), [])
    assert not (tmp_path / "runs").exists()


def test_cli_refuses_non_preregistered_p2_before_modal_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = False

    def gateway() -> None:
        nonlocal created
        created = True

    monkeypatch.setattr(cli, "ModalSandboxGateway", gateway)
    monkeypatch.setattr(
        "sys.argv",
        ["evohive", "p2-compare", "--seeds", "1300", "--iters", "10", "--workers", "1"],
    )
    assert cli.main() == 2
    assert created is False
