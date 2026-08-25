"""Pure cleanup planning helpers with no dependency on 3ds Max."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set, Tuple, TypeVar

from .errors import CleanupError
from .models import SceneNode


T = TypeVar("T")

ROOT_GROUP_NOT_DETECTED_MESSAGE = (
    "Root Group not Detected, Please open the group and select the Pink Box "
    "to pin the group as a Root Group"
)


@dataclass(frozen=True)
class CleanupPlan:
    root_id: str
    visible_geometry_ids: Tuple[str, ...]
    shape_ids: Tuple[str, ...]
    removable_group_ids: Tuple[str, ...]


def _is_geometry(node: SceneNode) -> bool:
    return not node.is_group_head and "geometryclass" in node.superclass.casefold()


def _is_shape(node: SceneNode) -> bool:
    if node.is_group_head:
        return False
    superclass = node.superclass.casefold()
    node_type = node.node_type.casefold()
    return (
        "shape" in superclass
        or "shape" in node_type
        or "spline" in node_type
        or node_type == "line"
    )


def _descendant_ids(root_id: str, nodes: Iterable[SceneNode]) -> Set[str]:
    children: Dict[str, List[str]] = {}
    for node in nodes:
        if node.parent_id:
            children.setdefault(node.parent_id, []).append(node.node_id)

    found: Set[str] = set()
    pending = list(children.get(root_id, ()))
    while pending:
        node_id = pending.pop()
        if node_id in found:
            continue
        found.add(node_id)
        pending.extend(children.get(node_id, ()))
    return found


def build_cleanup_plan(
    nodes: Iterable[SceneNode],
    root_id: str,
) -> CleanupPlan:
    """Plan a root-scoped join after a strict visibility preflight."""

    scene_nodes = list(nodes)
    node_by_id = {node.node_id: node for node in scene_nodes}
    root = node_by_id.get(root_id)
    if root is None or not root.is_group_head:
        raise CleanupError(ROOT_GROUP_NOT_DETECTED_MESSAGE)

    if any(node.hidden_or_frozen for node in scene_nodes):
        raise CleanupError(
            "The scene contains hidden or frozen objects! "
            "Ensure all objects are visible and unfrozen before continuing."
        )

    descendants = _descendant_ids(root_id, scene_nodes)
    visible_geometry = [
        node.node_id
        for node in scene_nodes
        if node.node_id in descendants and _is_geometry(node)
    ]
    shapes = [
        node.node_id
        for node in scene_nodes
        if node.node_id in descendants and _is_shape(node)
    ]

    if not visible_geometry:
        raise CleanupError(
            "The selected group contains no geometry to clean."
        )

    removable_groups = [
        node.node_id
        for node in scene_nodes
        if node.node_id in descendants and node.is_group_head
    ]

    return CleanupPlan(
        root_id=root_id,
        visible_geometry_ids=tuple(visible_geometry),
        shape_ids=tuple(shapes),
        removable_group_ids=tuple(removable_groups),
    )


def material_id_lookup(
    material_ids: Sequence[int],
    materials: Sequence[T],
) -> Dict[int, T]:
    """Map Multi/Sub IDs to slots without assuming list position equals ID."""

    return {
        int(material_id): material
        for material_id, material in zip(material_ids, materials)
    }


def format_face_bitarray(face_indices: Iterable[int]) -> str:
    """Create a compact MAXScript BitArray expression from one-based faces."""

    values = sorted({int(index) for index in face_indices if int(index) > 0})
    if not values:
        return "#{}"

    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = previous = value
    ranges.append((start, previous))

    tokens = [
        str(start) if start == end else "{0}..{1}".format(start, end)
        for start, end in ranges
    ]
    return "#{" + ",".join(tokens) + "}"
