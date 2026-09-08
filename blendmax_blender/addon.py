"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import os
import sys
import textwrap
import time
import traceback

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .errors import BlendMaxImportError
from .importer import import_blendmax
from .models import ImportSummary
from .restart_notice import (
    mark_hot_reload_failed,
    mark_hot_reload_pending,
    restart_notice_required,
)


_RESTART_NOTICE_REQUIRED = False
_RELOAD_PENDING = False
_SUMMARY_WIDTH = 60
_DETAIL_WIDTH = 72
_STDOUT_UTF8_CONFIGURED = False

# Preferred glyphs first; ASCII fallbacks if the console encoding cannot
# represent them (common on older Windows / cp437 Blender consoles).
_ICONS = {
    "objects": ("❒", "[O]"),
    "materials": ("●", "[M]"),
    "textures": ("■", "[T]"),
    "warnings": ("⚠", "[!]"),
    "notes": ("✎", "[i]"),
    "time": ("⏱", "[t]"),
}


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


def _hot_reload() -> None:
    """Reload BlendMax from the installed module location after the operator returns."""
    global _RELOAD_PENDING
    module_name = __package__
    try:
        mark_hot_reload_pending(bpy)
        bpy.ops.preferences.addon_disable(module=module_name)

        for name in list(sys.modules):
            if name == module_name or name.startswith(module_name + "."):
                del sys.modules[name]

        bpy.ops.preferences.addon_enable(module=module_name)
        print("BlendMax: hot reload completed successfully.")
    except Exception as exc:
        mark_hot_reload_failed(bpy)
        print("BlendMax: hot reload failed: {0}".format(exc))
        traceback.print_exc()
    finally:
        _RELOAD_PENDING = False
    return None


class BLENDMAX_OT_hot_reload(bpy.types.Operator):
    bl_idname = "blendmax.hot_reload"
    bl_label = "Reload BlendMax"
    bl_description = "Reload the currently installed BlendMax extension copy without restarting Blender"

    def execute(self, _context):
        global _RELOAD_PENDING
        if _RELOAD_PENDING:
            self.report({"INFO"}, "BlendMax reload is already scheduled.")
            return {"FINISHED"}

        _RELOAD_PENDING = True
        bpy.app.timers.register(_hot_reload, first_interval=0.1)
        self.report({"INFO"}, "BlendMax reload scheduled.")
        return {"FINISHED"}


class BLENDMAX_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, _context):
        layout = self.layout
        if _RESTART_NOTICE_REQUIRED:
            row = layout.row()
            row.alert = True
            row.operator(BLENDMAX_OT_restart_blender_notice.bl_idname, icon="FILE_REFRESH")
        layout.operator(BLENDMAX_OT_hot_reload.bl_idname, icon="FILE_REFRESH")


class BLENDMAX_OT_import_asset(ImportHelper, bpy.types.Operator):
    bl_idname = "blendmax.import_asset"
    bl_label = "Import BlendMax Asset"
    bl_options = {"UNDO"}

    filename_ext = ".blendmax"
    filter_glob: StringProperty(default="*.blendmax", options={"HIDDEN"})

    def execute(self, context):
        start = time.perf_counter()
        self._configure_stdout()
        try:
            summary = import_blendmax(self.filepath, context.scene)
        except BlendMaxImportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, "BlendMax import failed: {0}".format(exc))
            traceback.print_exc()
            return {"CANCELLED"}

        self._print_summary(summary, time.perf_counter() - start)
        self.report({"INFO"}, "BlendMax import completed.")
        return {"FINISHED"}

    @staticmethod
    def _configure_stdout():
        global _STDOUT_UTF8_CONFIGURED
        if _STDOUT_UTF8_CONFIGURED:
            return
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        _STDOUT_UTF8_CONFIGURED = True

    @staticmethod
    def _print_summary(summary: ImportSummary, elapsed: float) -> None:
        print("\nBlendMax import summary")
        print("-" * _SUMMARY_WIDTH)
        print("Objects    {0}".format(summary.objects))
        print("Materials  {0}".format(summary.materials))
        print("Textures   {0}".format(summary.textures))
        print("Warnings   {0}".format(summary.warnings))
        print("Notes      {0}".format(summary.notes))
        print("Time       {0:.2f}s".format(elapsed))
        print("-" * _SUMMARY_WIDTH)
        for detail in summary.details:
            for line in textwrap.wrap(detail, width=_DETAIL_WIDTH) or [""]:
                print(line)


def _menu_import(self, _context):
    self.layout.operator(
        BLENDMAX_OT_import_asset.bl_idname,
        text="BlendMax Asset (.blendmax)",
    )


_CLASSES = (
    BLENDMAX_Preferences,
    BLENDMAX_OT_restart_blender_notice,
    BLENDMAX_OT_hot_reload,
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
