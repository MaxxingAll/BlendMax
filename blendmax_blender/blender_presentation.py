"""Blender-side presentation tools for the BlendMax Measurement Cage."""

from __future__ import annotations

import math

import bpy

from .blender_scene import presentation_bounds
from .placement import Bounds
from .presentation_cage import cage_geometry

_COLLECTION_NAME = "BlendMax Presentation"
_COLLECTION_KEY = "blendmax_presentation_collection"
_COLLECTION_VALUE = "presentation"
_CAGE_NAME = "BlendMax Measurement Cage"
_TOOL_KEY = "blendmax_presentation_tool"
_TOOL_VALUE = "measurement_cage"
_KIND_KEY = "blendmax_presentation_kind"
_KIND_CAGE = "cage"
_KIND_LABEL = "label"
_SOURCE_KEY = "blendmax_measurement_source"
_DIMENSION_KEY = "blendmax_measurement_dimension"


def _is_cage_object(obj) -> bool:
    getter = getattr(obj, "get", None)
    return callable(getter) and getter(_TOOL_KEY) == _TOOL_VALUE


def _presentation_collection(context):
    collection = next(
        (
            item
            for item in bpy.data.collections
            if item.get(_COLLECTION_KEY) == _COLLECTION_VALUE
        ),
        None,
    )
    if collection is None:
        collection = bpy.data.collections.new(_COLLECTION_NAME)
        collection[_COLLECTION_KEY] = _COLLECTION_VALUE
        context.scene.collection.children.link(collection)
    elif collection.name not in {item.name for item in context.scene.collection.children}:
        context.scene.collection.children.link(collection)
    return collection


def _link_only_to(obj, collection) -> None:
    if collection not in obj.users_collection:
        collection.objects.link(obj)
    for current in tuple(obj.users_collection):
        if current != collection:
            current.objects.unlink(obj)


def _remove_object(obj) -> None:
    """Remove an object and free its datablock once nothing else uses it."""

    data = getattr(obj, "data", None)
    datablocks = {
        "MESH": "meshes",
        "CURVE": "curves",
        "FONT": "curves",
    }
    collection_name = datablocks.get(getattr(obj, "type", ""))
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is None or collection_name is None or getattr(data, "users", 0) != 0:
        return
    getattr(bpy.data, collection_name).remove(data)


def _get_or_create_cage(collection):
    cage = next(
        (
            obj
            for obj in bpy.data.objects
            if _is_cage_object(obj) and obj.get(_KIND_KEY) == _KIND_CAGE
        ),
        None,
    )
    if cage is None:
        mesh = bpy.data.meshes.new(_CAGE_NAME)
        cage = bpy.data.objects.new(_CAGE_NAME, mesh)
        cage[_TOOL_KEY] = _TOOL_VALUE
        cage[_KIND_KEY] = _KIND_CAGE
        collection.objects.link(cage)
    else:
        _link_only_to(cage, collection)
        if cage.type != "MESH" or cage.data is None:
            old_name = cage.name
            _remove_object(cage)
            mesh = bpy.data.meshes.new(old_name)
            cage = bpy.data.objects.new(old_name, mesh)
            cage[_TOOL_KEY] = _TOOL_VALUE
            cage[_KIND_KEY] = _KIND_CAGE
            collection.objects.link(cage)
    return cage


def _get_or_create_label(collection, dimension):
    label = next(
        (
            obj
            for obj in bpy.data.objects
            if _is_cage_object(obj)
            and obj.get(_KIND_KEY) == _KIND_LABEL
            and obj.get(_DIMENSION_KEY) == dimension
        ),
        None,
    )
    if label is None:
        name = "BlendMax Measurement {0}".format(dimension)
        curve = bpy.data.curves.new(name, type="FONT")
        label = bpy.data.objects.new(name, curve)
        label[_TOOL_KEY] = _TOOL_VALUE
        label[_KIND_KEY] = _KIND_LABEL
        label[_DIMENSION_KEY] = dimension
        collection.objects.link(label)
    else:
        _link_only_to(label, collection)
    return label


def _format_dimension(value: float) -> str:
    return "{0:.3f} m".format(float(value))


def _configure_label(label, text, location, rotation, size, in_front):
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.align_y = "CENTER"
    label.data.size = size
    label.location = location
    label.rotation_mode = "XYZ"
    label.rotation_euler = rotation
    label.hide_render = True
    label.show_in_front = bool(in_front)
    label.hide_set(False)


def _reset_world_transform(obj) -> None:
    """Keep generated world-space coordinates in an identity local frame."""
    obj.parent = None
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.delta_location = (0.0, 0.0, 0.0)
    obj.delta_rotation_euler = (0.0, 0.0, 0.0)
    obj.delta_scale = (1.0, 1.0, 1.0)


def _bounds_pair(bounds) -> Bounds:
    return bounds.minimum, bounds.maximum


def _update_mesh(cage, bounds, divisions):
    vertices, edges = cage_geometry(_bounds_pair(bounds), divisions)
    mesh = cage.data
    mesh.clear_geometry()
    mesh.from_pydata(vertices, edges, [])
    mesh.update()


def _hide_extra_labels(visible_dimensions):
    for obj in bpy.data.objects:
        if not _is_cage_object(obj) or obj.get(_KIND_KEY) == _KIND_CAGE:
            continue
        if obj.get(_DIMENSION_KEY) not in visible_dimensions:
            obj.hide_set(True)


def create_measurement_cage(context, *, margin=0.0, divisions=(1, 1, 1), show_dimensions=True, in_front=True):
    """Create or update the single BlendMax measurement cage for the selection."""
    active = context.view_layer.objects.active
    source = None
    if active is not None and _is_cage_object(active):
        # Re-running with the cage active reuses its stored source; when that
        # object is gone (deleted or renamed), fall back to the selection so
        # the cage can re-target instead of failing outright.
        source_name = active.get(_SOURCE_KEY)
        if source_name:
            source = bpy.data.objects.get(source_name)
    elif active is not None:
        source = active
    if source is None:
        source = next(
            (obj for obj in context.selected_objects if not _is_cage_object(obj)),
            None,
        )

    if source is None:
        raise ValueError("Select a BlendMax asset/object with mesh geometry first.")

    bounds = presentation_bounds([source], source_root=source.name)
    if bounds is None:
        raise ValueError("The selected object/asset has no valid mesh geometry.")

    amount = float(margin)
    if amount < 0.0:
        raise ValueError("Measurement cage margin cannot be negative.")
    cage_bounds = bounds.expanded(amount)
    collection = _presentation_collection(context)
    cage = _get_or_create_cage(collection)
    _reset_world_transform(cage)
    _update_mesh(cage, cage_bounds, divisions)

    cage[_SOURCE_KEY] = source.name
    cage["blendmax_measurement_margin"] = amount
    cage["blendmax_measurement_divisions"] = tuple(int(value) for value in divisions)
    cage["blendmax_measurement_dimensions"] = tuple(float(value) for value in bounds.dimensions)
    cage["blendmax_measurement_center"] = tuple(float(value) for value in bounds.center)
    cage.hide_render = True
    cage.show_in_front = bool(in_front)
    cage.display_type = "WIRE"
    cage.hide_set(False)

    visible_dimensions = set()
    if show_dimensions:
        width, depth, height = bounds.dimensions
        extent = max(max(bounds.dimensions), 1e-3)
        offset = max(extent * 0.025, 0.01)
        x0, y0, z0 = bounds.minimum
        x1, y1, z1 = bounds.maximum
        label_specs = (
            ("Width", "W {0}".format(_format_dimension(width)), ((x0 + x1) * 0.5, y0 - offset, z1 + offset), (math.pi / 2.0, 0.0, 0.0)),
            ("Depth", "D {0}".format(_format_dimension(depth)), (x1 + offset, (y0 + y1) * 0.5, z1 + offset), (0.0, math.pi / 2.0, 0.0)),
            ("Height", "H {0}".format(_format_dimension(height)), (x0 - offset, y0 - offset, (z0 + z1) * 0.5), (math.pi / 2.0, 0.0, 0.0)),
        )
        size = min(max(extent * 0.06, 0.02), 0.5)
        for dimension_name, text, location, rotation in label_specs:
            label = _get_or_create_label(collection, dimension_name)
            _reset_world_transform(label)
            _configure_label(label, text, location, rotation, size, in_front)
            visible_dimensions.add(dimension_name)
    _hide_extra_labels(visible_dimensions)

    for obj in context.selected_objects:
        obj.select_set(False)
    source.select_set(True)
    context.view_layer.objects.active = source
    return cage, bounds


def remove_measurement_cage() -> int:
    """Remove the BlendMax measurement cage and all of its supporting objects.

    Objects are removed together with their mesh/curve datablocks once
    nothing else uses them, and the presentation collection is removed when
    it is left empty. Returns the number of removed objects.
    """

    removed = 0
    for obj in tuple(bpy.data.objects):
        if _is_cage_object(obj):
            _remove_object(obj)
            removed += 1
    collection = next(
        (
            item
            for item in bpy.data.collections
            if item.get(_COLLECTION_KEY) == _COLLECTION_VALUE
        ),
        None,
    )
    if collection is not None and not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
    return removed
