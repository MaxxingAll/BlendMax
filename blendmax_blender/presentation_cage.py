"""Pure measurement-cage geometry shared by the Blender presentation tool.

This module intentionally has no Blender dependency. It turns axis-aligned
world-space presentation bounds into a deterministic wireframe grid, keeping
the geometry contract independently testable from Blender data APIs.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .placement import Bounds

Vector3 = Tuple[float, float, float]
Edge = Tuple[int, int]


def _axis_values(lower: float, upper: float, divisions: int) -> Iterable[float]:
    step = (upper - lower) / float(divisions)
    return (
        upper if index == divisions else lower + step * index
        for index in range(divisions + 1)
    )


def cage_geometry(bounds: Bounds, divisions: Sequence[int] = (1, 1, 1)) -> Tuple[Tuple[Vector3, ...], Tuple[Edge, ...]]:
    """Return unique vertices/edges for a six-face measurement grid."""
    if len(divisions) != 3:
        raise ValueError("Measurement cage divisions must contain X, Y and Z.")
    counts = tuple(int(value) for value in divisions)
    if any(value < 1 for value in counts):
        raise ValueError("Measurement cage divisions must be at least 1.")

    minimum, maximum = bounds
    x0, y0, z0 = (float(value) for value in minimum)
    x1, y1, z1 = (float(value) for value in maximum)
    vertices: List[Vector3] = []
    vertex_ids = {}
    edges: List[Edge] = []
    edge_ids = set()

    def vertex(point: Vector3) -> int:
        key = tuple(float(value) for value in point)
        index = vertex_ids.get(key)
        if index is None:
            index = len(vertices)
            vertex_ids[key] = index
            vertices.append(key)
        return index

    def edge(start: Vector3, end: Vector3) -> None:
        start_id = vertex(start)
        end_id = vertex(end)
        if start_id == end_id:
            return
        item = tuple(sorted((start_id, end_id)))
        if item in edge_ids:
            return
        edge_ids.add(item)
        edges.append(item)

    def face_grid(fixed_axis, fixed_value, axis_a, a0, a1, a_divisions, axis_b, b0, b1, b_divisions):
        point = [0.0, 0.0, 0.0]
        point[fixed_axis] = fixed_value
        for b in _axis_values(b0, b1, b_divisions):
            point[axis_b] = b
            point[axis_a] = a0
            start = tuple(point)
            point[axis_a] = a1
            edge(start, tuple(point))
        for a in _axis_values(a0, a1, a_divisions):
            point[axis_a] = a
            point[axis_b] = b0
            start = tuple(point)
            point[axis_b] = b1
            edge(start, tuple(point))

    for z in (z0, z1):
        face_grid(2, z, 0, x0, x1, counts[0], 1, y0, y1, counts[1])
    for y in (y0, y1):
        face_grid(1, y, 0, x0, x1, counts[0], 2, z0, z1, counts[2])
    for x in (x0, x1):
        face_grid(0, x, 1, y0, y1, counts[1], 2, z0, z1, counts[2])
    return tuple(vertices), tuple(edges)
