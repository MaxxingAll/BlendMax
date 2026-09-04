"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import os
import textwrap
import time

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .errors import BlendMaxImportError
from .importer import import_blendmax
from .restart_notice import restart_notice_required


_RESTART_NOTICE_REQUIRED = False
_SUMMARY_WIDTH = 60
_DETAIL_WIDTH = 72


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


def _enable_console_colors() -> bool:
    """Enable ANSI colors when Blender's System Console supports them."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(
            ctypes.windll.kernel32.SetConsoleMode(
                handle, mode.value | 0x0004
            )
        )
    except (AttributeError, OSError):
        return False


_CONSOLE_COLORS_ENABLED = _enable_console_colors()


def _console_color(text: str, code: str) -> str:
    if not _CONSOLE_COLORS_ENABLED:
        return text
    return "\x1b[{0}m{1}\x1b[0m".format(code, text)


def _print_import_summary(summary, elapsed_seconds: float) -> None:
    """Print the detailed import report to Blender's System Console."""
    separator = "=" * _SUMMARY_WIDTH
    section_separator = "-" * _SUMMARY_WIDTH

    print("\n" + separator)
    print(_console_color("                 BlendMax Import Summary", "96"))
    print(separator)
    print()
    print("Asset       : {0}".format(summary.asset_name))
    print("❒ Objects   : {0}".format(summary.object_count))
    print("◕ Materials : {0}".format(summary.material_count))
    print("◩ Textures  : {0}".format(summary.image_count))
    warning_count = len(summary.warnings)
    warning_line = "⚠︎ Warnings  : {0}".format(warning_count)
    print(_console_color(warning_line, "93" if warning_count else "92"))
    print("✎ Notes     : {0}".format(len(summary.notes)))
    print("⏱ Time      : {0:.2f} s".format(elapsed_seconds))
    print()

    if summary.warnings:
        print(_console_color("[!] Warnings", "93"))
        print(section_separator)
        for warning in summary.warnings:
            lines = textwrap.wrap(
                str(warning),
                width=max(20, _DETAIL_WIDTH - 2),
                break_long_words=False,
                break_on_hyphens=False,
            ) or [""]
            print(_console_color("- " + lines[0], "93"))
            for line in lines[1:]:
                print(_console_color("  " + line, "93"))
        print()

    if summary.notes:
        print(_console_color("[i] Compatibility Notes", "96"))
        print(section_separator)
        for note in summary.notes:
            lines = textwrap.wrap(
                str(note),
                width=max(20, _DETAIL_WIDTH - 2),
                break_long_words=False,
                break_on_hyphens=False,
            ) or [""]
            print(_console_color("- " + lines[0], "96"))
            for line in lines[1:]:
                print(_console_color("  " + line, "96"))
        print()

    print(_console_color("[OK] Import completed successfully.", "92"))
    print(separator)


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
        started_at = time.perf_counter()
        try:
            summary = import_blendmax(
                self.filepath,
                context=context,
                apply_recommended_scale=self.apply_recommended_scale,
            )
        except BlendMaxImportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        elapsed_seconds = time.perf_counter() - started_at

        if summary.warnings:
            self.report(
                {"WARNING"},
                "Imported {0}: {1} Objects, {2} Materials, {3} Warning(s).".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                    len(summary.warnings),
                ),
            )
        else:
            self.report(
                {"INFO"},
                "Imported {0}: {1} Objects, {2} Materials, 0 Warning(s).".format(
                    summary.asset_name,
                    summary.object_count,
                    summary.material_count,
                ),
            )

        _print_import_summary(summary, elapsed_seconds)
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
