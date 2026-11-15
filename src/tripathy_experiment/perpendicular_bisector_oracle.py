"""Second, structurally independent exact oracle for the no-isosceles constraint.

The trusted oracle in ``no_isosceles.py`` hashes squared distances per apex. This
one never compares two distances: for every unordered base pair ``{a, b}`` it
tests whether a third point lies on the perpendicular bisector of ``ab`` using
the linear identity ``2 c.(b - a) == |b|^2 - |a|^2``. It deliberately imports
nothing from ``no_isosceles.py`` so a shared bug cannot make the two agree.

Degenerate collinear triples (``c`` the midpoint of ``ab``) are rejected, which
matches the pinned upstream ``verify_construction`` (see ``benchmarks/upstream``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

Point = tuple[int, int]
Witness = tuple[Point, Point, Point]  # (base end, apex, base end)


@dataclass(frozen=True)
class BisectorResult:
    valid: bool
    score: int
    reason: str
    witness: Witness | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _on_bisector(a: Point, b: Point, c: Point) -> bool:
    return 2 * (c[0] * (b[0] - a[0]) + c[1] * (b[1] - a[1])) == (
        b[0] * b[0] + b[1] * b[1] - a[0] * a[0] - a[1] * a[1]
    )


def addition_witness(existing: tuple[Point, ...], new: Point) -> Witness | None:
    """Return an isosceles triple that contains ``new``, or None.

    ``existing`` must not contain ``new``. Every triple containing ``new`` is
    covered: ``new`` is either a base end (first loop) or the apex (second).
    """
    for index, a in enumerate(existing):
        for c in existing:
            if c != a and _on_bisector(new, a, c):
                return (new, c, a)
        for b in existing[index + 1 :]:
            if _on_bisector(a, b, new):
                return (a, new, b)
    return None


def verify(points: tuple[Point, ...], grid_size: int) -> BisectorResult:
    """Accept only distinct in-grid points with no apex on any base bisector."""
    score = len(points)
    seen: set[Point] = set()
    for x, y in points:
        if not (0 <= x < grid_size and 0 <= y < grid_size):
            return BisectorResult(False, score, "point outside grid")
        if (x, y) in seen:
            return BisectorResult(False, score, "duplicate point")
        seen.add((x, y))
    for index, point in enumerate(points):
        witness = addition_witness(points[:index], point)
        if witness is not None:
            return BisectorResult(False, score, "apex on a base bisector", witness)
    return BisectorResult(True, score, "bisector oracle passed")
