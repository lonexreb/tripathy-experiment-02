from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

Point = tuple[int, int]


@dataclass(frozen=True)
class Candidate:
    points: tuple[Point, ...]
    agent_id: str
    strategy: str
    parent_id: str | None = None
    inherited_from_agent: str | None = None
    source_urls: tuple[str, ...] = ()

    @property
    def candidate_id(self) -> str:
        payload = json.dumps(self.points, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @property
    def score(self) -> int:
        return len(self.points)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["candidate_id"] = self.candidate_id
        payload["score"] = self.score
        return payload


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    score: int
    reason: str
    witness: tuple[Point, Point, Point] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def verify(points: tuple[Point, ...], grid_size: int) -> VerificationResult:
    """Verify the no-isosceles constraint with exact integer squared distances."""
    if len(set(points)) != len(points):
        return VerificationResult(False, len(points), "duplicate point")
    if any(x < 0 or y < 0 or x >= grid_size or y >= grid_size for x, y in points):
        return VerificationResult(False, len(points), "point outside grid")

    for pivot in points:
        seen: dict[int, Point] = {}
        px, py = pivot
        for other in points:
            if other == pivot:
                continue
            ox, oy = other
            distance = (px - ox) ** 2 + (py - oy) ** 2
            if distance in seen:
                return VerificationResult(
                    False,
                    len(points),
                    "equal distances from one pivot",
                    (seen[distance], pivot, other),
                )
            seen[distance] = other
    return VerificationResult(True, len(points), "exact verifier passed")


def greedy_fill(
    points: tuple[Point, ...], grid_size: int, rng: random.Random
) -> tuple[Point, ...]:
    current = list(dict.fromkeys(points))
    available = [
        (x, y)
        for x in range(grid_size)
        for y in range(grid_size)
        if (x, y) not in current
    ]
    rng.shuffle(available)
    for point in available:
        candidate = tuple(sorted((*current, point)))
        if verify(candidate, grid_size).valid:
            current.append(point)
    return tuple(sorted(current))


def greedy_seed(grid_size: int, seed: int) -> tuple[Point, ...]:
    return greedy_fill((), grid_size, random.Random(seed))


def mutate(
    parent: tuple[Point, ...], strategy: str, grid_size: int, rng: random.Random
) -> tuple[Point, ...]:
    if strategy == "greedy_add":
        return greedy_fill(parent, grid_size, rng)

    ruin_count = 1 if strategy == "ruin_one" else min(3, max(1, len(parent) // 8))
    survivors = list(parent)
    if survivors:
        removed_indices = rng.sample(
            range(len(survivors)), k=min(ruin_count, len(survivors))
        )
        for index in sorted(removed_indices, reverse=True):
            survivors.pop(index)

    if strategy == "symmetric_ruin":
        center = grid_size - 1
        pairs = [
            ((x, y), (center - x, center - y))
            for x in range(grid_size)
            for y in range(grid_size)
            if (x, y) <= (center - x, center - y)
        ]
        rng.shuffle(pairs)
        current = tuple(sorted(survivors))
        for left, right in pairs:
            additions = tuple(point for point in (left, right) if point not in current)
            proposed = tuple(sorted((*current, *additions)))
            if additions and verify(proposed, grid_size).valid:
                current = proposed
        return greedy_fill(current, grid_size, rng)

    return greedy_fill(tuple(sorted(survivors)), grid_size, rng)


def load_public_baseline(path: Path) -> Candidate:
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = tuple((int(point[0]), int(point[1])) for point in payload["points"])
    return Candidate(points=points, agent_id="public-baseline", strategy="certificate")
