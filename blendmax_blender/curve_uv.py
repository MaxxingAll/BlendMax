"""Pure viewport-to-UV projection for Curve UV > Project From View.

This module has no Blender dependency. It reproduces the mapping of Blender's
Mesh > UV > Project From View (``BLI_uvproject_from_view``): the viewport is
fitted into the 0..1 UV square by its long side, so proportions on screen are
kept and the short side is centred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

UV = Tuple[float, float]

# At or below this clip-space w a vertex is on or behind the viewpoint, where
# dividing would mirror it or blow it up. Same threshold as Blender's. The
# Curve UV node graph uses it too, so its UVs match this module's.
MIN_W = 0.00001


@dataclass(frozen=True)
class ViewProjection:
    """UVs in input order, and how many vertices fell outside the viewport."""

    uvs: Tuple[UV, ...]
    outside: int


def uv_fit(width: float, height: float) -> Tuple[float, float, float, float]:
    """``(scale_u, offset_u, scale_v, offset_v)``: NDC to UV per axis.

    ``u = scale_u * ndc_x + offset_u``: the viewport's long side spans 0..1
    and the short side is centred.
    """
    if not (width > 0 and height > 0):
        raise ValueError("The 3D viewport has no usable size.")
    side = float(max(width, height))
    return (
        width / (2.0 * side),
        ((side - width) / 2.0 + width / 2.0) / side,
        height / (2.0 * side),
        ((side - height) / 2.0 + height / 2.0) / side,
    )


def project_from_view(
    points: Iterable[Iterable[float]],
    matrix: Sequence[Sequence[float]],
    width: float,
    height: float,
) -> ViewProjection:
    """Project points through ``matrix`` (object space to clip space) into UVs.

    Geometry outside the viewport keeps its true position beyond 0..1, because
    clamping would collapse it onto the edge. A vertex on or behind the
    viewpoint has no true position, so it stays finite without the perspective
    divide and is counted as outside.
    """

    scale_u, offset_u, scale_v, offset_v = uv_fit(width, height)
    row_x, row_y, _row_z, row_w = matrix[0], matrix[1], matrix[2], matrix[3]

    uvs = []
    outside = 0
    for x, y, z in points:
        clip_x = row_x[0] * x + row_x[1] * y + row_x[2] * z + row_x[3]
        clip_y = row_y[0] * x + row_y[1] * y + row_y[2] * z + row_y[3]
        w = row_w[0] * x + row_w[1] * y + row_w[2] * z + row_w[3]
        behind = w <= MIN_W
        divisor = 1.0 if behind else w
        ndc_x = clip_x / divisor
        ndc_y = clip_y / divisor
        if behind or abs(ndc_x) > 1.0 or abs(ndc_y) > 1.0:
            outside += 1
        uvs.append((scale_u * ndc_x + offset_u, scale_v * ndc_y + offset_v))
    return ViewProjection(tuple(uvs), outside)
