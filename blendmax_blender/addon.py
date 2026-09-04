"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import json
import textwrap

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .diagnostics import build_import_summary_view
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


def _show_import_summary(summary_json: str):
    """Open the completion popup after the modal File Browser has closed."""
    try:
        bpy.ops.blendmax.import_summary(
            "INVOKE_DEFAULT",
            summary_json=summary_json,
        )
    except RuntimeError:
        return 0.1
    return None


class BLENDMAX_OT_import_summary(bpy.types.Operator):
    bl_idname = "blendmax.import_summary"
    bl_label = "BlendMax Import Complete"
    bl_description = "Show the result of the completed BlendMax import"

    summary_json: StringProperty(options={"HIDDEN"})

    def _summary(self):
        try:
            value = json.loads(self.summary_json)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, _context):
        layout = self.layout
        summary = self._summary()
        asset_name = str(summary.get("asset_name") or "BlendMax Asset")
        warnings = tuple(summary.get("warnings") or ())
        notes = tuple(summary.get("notes") or ())

        layout.label(text=asset_name, icon="OBJECT_DATA")

        grid = layout.grid_flow(columns=2, even_columns=True, align=True)
        grid.label(text="Objects")
        grid.label(text=str(summary.get("object_count", 0)))
        grid.label(text="Materials")
        grid.label(text=str(summary.get("material_count", 0)))
        grid.label(text="Textures")
        grid.label(text=str(summary.get("image_count", 0)))
        grid.label(text="Warnings")
        grid.label(text=str(len(warnings)), icon="ERROR" if warnings else "CHECKMARK")
        grid.label(text="Notes")
        grid.label(text=str(len(notes)), icon="INFO")

        def draw_wrapped(parent, text, icon):
            lines = textwrap.wrap(text, width=65)
            if not lines:
                return
            parent.label(text=lines[0], icon=icon)
            for line in lines[1:]:
                parent.label(text=line, icon="BLANK1")

        if warnings:
            box = layout.box()
            box.label(text="Warnings", icon="ERROR")
            for warning in warnings:
                draw_wrapped(box, str(warning), icon="ERROR")

        if notes:
            box = layout.box()
            box.label(text="Compatibility Notes", icon="INFO")
            for note in notes:
                draw_wrapped(box, str(note), icon="INFO")

        if not warnings and not notes:
            layout.separator()
            layout.label(
                text="Import completed without warnings or compatibility notes.",
                icon="CHECKMARK",
            )

    def execute(self, _context):
        return {"FINISHED"}


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

        view = build_import_summary_view(summary)
        summary_json = json.dumps(view, ensure_ascii=False)
        bpy.app.timers.register(
            lambda: _show_import_summary(summary_json),
            first_interval=0.1,
        )
        return {"FINISHED"}


def _menu_import(self, _context) -> None:
    self.layout.operator(
        BLENDMAX_OT_import_asset.bl_idname,
        text="BlendMax Asset (.blendmax)",
    )


_CLASSES = (
    BLENDMAX_Preferences,
    BLENDMAX_OT_restart_blender_notice,
    BLENDMAX_OT_import_summary,
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
