"""Pure measurement-cage geometry shared by the Blender presentation tool.

This module intentionally has no Blender dependency. It turns axis-aligned
world-space presentation bounds into a deterministic wireframe grid, keeping
the geometry contract independently testable from Blender data APIs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .presentation import PresentationBounds
from .placement import Bounds

Vector3 = Tuple[float, float, float]
Edge = Tuple[int, int]

# Blender stores mesh and transform data in single precision, so world-space
# bounds can carry float32-scale rounding noise once transforms are applied.
_FLOAT32_EPS = 1.1920929e-07


@dataclass(frozen=True)
class MeasurementEnvelope:
    """Quantized measurements and their containing world-space cage bounds."""

    minimum: Vector3
    maximum: Vector3
    dimensions: Vector3
    increment: float


def measurement_envelope(
    bounds: PresentationBounds,
    increment: float,
) -> MeasurementEnvelope:
    """Quantize each asset extent upward from its minimum corner.

    Near-increment floating-point noise is snapped to the increment for the
    reported measurement. Blender supplies single-precision world bounds, so
    the snap tolerance also covers a few float32 ulps of the coordinate
    magnitude, capped at half an increment. The geometric maximum still
    includes the raw asset maximum, so this tolerance can never make the cage
    smaller than the asset. Degenerate axes remain zero-sized.
    """

    try:
        step = float(increment)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Envelope increment must be a finite positive number.") from exc
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("Envelope increment must be a finite positive number.")

    dimensions = []
    maximum = []
    for lower, upper in zip(bounds.minimum, bounds.maximum):
        extent = float(upper) - float(lower)
        if not math.isfinite(extent) or extent < 0.0:
            raise ValueError("Asset bounds must have finite, nonnegative dimensions.")
        if extent == 0.0:
            rounded = 0.0
        else:
            ratio = extent / step
            if not math.isfinite(ratio):
                raise ValueError("Envelope dimensions exceed the supported range.")
            nearest_units = round(ratio)
            nearest_extent = nearest_units * step
            tolerance = step * 1e-9
            # Blender's geometry pipeline is single precision, so world-space
            # extents can deviate from exact arithmetic by a few float32 ulps
            # of the coordinate magnitude. Snap within that noise floor,
            # capped at half an increment so noise can never shift a
            # measurement visibly.
            noise = min(
                max(abs(float(lower)), abs(float(upper)), abs(extent))
                * _FLOAT32_EPS
                * 8.0,
                step * 0.5,
            )
            tolerance = max(tolerance, noise)
            if math.isfinite(nearest_extent):
                tolerance = max(
                    tolerance,
                    math.ulp(extent) * 4.0,
                    math.ulp(nearest_extent) * 4.0,
                )
            if (
                nearest_units > 0
                and math.isfinite(nearest_extent)
                and abs(extent - nearest_extent) <= tolerance
            ):
                units = nearest_units
            else:
                units = math.ceil(ratio)
            rounded = units * step
            if not math.isfinite(rounded):
                raise ValueError("Envelope dimensions exceed the supported range.")
        dimensions.append(rounded)
        candidate_maximum = float(lower) + rounded
        if not math.isfinite(candidate_maximum):
            raise ValueError("Envelope dimensions exceed the supported range.")
        maximum.append(max(float(upper), candidate_maximum))

    return MeasurementEnvelope(
        minimum=tuple(float(value) for value in bounds.minimum),
        maximum=tuple(maximum),
        dimensions=tuple(dimensions),
        increment=step,
    )


def _axis_values(lower: float, upper: float, divisions: int) -> Iterable[float]:
    step = (upper - lower) / float(divisions)
    return (
        upper if index == divisions else lower + step * index
        for index in range(divisions + 1)
    )


def default_grid_divisions(dimensions: Sequence[float]) -> Tuple[int, int, int]:
    """Choose at least one segment per axis, targeting 1 m grid cells."""
    if len(dimensions) != 3:
        raise ValueError("Measurement cage dimensions must contain X, Y and Z.")
    values = tuple(float(value) for value in dimensions)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("Measurement cage dimensions must be finite and nonnegative.")
    return tuple(
        max(1, math.ceil(value - 1e-9 * max(1.0, value)))
        for value in values
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
