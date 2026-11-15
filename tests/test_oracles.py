import ast
import hashlib
import itertools
import json
import math
import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tripathy_experiment import no_isosceles
from tripathy_experiment import perpendicular_bisector_oracle as bisector

Point = tuple[int, int]
Verdict = Callable[[tuple[Point, ...], int], bool]

BENCHMARK = Path("benchmarks/no_isosceles_n32.json")
UPSTREAM = Path("benchmarks/upstream")
FAILURES = Path("artifacts/failures")


def distance_valid(points: tuple[Point, ...], grid_size: int) -> bool:
    return no_isosceles.verify(points, grid_size).valid


def bisector_valid(points: tuple[Point, ...], grid_size: int) -> bool:
    return bisector.verify(points, grid_size).valid


def load_upstream_verifier() -> Callable[[list[Point]], bool]:
    """Execute the pinned, verbatim upstream verifier after checking its hash."""
    provenance = json.loads((UPSTREAM / "PROVENANCE.json").read_text(encoding="utf-8"))
    source = (UPSTREAM / "verify_construction.py.txt").read_bytes()
    assert hashlib.sha256(source).hexdigest() == provenance["vendored_verifier"]["sha256"]
    namespace: dict[str, object] = {"itertools": itertools, "sqrt": math.sqrt}
    exec(compile(source, "upstream_verify_construction", "exec"), namespace)
    return namespace["verify_construction"]  # type: ignore[return-value]


def public_points() -> tuple[Point, ...]:
    payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    return tuple((int(x), int(y)) for x, y in payload["points"])


def corpus(count: int = 2400) -> Iterator[tuple[int, tuple[Point, ...]]]:
    """Deterministic random point sets on grids of size 1..8."""
    rng = random.Random(59)
    for _ in range(count):
        grid_size = rng.randint(1, 8)
        cells = [(x, y) for x in range(grid_size) for y in range(grid_size)]
        yield grid_size, tuple(rng.sample(cells, rng.randint(0, min(len(cells), 9))))


def minimize_disagreement(
    points: tuple[Point, ...], grid_size: int, left: Verdict, right: Verdict
) -> tuple[Point, ...]:
    """Greedily drop points while the two verdicts still differ."""
    current = list(points)
    shrunk = True
    while shrunk:
        shrunk = False
        for index in range(len(current)):
            smaller = tuple(current[:index] + current[index + 1 :])
            if left(smaller, grid_size) != right(smaller, grid_size):
                current = list(smaller)
                shrunk = True
                break
    return tuple(current)


def write_disagreement_fixture(
    directory: Path, points: tuple[Point, ...], grid_size: int, left: Verdict, right: Verdict
) -> Path:
    """Persist a minimized, replayable fixture and return its path."""
    minimal = minimize_disagreement(points, grid_size, left, right)
    fixture = {
        "kind": "oracle-disagreement",
        "grid_size": grid_size,
        "points": [list(point) for point in minimal],
        "original_points": [list(point) for point in points],
        "left_valid": left(minimal, grid_size),
        "right_valid": right(minimal, grid_size),
        "replay": "call both oracle verify() functions on points with grid_size",
    }
    digest = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode("utf-8")).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"oracle-disagreement-{digest[:16]}.json"
    path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def assert_real_witness(points: tuple[Point, ...], witness: object) -> None:
    assert isinstance(witness, tuple) and len(witness) == 3
    end_a, apex, end_b = witness
    assert len({end_a, apex, end_b}) == 3 and {end_a, apex, end_b} <= set(points)
    assert math.dist(apex, end_a) ** 2 == pytest.approx(math.dist(apex, end_b) ** 2)
    assert (apex[0] - end_a[0]) ** 2 + (apex[1] - end_a[1]) ** 2 == (
        (apex[0] - end_b[0]) ** 2 + (apex[1] - end_b[1]) ** 2
    )


def test_bisector_oracle_does_not_import_the_trusted_oracle() -> None:
    tree = ast.parse(Path(bisector.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {str(node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"__future__", "dataclasses"}


def test_oracles_agree_with_each_other_and_upstream_on_random_corpus() -> None:
    upstream = load_upstream_verifier()
    valid_count = invalid_count = 0
    for grid_size, points in corpus():
        left = no_isosceles.verify(points, grid_size)
        right = bisector.verify(points, grid_size)
        if left.valid != right.valid:
            path = write_disagreement_fixture(
                FAILURES, points, grid_size, distance_valid, bisector_valid
            )
            pytest.fail(f"oracle disagreement; minimized fixture written to {path}")
        assert upstream(list(points)) == left.valid, (grid_size, points)
        assert left.score == right.score == len(points)
        if left.valid:
            valid_count += 1
            assert left.witness is None and right.witness is None
        else:
            invalid_count += 1
            assert_real_witness(points, left.witness)
            assert_real_witness(points, right.witness)
    assert valid_count + invalid_count >= 2000
    assert valid_count >= 300 and invalid_count >= 300


@pytest.mark.parametrize(
    ("label", "points", "grid_size", "expected"),
    [
        ("empty", (), 3, True),
        ("single", ((0, 0),), 1, True),
        ("pair", ((0, 0), (1, 1)), 2, True),
        ("scalene triple", ((0, 0), (1, 0), (3, 1)), 4, True),
        ("duplicate", ((0, 0), (0, 0)), 3, False),
        ("duplicate among three", ((0, 0), (2, 1), (0, 0)), 3, False),
        ("x out of bounds", ((0, 0), (3, 0)), 3, False),
        ("y out of bounds", ((0, 0), (0, 3)), 3, False),
        ("negative coordinate", ((0, 0), (-1, 0)), 3, False),
        ("vertical base", ((0, 0), (0, 2), (1, 1)), 3, False),
        ("horizontal base", ((0, 0), (2, 0), (1, 2)), 3, False),
        ("degenerate collinear axis", ((0, 0), (1, 0), (2, 0)), 3, False),
        ("degenerate collinear diagonal", ((0, 0), (1, 1), (2, 2)), 3, False),
        ("nondegenerate isosceles", ((0, 0), (1, 2), (2, 1)), 3, False),
    ],
)
def test_both_oracles_on_edge_cases(
    label: str, points: tuple[Point, ...], grid_size: int, expected: bool
) -> None:
    left = no_isosceles.verify(points, grid_size)
    right = bisector.verify(points, grid_size)
    assert left.valid == right.valid == expected, label
    in_grid = all(0 <= x < grid_size and 0 <= y < grid_size for x, y in points)
    if not expected and in_grid and len(set(points)) == len(points):
        assert_real_witness(points, left.witness)
        assert_real_witness(points, right.witness)


def test_public_58_is_accepted_by_both_oracles_and_upstream() -> None:
    points = public_points()
    assert len(points) == 58
    assert no_isosceles.verify(points, 32).valid
    assert bisector.verify(points, 32).valid
    assert load_upstream_verifier()(list(points)) is True


def test_every_single_point_augmentation_of_public_58_is_rejected() -> None:
    points = public_points()
    unused = [(x, y) for x in range(32) for y in range(32) if (x, y) not in set(points)]
    assert len(unused) == 966
    for cell in unused:
        assert not no_isosceles.verify((*points, cell), 32).valid, cell
        # bisector.verify(points + (cell,)) reduces to this step once the base is valid
        assert bisector.addition_witness(points, cell) is not None, cell
    upstream = load_upstream_verifier()
    for cell in random.Random(58).sample(unused, 8):
        rejected = bisector.verify((*points, cell), 32)
        assert not rejected.valid
        assert_real_witness((*points, cell), rejected.witness)
        assert upstream([*points, cell]) is False


def test_disagreement_is_minimized_to_a_reproducible_fixture(tmp_path: Path) -> None:
    def ignores_flat_triples(points: tuple[Point, ...], grid_size: int) -> bool:
        del grid_size
        return not any(
            (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 == (a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2
            and (b[0] - a[0]) * (c[1] - a[1]) != (b[1] - a[1]) * (c[0] - a[0])
            for a in points
            for b, c in itertools.combinations([p for p in points if p != a], 2)
        )

    noisy = ((0, 0), (5, 3), (1, 0), (7, 6), (2, 0), (4, 7))
    path = write_disagreement_fixture(tmp_path, noisy, 8, bisector_valid, ignores_flat_triples)
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(map(tuple, fixture["points"])) == [(0, 0), (1, 0), (2, 0)]
    assert fixture["left_valid"] is False and fixture["right_valid"] is True
