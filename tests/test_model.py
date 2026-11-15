import pytest

from tripathy_experiment.model import ExperimentManifest, ValidationError
from tripathy_experiment.no_isosceles import Candidate


def test_placeholder_manifest_is_blocked() -> None:
    manifest = ExperimentManifest.from_dict({"experiment_id": "01", "budget_usd": 0})
    with pytest.raises(ValidationError, match="Start gate incomplete"):
        manifest.validate()


def test_complete_manifest_passes() -> None:
    manifest = ExperimentManifest.from_dict(
        {
            "experiment_id": "01",
            "status": "planning",
            "question": "Can the candidate beat the baseline?",
            "hypothesis": "The candidate improves the primary metric.",
            "primary_metric": "score",
            "baseline": "fixed baseline",
            "budget_usd": 10,
            "stop_condition": "Stop after ten runs.",
        }
    )
    manifest.validate()


def test_candidate_identity_depends_only_on_construction() -> None:
    left = Candidate(points=((0, 0), (1, 2)), agent_id="a", strategy="first")
    right = Candidate(points=((0, 0), (1, 2)), agent_id="b", strategy="second")
    assert left.candidate_id == right.candidate_id
