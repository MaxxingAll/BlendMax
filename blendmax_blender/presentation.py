"""World-space presentation bounds shared by the BlendMax presentation tools.

This is the pure, Blender-independent half of the presentation-bounds
foundation consumed by the Measurement Cage (#45) and the orthographic
camera setup (#46). It owns one authoritative world-space bounds pair for
the asset that presentation tools operate on, plus the derived values both
features must agree on: dimensions and center.

The Blender-specific gathering step -- walking scene objects and their
hierarchies -- lives in
``blendmax_blender.blender_scene.presentation_bounds``. Nothing here
imports ``bpy``.

Raw bounds describe the actual asset. Presentation margin/framing is an
explicit derived operation (:meth:`PresentationBounds.expanded`) rather
than baked into the stored bounds, so the cage measures the real asset
while cameras may frame a grown copy -- one cannot influence the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .placement import Bounds, Vector3, bounds_from_points


@dataclass(frozen=True)
class PresentationBounds:
    """Authoritative world-space bounds for the presentation tools.

    ``minimum``/``maximum`` are the only stored geometry; ``dimensions``
    and ``center`` are derived from that pair so it stays the single source
    of truth. ``source_root`` optionally records the object/root the bounds
    were gathered from, for future update-from-source flows.
    """

    minimum: Vector3
    maximum: Vector3
    source_root: Optional[str] = None

    @classmethod
    def from_points(
        cls,
        points: Iterable[Iterable[float]],
        source_root: Optional[str] = None,
    ) -> Optional["PresentationBounds"]:
        """Bounds of an arbitrary world-space point cloud.

        Returns ``None`` for an empty cloud: callers must handle "no valid
        geometry" explicitly, and no fallback size is invented.
        """

        bounds = bounds_from_points(points)
        if bounds is None:
            return None
        return cls.from_bounds(bounds, source_root=source_root)

    @classmethod
    def from_bounds(
        cls,
        bounds: Bounds,
        source_root: Optional[str] = None,
    ) -> "PresentationBounds":
        """Wrap an existing ``(minimum, maximum)`` pair from ``placement``."""

        minimum, maximum = bounds
        return cls(tuple(minimum), tuple(maximum), source_root=source_root)

    @property
    def dimensions(self) -> Vector3:
        return tuple(
            upper - lower for lower, upper in zip(self.minimum, self.maximum)
        )

    @property
    def center(self) -> Vector3:
        return tuple(
            (lower + upper) * 0.5
            for lower, upper in zip(self.minimum, self.maximum)
        )

    def expanded(self, margin: float) -> "PresentationBounds":
        """A copy grown by ``margin`` on every side of every axis.

        Presentation framing, deliberately derived on demand: the stored
        bounds stay the raw asset bounds. A zero margin is a value-equal
        copy; a negative margin shrinks, and an oversized one inverts the
        axis, so callers keep margins sane.
        """

        amount = float(margin)
        return PresentationBounds(
            tuple(lower - amount for lower in self.minimum),
            tuple(upper + amount for upper in self.maximum),
            source_root=self.source_root,
        )
