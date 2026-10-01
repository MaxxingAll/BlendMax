"""Blender-side presentation tools for the BlendMax Measurement Cage."""

from __future__ import annotations

import json
import math

import bpy

from .blender_scene import presentation_bounds
from .placement import Bounds
from .presentation_cage import cage_geometry, measurement_envelope

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
_SOURCES_KEY = "blendmax_measurement_sources"
_DIMENSION_KEY = "blendmax_measurement_dimension"
_MATERIAL_KEY = "blendmax_measurement_material"
_MATERIAL_VALUE = "cage"


def _is_cage_object(obj) -> bool:
    getter = getattr(obj, "get", None)
    return callable(getter) and getter(_TOOL_KEY) == _TOOL_VALUE


def _unlink_collection_from_parents(collection, scene_collection=None, keep=None):
    parents = list(bpy.data.collections)
    if scene_collection is not None:
        parents.append(scene_collection)
    for parent in parents:
        if parent is not keep and collection in parent.children:
            parent.children.unlink(collection)


def _presentation_collection(context, hierarchy_root=None):
    root_collection = None
    if hierarchy_root is not None and hierarchy_root.users_collection:
        # Blender permits objects in several collections. The first linked
        # collection is the deterministic owner used for this presentation.
        root_collection = hierarchy_root.users_collection[0]
    parent_collection = root_collection or context.scene.collection
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
    _unlink_collection_from_parents(
        collection,
        scene_collection=context.scene.collection,
        keep=parent_collection,
    )
    if collection not in parent_collection.children:
        parent_collection.children.link(collection)
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
    cages = [
        obj
        for obj in bpy.data.objects
        if _is_cage_object(obj) and obj.get(_KIND_KEY) == _KIND_CAGE
    ]
    cage = next(
        (obj for obj in cages if obj.type == "CURVE" and obj.data is not None),
        None,
    )
    for duplicate in cages:
        if duplicate is not cage:
            _remove_object(duplicate)
    if cage is None:
        curve = bpy.data.curves.new(_CAGE_NAME, type="CURVE")
        cage = bpy.data.objects.new(_CAGE_NAME, curve)
        cage[_TOOL_KEY] = _TOOL_VALUE
        cage[_KIND_KEY] = _KIND_CAGE
        collection.objects.link(cage)
    else:
        _link_only_to(cage, collection)
    return cage


def _get_or_create_material():
    material = next(
        (
            item
            for item in bpy.data.materials
            if item.get(_MATERIAL_KEY) == _MATERIAL_VALUE
        ),
        None,
    )
    if material is None:
        material = bpy.data.materials.new("BlendMax Measurement Cage")
        material[_MATERIAL_KEY] = _MATERIAL_VALUE
    color = (0.65, 0.65, 0.65, 1.0)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        base_color = principled.inputs.get("Base Color")
        if base_color is not None:
            base_color.default_value = color
        roughness = principled.inputs.get("Roughness")
        if roughness is not None:
            roughness.default_value = 0.5
    return material


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


def _configure_label(label, text, location, rotation, size, in_front, material):
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.align_y = "CENTER"
    label.data.size = size
    label.location = location
    label.rotation_mode = "XYZ"
    label.rotation_euler = rotation
    label.data.materials.clear()
    label.data.materials.append(material)
    label.hide_render = False
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


def _update_lattice(cage, bounds, divisions, material):
    vertices, edges = cage_geometry(_bounds_pair(bounds), divisions)
    curve = cage.data
    curve.dimensions = "3D"
    curve.resolution_u = 1
    extent = max(bounds.dimensions)
    curve.bevel_depth = min(max(extent * 0.002, 0.001), 0.02)
    curve.bevel_resolution = 2
    for spline in tuple(curve.splines):
        curve.splines.remove(spline)
    for start_id, end_id in edges:
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        for point, vertex_id in zip(spline.points, (start_id, end_id)):
            x, y, z = vertices[vertex_id]
            point.co = (x, y, z, 1.0)
    curve.materials.clear()
    curve.materials.append(material)
    curve.update_tag()


def _stored_sources(cage):
    raw_names = cage.get(_SOURCES_KEY)
    if raw_names:
        try:
            names = json.loads(raw_names)
        except (TypeError, ValueError):
            names = []
        sources = [bpy.data.objects.get(name) for name in names]
        if names and all(source is not None for source in sources):
            return sources
        return []
    legacy_name = cage.get(_SOURCE_KEY)
    legacy_source = bpy.data.objects.get(legacy_name) if legacy_name else None
    return [legacy_source] if legacy_source is not None else []


def _source_roots(context, cage=None):
    selected = [obj for obj in context.selected_objects if not _is_cage_object(obj)]
    if selected:
        return selected
    if cage is not None:
        return _stored_sources(cage)
    active = context.view_layer.objects.active
    return [active] if active is not None and not _is_cage_object(active) else []


def _hierarchy_target(sources):
    """Only a single selected root with descendants selects hierarchy placement."""
    if len(sources) == 1 and sources[0].children:
        return sources[0]
    return None


def _hide_extra_labels(visible_dimensions):
    for obj in bpy.data.objects:
        if not _is_cage_object(obj) or obj.get(_KIND_KEY) == _KIND_CAGE:
            continue
        if obj.get(_DIMENSION_KEY) not in visible_dimensions:
            obj.hide_set(True)
            obj.hide_render = True


def create_measurement_cage(
    context,
    *,
    envelope_increment=1.0,
    divisions=(1, 1, 1),
    show_dimensions=True,
    in_front=True,
):
    """Create or update the single BlendMax measurement cage for the selection."""
    active = context.view_layer.objects.active
    active_cage = active if active is not None and _is_cage_object(active) else None
    sources = _source_roots(context, active_cage)
    if not sources:
        raise ValueError("Select one or more objects with mesh geometry first.")

    bounds = presentation_bounds(
        sources,
        source_root=", ".join(source.name for source in sources),
    )
    if bounds is None:
        raise ValueError("The selected objects have no valid mesh geometry.")

    envelope = measurement_envelope(bounds, envelope_increment)
    hierarchy_root = _hierarchy_target(sources)
    collection = _presentation_collection(context, hierarchy_root)
    cage = _get_or_create_cage(collection)
    _reset_world_transform(cage)
    material = _get_or_create_material()
    _update_lattice(cage, envelope, divisions, material)

    cage.pop("blendmax_measurement_margin", None)
    cage[_SOURCE_KEY] = sources[0].name
    cage[_SOURCES_KEY] = json.dumps([source.name for source in sources])
    cage["blendmax_measurement_envelope_increment"] = envelope.increment
    cage["blendmax_measurement_divisions"] = tuple(int(value) for value in divisions)
    cage["blendmax_measurement_dimensions"] = envelope.dimensions
    cage["blendmax_measurement_asset_dimensions"] = tuple(
        float(value) for value in bounds.dimensions
    )
    cage["blendmax_measurement_center"] = tuple(
        (lower + upper) * 0.5
        for lower, upper in zip(envelope.minimum, envelope.maximum)
    )
    cage.hide_render = False
    cage.show_in_front = bool(in_front)
    cage.display_type = "SOLID"
    cage.hide_set(False)

    visible_dimensions = set()
    if show_dimensions:
        width, depth, height = envelope.dimensions
        extent = max(max(envelope.dimensions), 1e-3)
        offset = max(extent * 0.025, 0.01)
        x0, y0, z0 = envelope.minimum
        x1, y1, z1 = envelope.maximum
        label_specs = (
            ("Width", "W {0}".format(_format_dimension(width)), ((x0 + x1) * 0.5, y0 - offset, z1 + offset), (math.pi / 2.0, 0.0, 0.0)),
            ("Depth", "D {0}".format(_format_dimension(depth)), (x1 + offset, (y0 + y1) * 0.5, z1 + offset), (0.0, math.pi / 2.0, 0.0)),
            ("Height", "H {0}".format(_format_dimension(height)), (x0 - offset, y0 - offset, (z0 + z1) * 0.5), (math.pi / 2.0, 0.0, 0.0)),
        )
        size = min(max(extent * 0.06, 0.02), 0.5)
        for dimension_name, text, location, rotation in label_specs:
            label = _get_or_create_label(collection, dimension_name)
            _reset_world_transform(label)
            _configure_label(label, text, location, rotation, size, in_front, material)
            visible_dimensions.add(dimension_name)
    _hide_extra_labels(visible_dimensions)

    for obj in context.selected_objects:
        obj.select_set(False)
    for source in sources:
        source.select_set(True)
    context.view_layer.objects.active = sources[0]
    return cage, envelope


def remove_measurement_cage(context=None) -> int:
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
    for material in tuple(bpy.data.materials):
        if (
            material.get(_MATERIAL_KEY) == _MATERIAL_VALUE
            and getattr(material, "users", 0) == 0
        ):
            bpy.data.materials.remove(material)
    collection = next(
        (
            item
            for item in bpy.data.collections
            if item.get(_COLLECTION_KEY) == _COLLECTION_VALUE
        ),
        None,
    )
    if collection is not None and not collection.objects and not collection.children:
        _unlink_collection_from_parents(
            collection,
            scene_collection=(context.scene.collection if context is not None else None),
        )
        bpy.data.collections.remove(collection)
    return removed
