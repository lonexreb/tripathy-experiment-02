"""Judge report reconstruction and staleness tests."""

import json
from pathlib import Path

import pytest

from tripathy_experiment.judge_report import (
    EvidenceError,
    build_report,
    render_markdown,
    write_report,
)


def test_report_reconstructs_canonical_evidence_and_reverifies_candidates() -> None:
    report = build_report()
    assert report["verdict"] == {
        "best_dual_verified_score": 58,
        "public_score_reproduced_from_scratch": True,
        "verified_59_found": False,
        "modal_candidate_parity": True,
        "modal_speedup_demonstrated": False,
    }
    assert report["p0"]["target_reached"] == 10
    assert report["p1"]["total_trials"] == 24
    assert report["p1"]["minimum_working_violations"] == 2
    assert report["p2"]["candidate_hash_agree"] == 4
    assert report["p2"]["sandboxes_terminated"] == 4
    assert report["integrity"]["fresh_dual_verifications"] == 96
    assert report["integrity"]["source_artifact_count"] == 103
    assert len(report["integrity"]["evidence_set_sha256"]) == 64
    assert len(report["integrity"]["evidence_index_sha256"]) == 64


def test_markdown_states_result_and_claim_boundaries() -> None:
    markdown = render_markdown(build_report())
    assert "10/64 fixed-budget trials" in markdown
    assert "did not find a verified 59-point" in markdown
    assert "Modal timing" in markdown and "Cost is unknown, not zero" in markdown
    assert "Exa and past.dev have no live evidence" in markdown


def test_write_then_check_detects_stale_output(tmp_path: Path) -> None:
    report = build_report()
    json_path, markdown_path = write_report(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["project"] == "EvoHive"
    write_report(report, tmp_path, check=True)
    markdown_path.write_text("stale\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="stale"):
        write_report(report, tmp_path, check=True)


def test_missing_indexed_run_fails_closed(tmp_path: Path) -> None:
    index = json.loads(Path("experiment/evidence-index.json").read_text(encoding="utf-8"))
    index["p0"]["run_id"] = "missing"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(EvidenceError, match="cannot read"):
        build_report(index_path=path)
