"""Scene and scale policies that do not depend on 3ds Max."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from .errors import SceneValidationError
from .models import SceneNode, SizePolicyResult, ValidationResult


DEFAULT_MAX_OBJECTS = 30
DEFAULT_MAX_FOOTPRINT_M = 50.0
DEFAULT_MIN_LARGEST_DIMENSION_M = 0.01


def _descendant_ids(root_id: str, nodes: Iterable[SceneNode]) -> Set[str]:
    children: Dict[str, List[str]] = {}
    for node in nodes:
        if node.parent_id:
            children.setdefault(node.parent_id, []).append(node.node_id)

    found: Set[str] = set()
    pending = list(children.get(root_id, []))
    while pending:
        node_id = pending.pop()
        if node_id in found:
            continue
        found.add(node_id)
        pending.extend(children.get(node_id, []))
    return found


def _has_group_ancestor(
    node: SceneNode,
    node_by_id: Dict[str, SceneNode],
) -> bool:
    parent_id = node.parent_id
    visited: Set[str] = set()
    while parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = node_by_id.get(parent_id)
        if parent is None:
            return False
        if parent.is_group_head:
            return True
        parent_id = parent.parent_id
    return False


def _is_geometry(node: SceneNode) -> bool:
    return not node.is_group_head and "geometryclass" in node.superclass.casefold()


def validate_scene(
    nodes: Iterable[SceneNode],
    max_objects: int = DEFAULT_MAX_OBJECTS,
) -> ValidationResult:
    """Accept exactly one group asset or one standalone exportable object."""

    scene_nodes = list(nodes)
    if any(node.hidden_or_frozen for node in scene_nodes):
        raise SceneValidationError(
            "HIDDEN_OR_FROZEN_OBJECTS",
            (
                "The scene contains hidden or frozen objects! "
                "Ensure all objects are visible and unfrozen before continuing."
            ),
        )

    node_by_id = {node.node_id: node for node in scene_nodes}
    exportable = [node for node in scene_nodes if node.exportable]
    group_heads = [node for node in scene_nodes if node.is_group_head]
    top_group_heads = [
        node
        for node in group_heads
        if not _has_group_ancestor(node, node_by_id)
    ]

    if top_group_heads:
        if len(top_group_heads) != 1:
            raise SceneValidationError(
                "MULTIPLE_GROUPS",
                "BlendMax found more than one top-level group. Isolate one asset first.",
            )

        root = top_group_heads[0]
        descendant_ids = _descendant_ids(root.node_id, scene_nodes)
        payload = [
            node
            for node in exportable
            if node.node_id in descendant_ids
        ]
        extras = [
            node
            for node in exportable
            if node.node_id not in descendant_ids
            and node.node_id != root.node_id
        ]
        if extras:
            raise SceneValidationError(
                "MIXED_ASSETS",
                "BlendMax found objects outside the asset group. Keep only one grouped asset.",
            )
        if not payload:
            raise SceneValidationError(
                "EMPTY_GROUP",
                "The only group in the scene contains no exportable geometry.",
            )

        export_ids = [root.node_id]
        export_ids.extend(node.node_id for node in payload)
        export_ids.extend(
            node.node_id
            for node in scene_nodes
            if node.node_id in descendant_ids
            and node.is_group_head
        )
        mode = "group"
    else:
        if not exportable:
            raise SceneValidationError(
                "NO_ASSET",
                "BlendMax could not find an exportable object in this scene.",
            )
        if len(exportable) != 1:
            raise SceneValidationError(
                "MULTIPLE_OBJECTS",
                "BlendMax found multiple ungrouped objects. Group one asset or isolate one object first.",
            )
        root = exportable[0]
        payload = [root]
        export_ids = [root.node_id]
        mode = "object"

    if len(payload) > max_objects:
        raise SceneValidationError(
            "TOO_MANY_OBJECTS",
            "This asset contains {0} objects; BlendMax v0.1 allows at most {1}.".format(
                len(payload), max_objects
            ),
        )

    ignored = [
        node.name
        for node in scene_nodes
        if not node.exportable
        and not node.is_group_head
        and not _is_geometry(node)
    ]
    warnings = []
    if ignored:
        warnings.append(
            "Ignored non-geometry scene nodes: {0}".format(
                ", ".join(sorted(ignored))
            )
        )

    return ValidationResult(
        mode=mode,
        root_id=root.node_id,
        payload_ids=tuple(node.node_id for node in payload),
        export_ids=tuple(dict.fromkeys(export_ids)),
        warnings=tuple(warnings),
    )


def evaluate_size_policy(
    dimensions_m,
    max_footprint_m: float = DEFAULT_MAX_FOOTPRINT_M,
    min_largest_dimension_m: float = DEFAULT_MIN_LARGEST_DIMENSION_M,
) -> SizePolicyResult:
    dimensions = tuple(max(0.0, float(value)) for value in dimensions_m)
    if len(dimensions) != 3:
        raise ValueError("dimensions_m must contain X, Y and Z")

    largest = max(dimensions)
    if largest < min_largest_dimension_m:
        raise SceneValidationError(
            "TOO_SMALL",
            (
                "Object is too small! Even Blender needs a magnifying glass. "
                "Largest dimension: {0:.6f} m; minimum: {1:.3f} m."
            ).format(largest, min_largest_dimension_m),
        )

    footprint = max(dimensions[0], dimensions[1])
    oversized = footprint > max_footprint_m
    recommended_scale = (
        max_footprint_m / footprint if oversized and footprint > 0.0 else 1.0
    )
    return SizePolicyResult(
        dimensions_m=dimensions,
        recommended_scale=recommended_scale,
        oversized=oversized,
    )
