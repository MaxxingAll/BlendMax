"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .errors import BlendMaxImportError
from .importer import import_blendmax


class BLENDMAX_OT_import_asset(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.blendmax_asset"
    bl_label = "Import BlendMax Asset"
    bl_description = "Import a .blendmax asset exported from Autodesk 3ds Max"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".blendmax"
    filter_glob: StringProperty(default="*.blendmax", options={"HIDDEN"})
    apply_recommended_scale: BoolProperty(
        name="Apply Recommended Scale",
        description="Apply the exporter's scale recommendation for assets over 50 metres",
        default=True,
    )

    def execute(self, context):
        try:
            summary = import_blendmax(
                self.filepath,
                context=context,
                apply_recommended_scale=self.apply_recommended_scale,
            )
        except BlendMaxImportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if summary.warnings:
            self.report(
                {"WARNING"},
                "Imported {0}: {1} objects, {2} materials, {3} warning(s).".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                    len(summary.warnings),
                ),
            )
            for warning in summary.warnings:
                print("BlendMax warning: {0}".format(warning))
        else:
            self.report(
                {"INFO"},
                "Imported {0}: {1} objects and {2} materials.".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                ),
            )

        for note in summary.notes:
            print("BlendMax note: {0}".format(note))

        if summary.notes:
            self.report(
                {"INFO"},
                "BlendMax notes: {0}".format(" | ".join(summary.notes)),
            )
        return {"FINISHED"}


def _menu_import(self, _context) -> None:
    self.layout.operator(
        BLENDMAX_OT_import_asset.bl_idname,
        text="BlendMax Asset (.blendmax)",
    )


_CLASSES = (BLENDMAX_OT_import_asset,)


def register() -> None:
    for item in _CLASSES:
        bpy.utils.register_class(item)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)


def unregister() -> None:
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for item in reversed(_CLASSES):
        bpy.utils.unregister_class(item)
