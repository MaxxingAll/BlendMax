"""Blender-side presentation tools for the BlendMax Measurement Cage."""

from __future__ import annotations

import math

import bpy

from .blender_scene import presentation_bounds
from .placement import Bounds
from .presentation_cage import cage_geometry

_COLLECTION_NAME = "BlendMax Presentation"
_CAGE_NAME = "BlendMax Measurement Cage"
_TOOL_KEY = "blendmax_presentation_tool"
_TOOL_VALUE = "measurement_cage"
_SOURCE_KEY = "blendmax_measurement_source"
_DIMENSION_NAMES = ("Width", "Depth", "Height")


def _is_cage_object(obj) -> bool:
    return getattr(obj, "get", lambda *_args: None)(_TOOL_KEY) == _TOOL_VALUE


def _presentation_collection(context):
    collection = bpy.data.collections.get(_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(_COLLECTION_NAME)
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


def _get_or_create_cage(collection):
    cage = bpy.data.objects.get(_CAGE_NAME)
    if cage is not None and not _is_cage_object(cage):
        cage = None
    if cage is None:
        mesh = bpy.data.meshes.new(_CAGE_NAME)
        cage = bpy.data.objects.new(_CAGE_NAME, mesh)
        cage[_TOOL_KEY] = _TOOL_VALUE
        collection.objects.link(cage)
    else:
        _link_only_to(cage, collection)
        if cage.type != "MESH" or cage.data is None:
            old_name = cage.name
            bpy.data.objects.remove(cage, do_unlink=True)
            mesh = bpy.data.meshes.new(old_name)
            cage = bpy.data.objects.new(old_name, mesh)
            cage[_TOOL_KEY] = _TOOL_VALUE
            collection.objects.link(cage)
    return cage


def _get_or_create_label(collection, name):
    label = bpy.data.objects.get(name)
    if label is not None and label.type != "FONT":
        bpy.data.objects.remove(label, do_unlink=True)
        label = None
    if label is None:
        curve = bpy.data.curves.new(name, type="FONT")
        label = bpy.data.objects.new(name, curve)
        label[_TOOL_KEY] = _TOOL_VALUE
        collection.objects.link(label)
    else:
        _link_only_to(label, collection)
        label[_TOOL_KEY] = _TOOL_VALUE
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


def _bounds_pair(bounds) -> Bounds:
    return bounds.minimum, bounds.maximum


def _update_mesh(cage, bounds, divisions):
    vertices, edges = cage_geometry(_bounds_pair(bounds), divisions)
    mesh = cage.data
    mesh.clear_geometry()
    mesh.from_pydata(vertices, [], edges)
    mesh.update()


def _hide_extra_labels(visible_names):
    for obj in bpy.data.objects:
        if _is_cage_object(obj) and obj.name not in visible_names:
            obj.hide_set(True)


def create_measurement_cage(context, *, margin=0.0, divisions=(1, 1, 1), show_dimensions=True, in_front=True):
    """Create or update the single BlendMax measurement cage for the selection."""
    active = context.view_layer.objects.active
    if active is not None and _is_cage_object(active):
        source_name = active.get(_SOURCE_KEY)
        source = bpy.data.objects.get(source_name) if source_name else None
        roots = [source] if source is not None else []
    else:
        roots = [obj for obj in context.selected_objects if not _is_cage_object(obj)]
        source = active if active in roots else (roots[0] if roots else None)

    if not roots or source is None:
        raise ValueError("Select a BlendMax asset/object with mesh geometry first.")

    bounds = presentation_bounds(roots, source_root=source.name)
    if bounds is None:
        raise ValueError("The selected object/asset has no valid mesh geometry.")

    amount = float(margin)
    if amount < 0.0:
        raise ValueError("Measurement cage margin cannot be negative.")
    cage_bounds = bounds.expanded(amount)
    collection = _presentation_collection(context)
    cage = _get_or_create_cage(collection)
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

    label_names = []
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
            label = _get_or_create_label(collection, "BlendMax Measurement {0}".format(dimension_name))
            _configure_label(label, text, location, rotation, size, in_front)
            label_names.append(label.name)
    _hide_extra_labels(set(label_names) | {_CAGE_NAME})

    for obj in context.selected_objects:
        obj.select_set(False)
    source.select_set(True)
    context.view_layer.objects.active = source
    return cage, bounds


def remove_measurement_cage() -> None:
    """Remove the BlendMax measurement cage and its dimension labels."""
    for obj in tuple(bpy.data.objects):
        if _is_cage_object(obj):
            bpy.data.objects.remove(obj, do_unlink=True)
    collection = bpy.data.collections.get(_COLLECTION_NAME)
    if collection is not None and not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
