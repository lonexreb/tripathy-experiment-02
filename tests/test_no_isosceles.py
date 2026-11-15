import json
from pathlib import Path

from tripathy_experiment.no_isosceles import load_public_baseline, verify


def test_public_58_point_certificate_passes_exact_verifier() -> None:
    path = Path("benchmarks/no_isosceles_n32.json")
    candidate = load_public_baseline(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    result = verify(candidate.points, grid_size=32)

    assert result.valid
    assert result.score == payload["score"] == 58


def test_verifier_rejects_an_isosceles_triple() -> None:
    result = verify(((0, 0), (1, 0), (2, 0)), grid_size=3)

    assert not result.valid
    assert result.witness is not None
