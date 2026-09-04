"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .errors import BlendMaxImportError
from .importer import import_blendmax
from .restart_notice import restart_notice_required


_RESTART_NOTICE_REQUIRED = False


class BLENDMAX_OT_restart_blender_notice(bpy.types.Operator):
    bl_idname = "blendmax.restart_blender_notice"
    bl_label = "Restart Blender"
    bl_description = (
        "Restart Blender to apply recent BlendMax changes. "
        "This notice disappears automatically after Blender is restarted."
    )

    def execute(self, _context):
        self.report({"INFO"}, "Please restart Blender to apply recent BlendMax changes.")
        return {"FINISHED"}


class BLENDMAX_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, _context):
        layout = self.layout
        if _RESTART_NOTICE_REQUIRED:
            layout.operator(
                BLENDMAX_OT_restart_blender_notice.bl_idname,
                text="⚠ Restart Blender",
                icon="ERROR",
            )
        else:
            layout.label(text="BlendMax is ready to use.")


def _print_import_summary(summary) -> None:
    """Print detailed import information to Blender's System Console."""
    print("\nBlendMax Import Summary")
    print("=======================")
    print("Asset: {0}".format(summary.asset_name))
    print("Objects: {0}".format(summary.object_count))
    print("Materials: {0}".format(summary.material_count))
    print("Textures: {0}".format(summary.image_count))
    print("Warnings: {0}".format(len(summary.warnings)))
    print("Notes: {0}".format(len(summary.notes)))

    if summary.warnings:
        print("\nWarnings:")
        for warning in summary.warnings:
            print("- {0}".format(warning))

    if summary.notes:
        print("\nCompatibility Notes:")
        for note in summary.notes:
            print("- {0}".format(note))


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
                "[!] Imported {0}: {1} Objects, {2} Materials, {3} Warning(s).".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                    len(summary.warnings),
                ),
            )
        else:
            self.report(
                {"INFO"},
                "[+] Imported {0}: {1} Objects, {2} Materials, 0 Warning(s).".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                ),
            )

        _print_import_summary(summary)
        return {"FINISHED"}


def _menu_import(self, _context) -> None:
    self.layout.operator(
        BLENDMAX_OT_import_asset.bl_idname,
        text="BlendMax Asset (.blendmax)",
    )


_CLASSES = (
    BLENDMAX_Preferences,
    BLENDMAX_OT_restart_blender_notice,
    BLENDMAX_OT_import_asset,
)


def register() -> None:
    global _RESTART_NOTICE_REQUIRED
    _RESTART_NOTICE_REQUIRED = restart_notice_required(bpy)

    for item in _CLASSES:
        bpy.utils.register_class(item)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)


def unregister() -> None:
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for item in reversed(_CLASSES):
        bpy.utils.unregister_class(item)
