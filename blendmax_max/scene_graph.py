"""Pure scene-graph helpers shared by the Max-side validation and cleanup.

These operate only on :class:`~blendmax_max.models.SceneNode` values and never
touch 3ds Max itself, so they are testable with ordinary Python.

They previously existed as private duplicates inside
:mod:`blendmax_max.validation` and :mod:`blendmax_max.cleanup`. The two
``_descendant_ids`` copies were identical apart from spelling the empty default
as ``[]`` in one and ``()`` in the other; ``is_geometry`` was identical in both.
The shared implementations below preserve the original behaviour exactly --
this module is an extraction, not a rewrite.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from .models import SceneNode


def descendant_ids(root_id: str, nodes: Iterable[SceneNode]) -> Set[str]:
    """Return every descendant id of ``root_id``, excluding the root itself.

    Walks child links built from each node's ``parent_id``. The ``found`` set
    also provides cycle protection: a node already collected is skipped rather
    than re-expanded, so a parent cycle terminates instead of looping forever.
    Nodes whose ``parent_id`` is missing from ``nodes`` are never reached, and a
    node that is its own ancestor appears once.
    """

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


def has_group_ancestor(
    node: SceneNode,
    node_by_id: Dict[str, SceneNode],
) -> bool:
    """Return True when any ancestor of ``node`` is a group head.

    Stops at the first ancestor missing from ``node_by_id`` and returns False
    for it, and stops on a cycle via ``visited``, so a dangling ``parent_id``
    or a parent loop cannot hang the walk.
    """

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


def is_geometry(node: SceneNode) -> bool:
    """Return True for geometry nodes. Group heads are never geometry."""

    return not node.is_group_head and "geometryclass" in node.superclass.casefold()
