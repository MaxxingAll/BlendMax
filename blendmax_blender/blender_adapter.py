"""Orchestration for importing a .blendmax package into Blender.

This module owns the import transaction: it snapshots Blender data, runs the
import phases in order, and rolls back every data-block created by an import
that fails. The phase sequence in :meth:`BlenderAdapter._import` is the
authoritative description of how an import proceeds.

The work each phase performs lives in focused sibling modules:

``blender_api``
    Blender operator compatibility and the FBX import call itself.
``blender_scene``
    Object matching, group-head handling, hierarchy restoration, rebasing,
    bounds and controller creation.
``blender_materials``
    Material graph translation (``MaterialBuilder``) and the FBX material/image
    slot and data handling.

Nothing in those modules imports this one.
"""

from __future__ import annotations

import json
from typing import List, Set

import bpy

from .blender_api import _import_fbx
from .blender_materials import (
    MaterialBuilder,
    _discard_fbx_material_data,
    _replace_material_slots,
    _reserve_fbx_material_names,
)
from .blender_scene import (
    _create_controller,
    _discard_undeclared_fbx_objects,
    _link_only_to,
    _map_objects,
    _position_generated_group_heads,
    _rebase_imported_roots,
    _select_result,
)
from .errors import BlendMaxImportError
from .manifest import ManifestIndex
from .models import ImportSummary, PackageContents


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
        _reserve_fbx_material_names(fbx_materials)

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
        mapped, undeclared = _map_objects(
            imported,
            manifest.objects,
            collection,
            warnings,
            generated_group_heads,
        )
        undeclared_set = set(undeclared)
        imported = [obj for obj in imported if obj not in undeclared_set]
        _discard_undeclared_fbx_objects(undeclared)
        _rebase_imported_roots(imported, mapped)
        self.context.view_layer.update()
        _position_generated_group_heads(
            mapped,
            manifest.objects,
            generated_group_heads,
        )
        controller = _create_controller(
            collection,
            package,
            mapped,
            apply_recommended_scale,
            manifest_text.name,
            warnings,
            generated_group_heads,
        )

        # Meshes with no manifest assignment at all get no BlendMax-authored
        # materials; their raw FBX materials are dropped like before. Meshes
        # that *do* have an assignment must NOT go through materials.clear():
        # clearing removes the mesh's material_index attribute as a Blender
        # side effect, permanently destroying the per-face slot mapping the
        # FBX importer just established. Those meshes are rebuilt in place
        # instead (see _replace_material_slots).
        assigned_object_ids = {item.object_id for item in manifest.assignments}
        for object_id, obj in mapped.items():
            if obj.type == "MESH" and object_id not in assigned_object_ids:
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
            materials = builder.materials_for_assignment(assignment.material_ref)
            _replace_material_slots(obj, materials, warnings)

        _discard_fbx_material_data(fbx_materials, fbx_images, builder)
        _select_result(imported, controller)

        mesh_count = sum(1 for obj in mapped.values() if obj.type == "MESH")
        return ImportSummary(
            asset_name=manifest.asset_name,
            object_count=mesh_count,
            material_count=len(builder.created_materials),
            image_count=len(builder.created_images),
            warnings=tuple(warnings),
        )
