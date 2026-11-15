"""Derive a concise judge report from immutable experiment artifacts.

The evidence index chooses canonical runs but contains no result metrics. Every
number in the report is reconstructed from parent/child artifacts, and every
accepted child is freshly checked by both local oracles before output is written.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .no_isosceles import verify as verify_distance
from .perpendicular_bisector_oracle import verify as verify_bisector

DEFAULT_INDEX = Path("experiment/evidence-index.json")
DEFAULT_ARTIFACT_DIR = Path("artifacts/runs")
DEFAULT_OUTPUT_DIR = Path("artifacts/judge")


class EvidenceError(ValueError):
    """The selected evidence is absent, malformed or internally inconsistent."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} is not a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EvidenceLoader:
    """Load only paths inside the configured artifact directory and hash each one."""

    def __init__(self, root: Path, artifact_dir: Path) -> None:
        self.root = root.resolve()
        self.artifact_dir = (self.root / artifact_dir).resolve()
        self.hashes: dict[str, str] = {}
        self.reverified_candidates = 0

    def _resolve(self, reference: str | Path) -> Path:
        path = Path(reference)
        resolved = (path if path.is_absolute() else self.root / path).resolve()
        if not resolved.is_relative_to(self.artifact_dir):
            raise EvidenceError(f"artifact reference escapes evidence directory: {reference}")
        return resolved

    def read(self, reference: str | Path) -> dict[str, Any]:
        path = self._resolve(reference)
        payload = _read_object(path)
        relative = str(path.relative_to(self.root))
        self.hashes[relative] = _sha256(path)
        return payload

    def parent(self, run_id: str, kind: str) -> dict[str, Any]:
        payload = self.read(self.artifact_dir / f"{run_id}.json")
        if payload.get("run_id") != run_id or payload.get("kind") != kind:
            raise EvidenceError(f"{run_id} is not a {kind}")
        return payload

    def child(self, reference: str, run_id: str) -> dict[str, Any]:
        payload = self.read(reference)
        if payload.get("run_id") != run_id:
            raise EvidenceError(f"child {reference} does not belong to {run_id}")
        self._reverify(payload, reference)
        return payload

    def _reverify(self, child: dict[str, Any], reference: str) -> None:
        if child.get("failure_class") is not None:
            return
        raw_points = child.get("points")
        if not isinstance(raw_points, list):
            raise EvidenceError(f"accepted child {reference} has no points")
        points: list[tuple[int, int]] = []
        for point in raw_points:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or type(point[0]) is not int
                or type(point[1]) is not int
            ):
                raise EvidenceError(f"accepted child {reference} has malformed points")
            points.append((point[0], point[1]))
        grid_size = int(child.get("config", {}).get("grid_size", 32))
        point_tuple = tuple(points)
        distance = verify_distance(point_tuple, grid_size)
        bisector = verify_bisector(point_tuple, grid_size)
        if not distance.valid or not bisector.valid or child.get("score") != len(points):
            raise EvidenceError(f"accepted child {reference} failed fresh dual verification")
        self.reverified_candidates += 1


def _indexed_run(index: dict[str, Any], key: str) -> tuple[str, str]:
    value = index.get(key)
    if not isinstance(value, dict):
        raise EvidenceError(f"evidence index needs object {key}")
    label, run_id = value.get("label"), value.get("run_id")
    if not isinstance(label, str) or not isinstance(run_id, str):
        raise EvidenceError(f"evidence index {key} needs label and run_id")
    return label, run_id


def _load_children(
    loader: EvidenceLoader, parent: dict[str, Any], run_id: str
) -> list[dict[str, Any]]:
    indexed = parent.get("children")
    if not isinstance(indexed, list) or len(indexed) != parent.get("trials"):
        raise EvidenceError(f"{run_id} child count does not equal trials")
    children = []
    for child in indexed:
        if not isinstance(child, dict) or not isinstance(child.get("artifact"), str):
            raise EvidenceError(f"{run_id} has a malformed child reference")
        children.append(loader.child(child["artifact"], run_id))
    return children


def _p0_report(loader: EvidenceLoader, label: str, run_id: str) -> dict[str, Any]:
    parent = loader.parent(run_id, "baseline-summary")
    children = _load_children(loader, parent, run_id)
    target = int(parent["config"]["target_score"])
    reached = sum(1 for child in children if child.get("score", -1) >= target)
    if reached != parent.get("reach_target_count"):
        raise EvidenceError(f"{run_id} reach-target count disagrees with children")
    score_counts = {
        str(score): count
        for score, count in sorted(Counter(child.get("score") for child in children).items())
    }
    disagreements = sum(
        child.get("failure_class") == "oracle_disagreement" for child in children
    )
    if score_counts != parent.get("score_counts") or disagreements != parent.get(
        "oracle_disagreements"
    ):
        raise EvidenceError(f"{run_id} summary counts disagree with children")
    return {
        "label": label,
        "run_id": run_id,
        "gate_status": parent["gate_status"],
        "trials": len(children),
        "iterations_per_trial": parent["config"]["iters"],
        "best_score": max(int(child["score"]) for child in children),
        "target_score": target,
        "target_reached": reached,
        "target_reached_ci95_exact": parent["reach_target_ci95_exact"],
        "score_counts": score_counts,
        "oracle_disagreements": disagreements,
        "wall_seconds": parent["wall_seconds"],
        "cost_usd": parent["cost_usd"],
    }


def _p1_report(
    loader: EvidenceLoader, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    iterations = []
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise EvidenceError("evidence index p1 entries must be objects")
        label, run_id = entry.get("label"), entry.get("run_id")
        if not isinstance(label, str) or not isinstance(run_id, str):
            raise EvidenceError("evidence index p1 entries need label and run_id")
        parent = loader.parent(run_id, "p1-smoke-summary")
        children = _load_children(loader, parent, run_id)
        minimum = min(int(child["min_working_violations"]) for child in children)
        if minimum != parent.get("min_working_violations"):
            raise EvidenceError(f"{run_id} violation minimum disagrees with children")
        target = int(parent["config"]["target_score"])
        verified_target_count = sum(
            child.get("failure_class") is None and child.get("score", -1) >= target
            for child in children
        )
        disagreements = sum(
            child.get("failure_class") == "oracle_disagreement" for child in children
        )
        counts_disagree = verified_target_count != parent.get("verified_target_count")
        counts_disagree |= disagreements != parent.get("oracle_disagreements")
        if counts_disagree:
            raise EvidenceError(f"{run_id} summary counts disagree with children")
        iterations.append(
            {
                "iteration": number,
                "label": label,
                "run_id": run_id,
                "gate_status": parent["gate_status"],
                "trials": len(children),
                "best_valid_score": max(int(child["score"]) for child in children),
                "verified_59_count": verified_target_count,
                "minimum_working_violations": minimum,
                "oracle_disagreements": disagreements,
                "wall_seconds": parent["wall_seconds"],
                "cost_usd": parent["cost_usd"],
            }
        )
    return {
        "operator_family_status": "stopped after preregistered negative boundary",
        "iterations": iterations,
        "total_trials": sum(int(item["trials"]) for item in iterations),
        "verified_59_count": sum(int(item["verified_59_count"]) for item in iterations),
        "minimum_working_violations": min(
            int(item["minimum_working_violations"]) for item in iterations
        ),
    }


def _p2_report(loader: EvidenceLoader, label: str, run_id: str) -> dict[str, Any]:
    parent = loader.parent(run_id, "p2-comparison")
    arm_artifacts = parent.get("arm_artifacts")
    if not isinstance(arm_artifacts, dict):
        raise EvidenceError(f"{run_id} has no arm artifacts")
    for reference in arm_artifacts.values():
        if not isinstance(reference, str):
            raise EvidenceError(f"{run_id} has a malformed arm artifact")
        arm_summary = loader.read(reference)
        if arm_summary.get("run_id") != run_id or arm_summary.get("kind") != "p2-arm-summary":
            raise EvidenceError(f"{reference} is not a P2 arm summary")
    pairs = parent.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != parent.get("agreement", {}).get("seeds"):
        raise EvidenceError(f"{run_id} pair count is inconsistent")
    loaded: dict[str, list[dict[str, Any]]] = {"local": [], "modal": []}
    for pair in pairs:
        if not isinstance(pair, dict):
            raise EvidenceError(f"{run_id} has a malformed pair")
        for arm_name in ("local", "modal"):
            arm_child = pair.get(arm_name)
            if not isinstance(arm_child, dict) or not isinstance(arm_child.get("artifact"), str):
                raise EvidenceError(f"{run_id} has a malformed {arm_name} child")
            loaded[arm_name].append(loader.child(arm_child["artifact"], run_id))
    agreement = parent["agreement"]
    isolation = parent["isolation"]
    latency = parent["latency"]
    derived_agree = 0
    derived_stdout = 0
    for local, modal in zip(loaded["local"], loaded["modal"], strict=True):
        candidate_hashes = (local.get("candidate_sha256"), modal.get("candidate_sha256"))
        stdout_hashes = (local.get("stdout_sha256"), modal.get("stdout_sha256"))
        if not all(isinstance(value, str) for value in (*candidate_hashes, *stdout_hashes)):
            raise EvidenceError(f"{run_id} accepted pair lacks output hashes")
        derived_agree += candidate_hashes[0] == candidate_hashes[1]
        derived_stdout += stdout_hashes[0] == stdout_hashes[1]
    accepted = sum(
        child.get("failure_class") is None for children in loaded.values() for child in children
    )
    disagreements = sum(
        child.get("failure_class") == "oracle_disagreement"
        for children in loaded.values()
        for child in children
    )
    terminated = sum(child.get("termination", {}).get("ok") is True for child in loaded["modal"])
    created = sum(isinstance(child.get("sandbox_id"), str) for child in loaded["modal"])
    isolation_verified = all(child.get("isolation_verified") is True for child in loaded["modal"])
    failures = {
        arm_name: dict(
            sorted(
                Counter(
                    str(child["failure_class"])
                    for child in children
                    if child.get("failure_class") is not None
                ).items()
            )
        )
        for arm_name, children in loaded.items()
    }
    if (
        derived_agree != agreement.get("candidate_hash_agree")
        or derived_stdout != agreement.get("stdout_byte_identical")
        or accepted != parent.get("accepted_trials")
        or disagreements != parent.get("oracle_disagreements")
        or parent.get("false_accepts") != 0
        or failures != parent.get("failure_counts")
        or created != isolation.get("sandboxes_created")
        or terminated != isolation.get("sandboxes_terminated")
        or isolation_verified != isolation.get("all_trials_verified")
    ):
        raise EvidenceError(f"{run_id} summary counts disagree with children")
    return {
        "label": label,
        "run_id": run_id,
        "gate_status": parent["gate_status"],
        "trials": parent["trials"],
        "accepted_trials": accepted,
        "candidate_hash_agree": derived_agree,
        "candidate_hash_mismatch": len(pairs) - derived_agree,
        "seeds_compared": agreement["seeds"],
        "stdout_byte_identical": derived_stdout,
        "oracle_disagreements": disagreements,
        "false_accepts": 0,
        "failures": failures,
        "sandboxes_created": created,
        "sandboxes_terminated": terminated,
        "all_isolation_probes_verified": isolation_verified,
        "local_parallel_wall_seconds": latency["local_parallel_wall_seconds"],
        "local_serial_equivalent_seconds": latency["local_serial_equivalent_seconds"],
        "modal_wall_seconds": latency["sandbox_wall_seconds"],
        "modal_prepare_seconds": latency["sandbox_prepare_seconds"],
        "modal_faster_than_local_parallel": latency["sandbox_faster_than_local_parallel"],
        "modal_faster_than_local_serial_equivalent": latency[
            "sandbox_faster_than_local_serial"
        ],
        "cost_usd": parent["cost_usd"],
        "cost_status": parent["cost_status"],
    }


def _p3_report(loader: EvidenceLoader, label: str, transition_id: str) -> dict[str, Any]:
    transition_path = loader.artifact_dir / f"{transition_id}.transition.json"
    transition = loader.read(transition_path)
    if (
        transition.get("kind") != "autonomy-transition"
        or transition.get("transition_id") != transition_id
    ):
        raise EvidenceError(f"{transition_path} is not the selected autonomy transition")
    decision_ref = transition.get("decision_artifact")
    action_ref = transition.get("action_artifact")
    if not isinstance(decision_ref, str) or not isinstance(action_ref, str):
        raise EvidenceError(f"{transition_id} lacks decision or action references")
    decision = loader.read(decision_ref)
    action = loader.read(action_ref)
    if (
        decision.get("kind") != "causal-decision"
        or decision.get("decision_id") != transition_id
        or action.get("kind") != "baseline-summary"
        or action.get("run_id") != transition.get("action_run_id")
    ):
        raise EvidenceError(f"{transition_id} has inconsistent linked artifacts")
    if (
        _sha256(loader._resolve(decision_ref)) != transition.get("decision_sha256")
        or _sha256(loader._resolve(action_ref)) != transition.get("action_sha256")
    ):
        raise EvidenceError(f"{transition_id} linked artifact hash mismatch")
    action_run_id = str(action["run_id"])
    children = _load_children(loader, action, action_run_id)
    scores = [int(child["score"]) for child in children if child.get("failure_class") is None]
    score_counts = {
        str(score): count for score, count in sorted(Counter(scores).items())
    }
    disagreements = sum(
        child.get("failure_class") == "oracle_disagreement" for child in children
    )
    incumbent_hash = _sha256(loader.root / "solver/solver.c")
    rollback = transition.get("rollback", {})
    causal_gate = all(
        (
            transition.get("gate_status") == "passed",
            transition.get("decision_precedes_action") is True,
            transition.get("action_matches_decision_spec") is True,
            decision.get("selected_action") == transition.get("selected_action"),
            decision.get("reason_code") == transition.get("reason_code"),
            decision.get("experiment_spec", {}).get("matches_preregistration") is True,
            action.get("score_counts") == score_counts,
            action.get("oracle_disagreements") == disagreements,
            max(scores) == transition.get("best_score"),
            rollback.get("incumbent_unchanged") is True,
            rollback.get("sha256_before") == rollback.get("sha256_after") == incumbent_hash,
        )
    )
    if not causal_gate:
        raise EvidenceError(f"{transition_id} failed causal transition reconstruction")
    return {
        "label": label,
        "transition_id": transition_id,
        "decision_artifact": decision_ref,
        "action_run_id": action_run_id,
        "selected_action": transition["selected_action"],
        "reason_code": transition["reason_code"],
        "decision_precedes_action": True,
        "action_matches_decision_spec": True,
        "trials": len(children),
        "score_counts": score_counts,
        "best_score": max(scores),
        "oracle_disagreements": disagreements,
        "promotion_status": transition["promotion"]["status"],
        "incumbent_unchanged": True,
        "negative_evidence_retained": transition["rollback"]["negative_evidence_retained"],
        "cost_usd": transition["cost_usd"],
        "record_claim": transition["record_claim"],
    }


def build_report(
    root: Path = Path("."),
    index_path: Path = DEFAULT_INDEX,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    """Build and validate the machine-readable judge report."""
    resolved_index = (root / index_path).resolve()
    index = _read_object(resolved_index)
    if index.get("schema_version") != 1:
        raise EvidenceError("unsupported evidence-index schema")
    p0_label, p0_run = _indexed_run(index, "p0")
    p2_label, p2_run = _indexed_run(index, "p2")
    p3_value = index.get("p3")
    if not isinstance(p3_value, dict):
        raise EvidenceError("evidence index needs object p3")
    p3_label, p3_transition = p3_value.get("label"), p3_value.get("transition_id")
    if not isinstance(p3_label, str) or not isinstance(p3_transition, str):
        raise EvidenceError("evidence index p3 needs label and transition_id")
    p1_entries = index.get("p1")
    if not isinstance(p1_entries, list) or not p1_entries:
        raise EvidenceError("evidence index needs non-empty p1")
    sponsor_status = index.get("sponsor_status")
    if not isinstance(sponsor_status, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in sponsor_status.items()
    ):
        raise EvidenceError("evidence index needs sponsor_status")

    loader = EvidenceLoader(root, artifact_dir)
    p0 = _p0_report(loader, p0_label, p0_run)
    p1 = _p1_report(loader, p1_entries)
    p2 = _p2_report(loader, p2_label, p2_run)
    p3 = _p3_report(loader, p3_label, p3_transition)
    source_hashes = [
        {"path": path, "sha256": digest} for path, digest in sorted(loader.hashes.items())
    ]
    evidence_set_sha256 = hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "project": index.get("project", "EvoHive"),
        "verdict": {
            "best_dual_verified_score": p0["best_score"],
            "public_score_reproduced_from_scratch": p0["target_reached"] > 0,
            "verified_59_found": p1["verified_59_count"] > 0,
            "modal_candidate_parity": p2["candidate_hash_mismatch"] == 0,
            "modal_speedup_demonstrated": p2["modal_faster_than_local_parallel"],
            "causal_autonomy_demonstrated": (
                p3["decision_precedes_action"]
                and p3["action_matches_decision_spec"]
                and p3["incumbent_unchanged"]
            ),
        },
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "sponsor_status": sponsor_status,
        "claim_boundaries": [
            "The 58-point result is a from-scratch reproduction, not a discovery.",
            "No verified 59-point construction exists in this evidence set.",
            "The Modal run demonstrates isolated parity, not speedup or known cost.",
            "The autonomy canary demonstrates a causal transition and rollback, "
            "not a better solver.",
            "Exa and past.dev have adapters and fixture tests but no live evidence.",
        ],
        "integrity": {
            "fresh_dual_verifications": loader.reverified_candidates,
            "source_artifact_count": len(source_hashes),
            "evidence_index_sha256": _sha256(resolved_index),
            "evidence_set_sha256": evidence_set_sha256,
            "source_artifacts": source_hashes,
        },
    }


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    p0, p1, p2, p3 = report["p0"], report["p1"], report["p2"], report["p3"]
    lines = [
        "# EvoHive: Judge Evidence Report",
        "",
        "## Verdict",
        "",
        f"EvoHive reproduced the public {p0['target_score']}-point construction from scratch in "
        f"{p0['target_reached']}/{p0['trials']} fixed-budget trials. It did not find a verified "
        "59-point construction. Modal reproduced four same-seed local candidates exactly, but "
        "was slower at this budget. A persisted P3 decision causally selected and rolled back a "
        "structurally different canary; Exa and past.dev have no live evidence.",
        "",
        "## Evidence",
        "",
        "| Phase | Result | Safety / interpretation |",
        "|---|---|---|",
        f"| P0 `{p0['run_id'][:8]}` | {p0['target_reached']}/{p0['trials']} reached "
        f"{p0['target_score']}; best {p0['best_score']}; {p0['wall_seconds']:.2f} s | "
        f"{p0['oracle_disagreements']} oracle disagreements; cost ${p0['cost_usd']:.2f} |",
    ]
    for item in p1["iterations"]:
        lines.append(
            f"| P1.{item['iteration']} `{item['run_id'][:8]}` | {item['label']}: "
            f"0 verified 59s; minimum {item['minimum_working_violations']} conflicts | "
            f"gate {item['gate_status']}; operator family stopped |"
        )
    lines.extend(
        [
            f"| P2 `{p2['run_id'][:8]}` | {p2['candidate_hash_agree']}/"
            f"{p2['seeds_compared']} candidate hashes and {p2['stdout_byte_identical']}/"
            f"{p2['seeds_compared']} stdout streams match | "
            f"{p2['sandboxes_terminated']}/{p2['sandboxes_created']} terminated; "
            f"{p2['oracle_disagreements']} oracle disagreements |",
            f"| P3 `{p3['transition_id'][:8]}` | selected `{p3['selected_action']}` from P1/P2 "
            f"evidence; best {p3['best_score']} | decision preceded action; "
            f"{p3['promotion_status']}; incumbent unchanged |",
            "",
            "## Modal timing",
            "",
            f"Local parallel: **{p2['local_parallel_wall_seconds']:.2f} s**. Local "
            f"serial-equivalent: **{p2['local_serial_equivalent_seconds']:.2f} s**. Modal: "
            f"**{p2['modal_wall_seconds']:.2f} s** plus "
            f"**{p2['modal_prepare_seconds']:.2f} s** prepare. Cost is unknown, not zero.",
            "",
            "## Claim boundaries",
            "",
        ]
    )
    lines.extend(f"- {claim}" for claim in report["claim_boundaries"])
    integrity = report["integrity"]
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"The generator freshly dual-verified **{integrity['fresh_dual_verifications']}** "
            f"accepted candidates and hashed **{integrity['source_artifact_count']}** source "
            f"artifacts. Evidence-set SHA-256: `{integrity['evidence_set_sha256']}`.",
            "",
            "Rebuild: `python -m tripathy_experiment.cli judge-report`",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    report: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR, *, check: bool = False
) -> tuple[Path, Path]:
    """Write the two report views, or prove committed views are current."""
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        output_dir / "judge-report.json": render_json(report),
        output_dir / "judge-report.md": render_markdown(report),
    }
    for path, expected in outputs.items():
        if check:
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError as error:
                raise EvidenceError(f"missing generated report {path}") from error
            if actual != expected:
                raise EvidenceError(f"generated report is stale: {path}")
        else:
            path.write_text(expected, encoding="utf-8")
    return output_dir / "judge-report.json", output_dir / "judge-report.md"
