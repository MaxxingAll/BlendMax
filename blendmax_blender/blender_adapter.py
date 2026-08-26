"""Small Blender API boundary for the BlendMax importer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import bpy
from mathutils import Vector

from .blender_materials import MaterialBuilder
from .errors import BlendMaxImportError
from .manifest import ManifestIndex
from .models import ImportSummary, ObjectRecord, PackageContents
from .placement import (
    bounds_from_points,
    grounded_anchor,
    hierarchy_bounds,
    merge_bounds,
)


_BLENDER_SUFFIX = re.compile(r"\.\d{3,}$")


class _DataSnapshot:
    """Remove data created during a failed import."""

    def __init__(self):
        self.objects = set(bpy.data.objects)
        self.meshes = set(bpy.data.meshes)
        self.materials = set(bpy.data.materials)
        self.images = set(bpy.data.images)
        self.texts = set(bpy.data.texts)
        self.collections = set(bpy.data.collections)

    def rollback(self) -> None:
        for item in tuple(set(bpy.data.objects) - self.objects):
            bpy.data.objects.remove(item, do_unlink=True)
        for item in tuple(set(bpy.data.meshes) - self.meshes):
            if item.users == 0:
                bpy.data.meshes.remove(item)
        for item in tuple(set(bpy.data.materials) - self.materials):
            bpy.data.materials.remove(item, do_unlink=True)
        for item in tuple(set(bpy.data.images) - self.images):
            bpy.data.images.remove(item, do_unlink=True)
        for item in tuple(set(bpy.data.texts) - self.texts):
            bpy.data.texts.remove(item)
        for item in tuple(set(bpy.data.collections) - self.collections):
            bpy.data.collections.remove(item, do_unlink=True)


def _operator_properties(operator) -> Optional[Set[str]]:
    try:
        return {
            item.identifier
            for item in operator.get_rna_type().properties
            if item.identifier != "rna_type"
        }
    except (AttributeError, RuntimeError):
        return None


def _call_supported(
    operator,
    candidates: Dict[str, object],
    supported: Optional[Set[str]] = None,
):
    supported = supported if supported is not None else _operator_properties(operator)
    if supported is None:
        raise BlendMaxImportError("The requested Blender import operator is unavailable.")
    return operator(**{key: value for key, value in candidates.items() if key in supported})


def _import_fbx(path: Path):
    new_operator = getattr(getattr(bpy.ops, "wm", None), "fbx_import", None)
    new_properties = _operator_properties(new_operator) if new_operator is not None else None
    if new_operator is not None and new_properties is not None:
        return _call_supported(
            new_operator,
            {
                "filepath": str(path),
                "import_meshes": True,
                "import_materials": True,
                "import_cameras": False,
                "import_lights": False,
                "import_animation": False,
                "use_anim": False,
            },
            supported=new_properties,
        )

    legacy_operator = getattr(getattr(bpy.ops, "import_scene", None), "fbx", None)
    if legacy_operator is None:
        raise BlendMaxImportError(
            "No Blender FBX importer is available. Enable Blender's FBX import support."
        )
    return _call_supported(
        legacy_operator,
        {
            "filepath": str(path),
            "use_custom_normals": True,
            "use_image_search": False,
            "use_anim": False,
        },
    )


def _leaf_name(name: str) -> str:
    return str(name).rsplit("::", 1)[-1]


def _name_matches(blender_name: str, fbx_name: str) -> bool:
    leaf = _leaf_name(blender_name)
    return leaf == fbx_name or _BLENDER_SUFFIX.sub("", leaf) == fbx_name


def _link_only_to(obj, collection) -> None:
    if collection not in obj.users_collection:
        collection.objects.link(obj)
    for current in tuple(obj.users_collection):
        if current != collection:
            current.objects.unlink(obj)


def _set_parent_preserve_world(child, parent) -> None:
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def _mesh_world_bounds(obj):
    if obj.type != "MESH" or obj.data is None or not len(obj.data.vertices):
        return None
    return bounds_from_points(
        tuple(obj.matrix_world @ Vector(corner)) for corner in obj.bound_box
    )


class BlenderAdapter:
    def __init__(self, context):
        self.context = context

    def import_package(
        self,
        package: PackageContents,
        apply_recommended_scale: bool = True,
    ) -> ImportSummary:
        snapshot = _DataSnapshot()
        warnings: List[str] = list(package.manifest.warnings)
        try:
            return self._import(package, snapshot, warnings, apply_recommended_scale)
        except BlendMaxImportError:
            snapshot.rollback()
            raise
        except Exception as exc:
            snapshot.rollback()
            raise BlendMaxImportError("BlendMax import failed: {0}".format(exc)) from exc

    def _import(
        self,
        package: PackageContents,
        snapshot: _DataSnapshot,
        warnings: List[str],
        apply_recommended_scale: bool,
    ) -> ImportSummary:
        if self.context.object is not None and self.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        before_objects = set(bpy.data.objects)
        before_materials = set(bpy.data.materials)
        before_images = set(bpy.data.images)
        result = _import_fbx(package.geometry_path)
        if "FINISHED" not in result:
            raise BlendMaxImportError("Blender's FBX importer did not finish successfully.")

        imported = list(set(bpy.data.objects) - before_objects)
        if not imported:
            raise BlendMaxImportError("The FBX importer created no objects.")
        fbx_materials = set(bpy.data.materials) - before_materials
        fbx_images = set(bpy.data.images) - before_images

        manifest = package.manifest
        index = ManifestIndex(manifest)
        collection = bpy.data.collections.new(manifest.asset_name)
        self.context.scene.collection.children.link(collection)
        collection["blendmax_schema_version"] = manifest.schema_version
        collection["blendmax_source_package"] = str(package.source_path)
        manifest_text = bpy.data.texts.new(
            name="{0} - BlendMax manifest.json".format(manifest.asset_name)
        )
        manifest_text.write(
            json.dumps(manifest.raw, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        collection["blendmax_manifest_text"] = manifest_text.name
        for obj in imported:
            _link_only_to(obj, collection)

        generated_group_heads: Set[str] = set()
        mapped, undeclared = self._map_objects(
            imported,
            manifest.objects,
            collection,
            warnings,
            generated_group_heads,
        )
        undeclared_set = set(undeclared)
        imported = [obj for obj in imported if obj not in undeclared_set]
        self._discard_undeclared_fbx_objects(undeclared)
        self._rebase_imported_roots(imported, mapped)
        self.context.view_layer.update()
        self._position_generated_group_heads(
            mapped,
            manifest.objects,
            generated_group_heads,
        )
        self._restore_hierarchy(mapped, manifest.objects, warnings)
        self.context.view_layer.update()
        controller = self._create_controller(
            collection,
            package,
            mapped,
            apply_recommended_scale,
            manifest_text.name,
        )

        for obj in mapped.values():
            if obj.type == "MESH":
                obj.data.materials.clear()

        builder = MaterialBuilder(index, package.root, warnings)
        for assignment in manifest.assignments:
            obj = mapped.get(assignment.object_id)
            if obj is None:
                warnings.append(
                    "Material assignment skipped because object {0} was not imported.".format(
                        assignment.object_id
                    )
                )
                continue
            if obj.type != "MESH":
                continue
            for material in builder.materials_for_assignment(assignment.material_ref):
                obj.data.materials.append(material)

        self._discard_fbx_material_data(fbx_materials, fbx_images, builder)
        self._select_result(imported, controller)

        mesh_count = sum(1 for obj in mapped.values() if obj.type == "MESH")
        return ImportSummary(
            asset_name=manifest.asset_name,
            object_count=mesh_count,
            material_count=len(builder.created_materials),
            image_count=len(builder.created_images),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _map_objects(
        imported: Iterable[object],
        records: Iterable[ObjectRecord],
        collection,
        warnings: List[str],
        generated_group_heads: Set[str],
    ) -> Tuple[Dict[str, object], Tuple[object, ...]]:
        available = list(imported)
        mapped: Dict[str, object] = {}
        for record in records:
            match = next(
                (obj for obj in available if _name_matches(obj.name, record.fbx_name)),
                None,
            )
            if match is not None:
                available.remove(match)
            elif record.is_group_head:
                match = bpy.data.objects.new(record.fbx_name, None)
                match.empty_display_type = "PLAIN_AXES"
                collection.objects.link(match)
                generated_group_heads.add(record.object_id)
            else:
                warnings.append(
                    "Manifest object {0} was not found in geometry.fbx.".format(
                        record.original_name
                    )
                )
                continue

            match["blendmax_object_id"] = record.object_id
            match["blendmax_fbx_name"] = record.fbx_name
            match["blendmax_node_type"] = record.node_type
            match.name = record.original_name or record.fbx_name
            mapped[record.object_id] = match

        return mapped, tuple(available)

    @staticmethod
    def _discard_undeclared_fbx_objects(objects: Iterable[object]) -> None:
        data_collection_names = {
            "MESH": "meshes",
            "CURVE": "curves",
            "SURFACE": "curves",
            "FONT": "curves",
            "ARMATURE": "armatures",
            "CAMERA": "cameras",
            "LIGHT": "lights",
        }
        for obj in tuple(objects):
            data = getattr(obj, "data", None)
            collection_name = data_collection_names.get(getattr(obj, "type", ""))
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is None or collection_name is None or getattr(data, "users", 0) != 0:
                continue
            getattr(bpy.data, collection_name).remove(data)

    @staticmethod
    def _rebase_imported_roots(
        imported: Iterable[object],
        mapped: Dict[str, object],
    ) -> None:
        actual_bounds = []
        for obj in mapped.values():
            bounds = _mesh_world_bounds(obj)
            if bounds is not None:
                actual_bounds.append(bounds)

        bounds = merge_bounds(actual_bounds)
        if bounds is None:
            return

        anchor = Vector(grounded_anchor(bounds))
        imported_objects = set(imported)
        for obj in imported_objects:
            if obj.parent in imported_objects:
                continue
            world = obj.matrix_world.copy()
            world.translation -= anchor
            obj.matrix_world = world

    @staticmethod
    def _position_generated_group_heads(
        mapped: Dict[str, object],
        records: Iterable[ObjectRecord],
        generated_group_heads: Set[str],
    ) -> None:
        if not generated_group_heads:
            return

        mesh_bounds = {}
        for object_id, obj in mapped.items():
            bounds = _mesh_world_bounds(obj)
            if bounds is not None:
                mesh_bounds[object_id] = bounds

        branches = hierarchy_bounds(
            {record.object_id: record.parent_id for record in records},
            mesh_bounds,
        )
        for object_id in generated_group_heads:
            bounds = branches.get(object_id)
            if bounds is not None:
                mapped[object_id].location = grounded_anchor(bounds)

    @staticmethod
    def _restore_hierarchy(
        mapped: Dict[str, object],
        records: Iterable[ObjectRecord],
        warnings: List[str],
    ) -> None:
        for record in records:
            child = mapped.get(record.object_id)
            if child is None or not record.parent_id:
                continue
            parent = mapped.get(record.parent_id)
            if parent is None:
                warnings.append(
                    "Parent {0} for {1} is missing.".format(
                        record.parent_id, record.original_name
                    )
                )
                continue
            _set_parent_preserve_world(child, parent)

    @staticmethod
    def _create_controller(
        collection,
        package: PackageContents,
        mapped: Dict[str, object],
        apply_recommended_scale: bool,
        manifest_text_name: str,
    ):
        manifest = package.manifest
        controller = bpy.data.objects.new("{0} [BlendMax]".format(manifest.asset_name), None)
        controller.empty_display_type = "CUBE"
        actual_bounds = []
        for obj in mapped.values():
            bounds = _mesh_world_bounds(obj)
            if bounds is not None:
                actual_bounds.append(bounds)
        minimum, maximum = merge_bounds(actual_bounds) or (
            manifest.bounds_minimum_m,
            manifest.bounds_maximum_m,
        )
        dimensions = tuple(
            upper - lower for lower, upper in zip(minimum, maximum)
        )
        controller.empty_display_size = max(0.01, max(dimensions) * 0.08)
        controller.location = (0.0, 0.0, 0.0)
        controller["blendmax_asset"] = True
        controller["blendmax_schema_version"] = manifest.schema_version
        controller["blendmax_source_package"] = str(package.source_path)
        controller["blendmax_manifest_text"] = manifest_text_name
        controller["blendmax_recommended_scale"] = manifest.recommended_scale
        collection.objects.link(controller)

        roots = []
        records_by_id = {item.object_id: item for item in manifest.objects}
        for object_id, obj in mapped.items():
            record = records_by_id[object_id]
            if not record.parent_id or record.parent_id not in mapped:
                roots.append(obj)
        for root in roots:
            _set_parent_preserve_world(root, controller)
        for obj in tuple(collection.objects):
            if obj != controller and obj.parent is None:
                _set_parent_preserve_world(obj, controller)

        if apply_recommended_scale and manifest.recommended_scale != 1.0:
            scale = manifest.recommended_scale
            controller.scale = (scale, scale, scale)
        return controller

    @staticmethod
    def _discard_fbx_material_data(fbx_materials, fbx_images, builder) -> None:
        built_materials = set(builder.created_materials)
        built_images = set(builder.created_images)
        for material in tuple(fbx_materials):
            if material not in built_materials and material.users == 0:
                bpy.data.materials.remove(material)
        for image in tuple(fbx_images):
            if image not in built_images and image.users == 0:
                bpy.data.images.remove(image)

    @staticmethod
    def _select_result(imported: Iterable[object], controller) -> None:
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in imported:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        controller.select_set(True)
        bpy.context.view_layer.objects.active = controller
