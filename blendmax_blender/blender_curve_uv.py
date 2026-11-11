"""Blender side of BlendMax > Curve UV > Project From View.

A Curve datablock has no mesh UV layers, so the UV map lives on the Curve's
evaluated geometry instead: a Geometry Nodes modifier on the Curve projects
every point through the stored view and writes the result as the ``UVMap``
face-corner attribute, which Blender and renderers read as a normal UV map.
No second object is made, and the Curve stays an editable Curve.

The view is stored as 16 numbers on the modifier, because Blender does not let
a modifier input hold a matrix. Every modifier shares one node group.
"""

from __future__ import annotations

from typing import NamedTuple, Tuple

import bpy

from .curve_uv import project_from_view, uv_matrix

_GROUP_NAME = "BlendMax Curve UV"
_GROUP_KEY = "blendmax_curve_uv_group"
_GROUP_VALUE = "project_from_view"
_MODIFIER_NAME = "BlendMax Curve UV"
_PANEL_NAME = "Stored View"
_UV_MAP_NAME = "UVMap"


def _input_name(row: int, column: int) -> str:
    return "Row {0} Column {1}".format(row + 1, column + 1)


class ProjectionResult(NamedTuple):
    """Curves projected, curves without faces, vertices out of view."""

    projected: Tuple[object, ...]
    skipped: Tuple[str, ...]
    outside: int


def _selected_curves(context):
    return [obj for obj in context.selected_objects if obj.type == "CURVE"]


def _largest(items):
    return max(items, key=lambda item: item.width * item.height, default=None)


def _viewport_region(context):
    """The 3D viewport region to project from.

    The BlendMax menu lives in the top bar, whose context has no viewport, and
    Blender does not expose the last-used one. A run from inside a viewport
    (F3 search) uses that viewport; otherwise the largest one on the screen.
    """
    region = context.region
    area = context.area
    if not (
        area is not None
        and area.type == "VIEW_3D"
        and region is not None
        and region.type == "WINDOW"
    ):
        screen = context.screen
        area = _largest(
            [item for item in (screen.areas if screen else ()) if item.type == "VIEW_3D"]
        )
        if area is None:
            raise ValueError("Open a 3D Viewport to project from.")
        region = _largest([item for item in area.regions if item.type == "WINDOW"])
    if region is None or region.data is None or region.width < 1 or region.height < 1:
        raise ValueError("The 3D viewport has no usable size.")
    return region


def _is_ours(group) -> bool:
    return group is not None and group.get(_GROUP_KEY) == _GROUP_VALUE


def _build_group():
    """Position -> Project Point (stored view) -> Store Named Attribute UVMap."""
    tree = bpy.data.node_groups.new(_GROUP_NAME, "GeometryNodeTree")
    tree[_GROUP_KEY] = _GROUP_VALUE
    interface = tree.interface
    interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    panel = interface.new_panel(_PANEL_NAME, default_closed=True)
    for row in range(4):
        for column in range(4):
            interface.new_socket(
                _input_name(row, column),
                in_out="INPUT",
                socket_type="NodeSocketFloat",
                parent=panel,
            )
    interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = tree.nodes, tree.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    position = nodes.new("GeometryNodeInputPosition")
    combine = nodes.new("FunctionNodeCombineMatrix")
    project = nodes.new("FunctionNodeProjectPoint")
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT2"
    store.domain = "CORNER"
    store.inputs["Name"].default_value = _UV_MAP_NAME

    for row in range(4):
        for column in range(4):
            # Combine Matrix lists its inputs column by column.
            links.new(
                group_in.outputs[_input_name(row, column)],
                combine.inputs[column * 4 + row],
            )
    links.new(group_in.outputs["Geometry"], store.inputs["Geometry"])
    links.new(position.outputs["Position"], project.inputs["Vector"])
    links.new(combine.outputs["Matrix"], project.inputs["Transform"])
    links.new(project.outputs["Vector"], store.inputs["Value"])
    links.new(store.outputs["Geometry"], group_out.inputs["Geometry"])

    for index, node in enumerate((group_in, position, combine, project, store, group_out)):
        node.location = (index * 200.0, 0.0)
    return tree


def _node_group():
    group = next((item for item in bpy.data.node_groups if _is_ours(item)), None)
    return group if group is not None else _build_group()


def _our_modifier(obj):
    return next(
        (
            modifier
            for modifier in obj.modifiers
            if modifier.type == "NODES" and _is_ours(modifier.node_group)
        ),
        None,
    )


def _set_view(modifier, group, matrix) -> None:
    identifiers = {
        item.name: item.identifier
        for item in group.interface.items_tree
        if getattr(item, "item_type", None) == "SOCKET" and item.in_out == "INPUT"
    }
    # Blender 5 reaches modifier inputs through ``properties.inputs``; older
    # versions keep them as ID properties on the modifier.
    properties = getattr(modifier, "properties", None)
    inputs = getattr(properties, "inputs", None)
    for row in range(4):
        for column in range(4):
            identifier = identifiers[_input_name(row, column)]
            value = float(matrix[row][column])
            if inputs is not None:
                getattr(inputs, identifier).value = value
            else:
                modifier[identifier] = value


def _refresh(modifier) -> None:
    """Make Blender re-evaluate the Curve and redraw its UVs.

    Writing the inputs from Python neither re-evaluates the Curve nor, after
    an object or data update tag, rebuilds the viewport's drawing of it: found
    in live use (Blender 5.2.3), Material Preview kept the old UVs after a
    re-run. Flipping the modifier's viewport switch does both, and setting it
    back keeps the user's choice.
    """
    shown = modifier.show_viewport
    modifier.show_viewport = not shown
    modifier.show_viewport = shown


def _faces_and_outside(evaluated, matrix, region):
    """Whether the evaluated Curve has faces, and its vertices out of view."""
    mesh = evaluated.to_mesh()
    try:
        if mesh is None or not mesh.polygons:
            return False, 0
        projection = project_from_view(
            [vertex.co for vertex in mesh.vertices], matrix, region.width, region.height
        )
        return True, projection.outside
    finally:
        evaluated.to_mesh_clear()


def project_curves_from_view(context) -> ProjectionResult:
    """Add or update the Curve UV modifier on every selected Curve."""
    # Edits to a Curve in Edit Mode have not reached its evaluated geometry,
    # so the face check and the out-of-view count would read the old shape.
    if context.mode != "OBJECT":
        raise ValueError("Switch to Object Mode first.")
    curves = _selected_curves(context)
    if not curves:
        raise ValueError("Select one or more Curve objects first.")
    region = _viewport_region(context)
    view_matrix = region.data.perspective_matrix
    depsgraph = context.evaluated_depsgraph_get()

    targets = []
    skipped = []
    outside = 0
    for curve in curves:
        evaluated = curve.evaluated_get(depsgraph)
        matrix = view_matrix @ evaluated.matrix_world
        has_faces, out = _faces_and_outside(evaluated, matrix, region)
        if not has_faces:
            skipped.append(curve.name)
            continue
        outside += out
        targets.append((curve, matrix))

    if not targets:
        raise ValueError(
            "The selected curves have no faces to carry UVs: "
            "close and fill them, or add a bevel or extrude."
        )

    group = _node_group()
    for curve, matrix in targets:
        modifier = _our_modifier(curve)
        if modifier is None:
            modifier = curve.modifiers.new(_MODIFIER_NAME, "NODES")
            modifier.node_group = group
        _set_view(modifier, modifier.node_group, uv_matrix(matrix, region.width, region.height))
        _refresh(modifier)
    return ProjectionResult(tuple(curve for curve, _ in targets), tuple(skipped), outside)
