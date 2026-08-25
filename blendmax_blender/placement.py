"""Pure-Python bounding-box and hierarchy placement helpers."""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Tuple


Vector3 = Tuple[float, float, float]
Bounds = Tuple[Vector3, Vector3]


def bounds_from_points(points: Iterable[Iterable[float]]) -> Optional[Bounds]:
    iterator = iter(points)
    try:
        first = tuple(next(iterator))
    except StopIteration:
        return None

    minimum = [float(value) for value in first]
    maximum = list(minimum)
    for point in iterator:
        for axis, value in enumerate(point):
            coordinate = float(value)
            minimum[axis] = min(minimum[axis], coordinate)
            maximum[axis] = max(maximum[axis], coordinate)
    return tuple(minimum), tuple(maximum)  # type: ignore[return-value]


def merge_bounds(items: Iterable[Bounds]) -> Optional[Bounds]:
    return bounds_from_points(
        point for minimum, maximum in items for point in (minimum, maximum)
    )


def grounded_anchor(bounds: Bounds) -> Vector3:
    minimum, maximum = bounds
    return (
        (minimum[0] + maximum[0]) * 0.5,
        (minimum[1] + maximum[1]) * 0.5,
        minimum[2],
    )


def hierarchy_bounds(
    parent_ids: Mapping[str, Optional[str]],
    object_bounds: Mapping[str, Bounds],
) -> Dict[str, Bounds]:
    children: Dict[str, List[str]] = {object_id: [] for object_id in parent_ids}
    for object_id, parent_id in parent_ids.items():
        if parent_id in children:
            children[parent_id].append(object_id)

    cache: Dict[str, Optional[Bounds]] = {}
    visiting = set()

    def collect(object_id: str) -> Optional[Bounds]:
        if object_id in cache:
            return cache[object_id]
        if object_id in visiting:
            raise ValueError("Object hierarchy contains a parent cycle.")

        visiting.add(object_id)
        branch = []
        own = object_bounds.get(object_id)
        if own is not None:
            branch.append(own)
        for child_id in children.get(object_id, ()):
            child_bounds = collect(child_id)
            if child_bounds is not None:
                branch.append(child_bounds)
        visiting.remove(object_id)

        cache[object_id] = merge_bounds(branch)
        return cache[object_id]

    for object_id in parent_ids:
        collect(object_id)
    return {
        object_id: bounds
        for object_id, bounds in cache.items()
        if bounds is not None
    }
