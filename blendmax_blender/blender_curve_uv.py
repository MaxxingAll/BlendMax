"""Blender side of BlendMax > Curve UV > Project From View.

A Curve datablock has no mesh UV layers, so the UV map lives on the Curve's
evaluated geometry instead: a Geometry Nodes modifier on the Curve projects
every point through the stored view and writes the result as the ``UVMap``
face-corner attribute, which Blender and renderers read as a normal UV map.
No second object is made, and the Curve stays an editable Curve.

The node graph repeats :func:`curve_uv.project_from_view` step by step,
including its guard at and behind the viewpoint (w <= MIN_W: no divide), so
the written UVs stay finite and match the Python reference everywhere. It
does not use Project Point, which divides by any w.

The view is stored on the modifier as plain numbers (the clip-space x, y and
w rows, and the viewport fit), because Blender does not let a modifier input
hold a matrix. Every modifier shares one node group.
"""

from __future__ import annotations

from typing import NamedTuple, Tuple

import bpy

from .curve_uv import MIN_W, project_from_view, uv_fit

_GROUP_NAME = "BlendMax Curve UV"
_GROUP_KEY = "blendmax_curve_uv_group"
_GROUP_VALUE = "project_from_view"
_MODIFIER_NAME = "BlendMax Curve UV"
_PANEL_NAME = "Stored View"
_UV_MAP_NAME = "UVMap"

# Clip-space rows the projection needs: x, y and w (z, the depth, is unused).
_ROWS = (0, 1, 3)
_FIT_NAMES = ("U Scale", "U Offset", "V Scale", "V Offset")


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


def _math(nodes, links, operation, *sources):
    """A Math node; ``sources`` are output sockets or constants, in input order."""
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    for index, source in enumerate(sources):
        if isinstance(source, float):
            node.inputs[index].default_value = source
        else:
            links.new(source, node.inputs[index])
    return node.outputs[0]


def _clip_row(nodes, links, group_in, position, row):
    """dot(row xyz, position) + row w: one clip-space coordinate."""
    combine = nodes.new("ShaderNodeCombineXYZ")
    for column, axis in enumerate("XYZ"):
        links.new(group_in.outputs[_input_name(row, column)], combine.inputs[axis])
    dot = nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    links.new(position, dot.inputs[0])
    links.new(combine.outputs["Vector"], dot.inputs[1])
    return _math(nodes, links, "ADD", dot.outputs["Value"], group_in.outputs[_input_name(row, 3)])


def _build_group():
    """Position -> clip x, y, w -> guarded divide -> fit -> Store UVMap."""
    tree = bpy.data.node_groups.new(_GROUP_NAME, "GeometryNodeTree")
    tree[_GROUP_KEY] = _GROUP_VALUE
    interface = tree.interface
    interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    panel = interface.new_panel(_PANEL_NAME, default_closed=True)
    names = [_input_name(row, column) for row in _ROWS for column in range(4)]
    for name in names + list(_FIT_NAMES):
        interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat", parent=panel)
    interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = tree.nodes, tree.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    position = nodes.new("GeometryNodeInputPosition").outputs["Position"]
    clip_x, clip_y, clip_w = (
        _clip_row(nodes, links, group_in, position, row) for row in _ROWS
    )

    # On or behind the viewpoint (w <= MIN_W) divide by 1, as project_from_view.
    in_front = nodes.new("FunctionNodeCompare")
    in_front.data_type = "FLOAT"
    in_front.operation = "GREATER_THAN"
    links.new(clip_w, in_front.inputs[0])
    in_front.inputs[1].default_value = MIN_W
    divisor = nodes.new("GeometryNodeSwitch")
    divisor.input_type = "FLOAT"
    links.new(in_front.outputs["Result"], divisor.inputs["Switch"])
    divisor.inputs["False"].default_value = 1.0
    links.new(clip_w, divisor.inputs["True"])

    uv = nodes.new("ShaderNodeCombineXYZ")
    for clip, (scale, offset), axis in (
        (clip_x, _FIT_NAMES[:2], "X"),
        (clip_y, _FIT_NAMES[2:], "Y"),
    ):
        ndc = _math(nodes, links, "DIVIDE", clip, divisor.outputs["Output"])
        value = _math(
            nodes, links, "MULTIPLY_ADD", ndc, group_in.outputs[scale], group_in.outputs[offset]
        )
        links.new(value, uv.inputs[axis])
    uv.inputs["Z"].default_value = 0.0

    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT2"
    store.domain = "CORNER"
    store.inputs["Name"].default_value = _UV_MAP_NAME
    links.new(group_in.outputs["Geometry"], store.inputs["Geometry"])
    links.new(uv.outputs["Vector"], store.inputs["Value"])
    links.new(store.outputs["Geometry"], group_out.inputs["Geometry"])

    for index, node in enumerate(nodes):
        node.location = ((index % 8) * 180.0, -(index // 8) * 220.0)
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


def _set_view(modifier, group, matrix, fit) -> None:
    """Store the clip rows of ``matrix`` and the viewport ``fit`` on the modifier."""
    identifiers = {
        item.name: item.identifier
        for item in group.interface.items_tree
        if getattr(item, "item_type", None) == "SOCKET" and item.in_out == "INPUT"
    }
    values = {
        _input_name(row, column): matrix[row][column]
        for row in _ROWS
        for column in range(4)
    }
    values.update(zip(_FIT_NAMES, fit))
    # Blender 5 reaches modifier inputs through ``properties.inputs``; older
    # versions keep them as ID properties on the modifier.
    properties = getattr(modifier, "properties", None)
    inputs = getattr(properties, "inputs", None)
    for name, value in values.items():
        identifier = identifiers[name]
        if inputs is not None:
            getattr(inputs, identifier).value = float(value)
        else:
            modifier[identifier] = float(value)


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
        _set_view(modifier, modifier.node_group, matrix, uv_fit(region.width, region.height))
        _refresh(modifier)
    return ProjectionResult(tuple(curve for curve, _ in targets), tuple(skipped), outside)
