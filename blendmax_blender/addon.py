"""Blender operator and File > Import menu registration."""

from __future__ import annotations

import os
import sys
import textwrap
import time

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import restart_notice
from .errors import BlendMaxImportError
from .importer import import_blendmax
from .models import ImportSummary


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


def _enable_console_colors() -> bool:
    """Enable ANSI colors when Blender's System Console supports them."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    stdout = getattr(sys, "stdout", None)
    if stdout is not None and hasattr(stdout, "isatty") and not stdout.isatty():
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


def _ensure_utf8_stdout() -> None:
    """Best-effort UTF-8 console so summary icons render on Windows."""
    global _STDOUT_UTF8_CONFIGURED
    if _STDOUT_UTF8_CONFIGURED:
        return
    _STDOUT_UTF8_CONFIGURED = True
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except (AttributeError, OSError):
            pass
    stdout = getattr(sys, "stdout", None)
    reconfigure = getattr(stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, TypeError):
            pass


def _stdout_encoding() -> str:
    return getattr(sys.stdout, "encoding", None) or "utf-8"


def _can_encode(text: str) -> bool:
    try:
        text.encode(_stdout_encoding())
        return True
    except LookupError:
        return True
    except UnicodeEncodeError:
        return False


def _icon(name: str) -> str:
    preferred, fallback = _ICONS[name]
    return preferred if _can_encode(preferred) else fallback


def _console_color(text: str, code: str) -> str:
    if not _enable_console_colors():
        return text
    return "\x1b[{0}m{1}\x1b[0m".format(code, text)


def _print_wrapped_items(items, heading: str, color_code: str) -> None:
    print(_console_color(heading, color_code))
    print("-" * _SUMMARY_WIDTH)
    wrap_width = max(20, _DETAIL_WIDTH - 2)
    for item in items:
        lines = textwrap.wrap(
            str(item),
            width=wrap_width,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        print(_console_color("- " + lines[0], color_code))
        for line in lines[1:]:
            print(_console_color("  " + line, color_code))
    print()


def _print_import_summary(summary: ImportSummary, elapsed_seconds: float) -> None:
    """Print the detailed import report to Blender's System Console."""
    _ensure_utf8_stdout()
    separator = "=" * _SUMMARY_WIDTH
    warning_count = len(summary.warnings)

    print("\n" + separator)
    print(_console_color("                 BlendMax Import Summary", "96"))
    print(separator)
    print()
    print("Asset       : {0}".format(summary.asset_name))
    print("{0} Objects   : {1}".format(_icon("objects"), summary.object_count))
    print("{0} Materials : {1}".format(_icon("materials"), summary.material_count))
    print("{0} Textures  : {1}".format(_icon("textures"), summary.image_count))
    warning_line = "{0} Warnings  : {1}".format(_icon("warnings"), warning_count)
    print(_console_color(warning_line, "93" if warning_count else "92"))
    print("{0} Notes     : {1}".format(_icon("notes"), len(summary.notes)))
    print("{0} Time      : {1:.2f} s".format(_icon("time"), elapsed_seconds))
    print()

    if summary.warnings:
        _print_wrapped_items(summary.warnings, "[!] Warnings", "93")
    if summary.notes:
        _print_wrapped_items(summary.notes, "[i] Compatibility Notes", "96")

    if warning_count:
        print(_console_color(
            "[!] Import completed with {0} warning(s).".format(warning_count),
            "93",
        ))
    else:
        print(_console_color("[OK] Import completed successfully.", "92"))
    print(separator)


class BLENDMAX_OT_create_measurement_cage(bpy.types.Operator):
    """Create or update the renderable BlendMax measurement cage."""

    bl_idname = "blendmax.create_measurement_cage"
    bl_label = "Create Measurement Cage"
    bl_description = (
        "Create or update a renderable measurement lattice around the selected "
        "objects and their descendants"
    )
    bl_options = {"REGISTER", "UNDO"}

    envelope_increment: bpy.props.FloatProperty(
        name="Envelope Increment",
        description="Round each cage dimension up to this world-space increment",
        default=1.0,
        min=0.000001,
        soft_max=10.0,
        subtype="DISTANCE",
    )
    divisions_x: bpy.props.IntProperty(
        name="X Divisions",
        description="Segments along X; 0 chooses about 1 m grid cells",
        default=0,
        min=0,
        max=100,
    )
    divisions_y: bpy.props.IntProperty(
        name="Y Divisions",
        description="Segments along Y; 0 chooses about 1 m grid cells",
        default=0,
        min=0,
        max=100,
    )
    divisions_z: bpy.props.IntProperty(
        name="Z Divisions",
        description="Segments along Z; 0 chooses about 1 m grid cells",
        default=0,
        min=0,
        max=100,
    )
    in_front: bpy.props.BoolProperty(
        name="In Front",
        description="Keep the cage visible through scene geometry",
        default=False,
    )

    def execute(self, context):
        from .blender_presentation import create_measurement_cage

        try:
            _cage, envelope = create_measurement_cage(
                context,
                envelope_increment=self.envelope_increment,
                divisions=(self.divisions_x, self.divisions_y, self.divisions_z),
                in_front=self.in_front,
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            "Measurement Cage: W {0:.3f} m, D {1:.3f} m, H {2:.3f} m.".format(
                *envelope.dimensions
            ),
        )
        return {"FINISHED"}


class BLENDMAX_OT_remove_measurement_cage(bpy.types.Operator):
    """Remove the BlendMax measurement cage."""

    bl_idname = "blendmax.remove_measurement_cage"
    bl_label = "Remove Measurement Cage"
    bl_description = (
        "Remove the BlendMax measurement cage and its supporting datablocks"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .blender_presentation import remove_measurement_cage

        removed = remove_measurement_cage(context)
        if removed:
            self.report({"INFO"}, "Measurement Cage removed.")
        else:
            self.report({"INFO"}, "No BlendMax measurement cage to remove.")
        return {"FINISHED"}


class BLENDMAX_OT_restart_notice_later(bpy.types.Operator):
    """Keep working; the restart notice stays in the add-on preferences."""

    bl_idname = "blendmax.restart_notice_later"
    bl_label = "Later"
    bl_options = {"INTERNAL"}

    def execute(self, _context):
        return {"FINISHED"}


class BLENDMAX_OT_restart_notice_popup(bpy.types.Operator):
    """BlendMax was updated while this session was running."""

    bl_idname = "blendmax.restart_notice_popup"
    bl_label = "BlendMax Was Updated"
    # WindowManager.invoke_props_popup requires both REGISTER and UNDO on the
    # operator; without them Blender refuses to show the popup with an
    # "incorrect invoke function" error. Same option set as BlenderKit's
    # post-update report popup.
    bl_options = {"REGISTER", "INTERNAL", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_popup(self, event)

    def execute(self, _context):
        return {"FINISHED"}

    def draw(self, _context):
        layout = self.layout
        heading = layout.row()
        heading.alert = True
        heading.label(text="BlendMax was updated.", icon="ERROR")
        layout.label(text="Restart Blender to load the new code.")
        layout.separator()
        layout.label(
            text="Installed BlendMax version: {0}".format(
                restart_notice.disk_version()
            )
        )
        layout.label(
            text="Running BlendMax version: {0}".format(
                restart_notice.running_version()
            )
        )
        layout.separator()
        buttons = layout.row()
        buttons.operator(
            "wm.quit_blender", text="Restart Blender", icon="ERROR"
        )
        buttons.operator(
            BLENDMAX_OT_restart_notice_later.bl_idname, text="Later"
        )


class BLENDMAX_MT_presentation(bpy.types.Menu):
    bl_idname = "BLENDMAX_MT_presentation"
    bl_label = "Presentation"

    def draw(self, _context):
        self.layout.operator(
            BLENDMAX_OT_create_measurement_cage.bl_idname,
            text="Create Measurement Cage",
            icon="CUBE",
        )
        self.layout.operator(
            BLENDMAX_OT_remove_measurement_cage.bl_idname,
            text="Remove Measurement Cage",
            icon="TRASH",
        )


class BLENDMAX_MT_main(bpy.types.Menu):
    bl_idname = "BLENDMAX_MT_main"
    bl_label = "BlendMax"

    def draw(self, _context):
        self.layout.menu(
            BLENDMAX_MT_presentation.bl_idname,
            icon="SCENE_DATA",
        )


def _menu_blendmax(self, _context) -> None:
    self.layout.menu(BLENDMAX_MT_main.bl_idname)


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


class BLENDMAX_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, _context):
        if not restart_notice.draw_notice(self.layout):
            self.layout.label(
                text=(
                    "Restart Blender after installing or updating BlendMax "
                    "to load the new code."
                )
            )


def _menu_import(self, _context) -> None:
    self.layout.operator(
        BLENDMAX_OT_import_asset.bl_idname,
        text="BlendMax Asset (.blendmax)",
    )


_CLASSES = (
    BLENDMAX_Preferences,
    BLENDMAX_OT_import_asset,
    BLENDMAX_OT_create_measurement_cage,
    BLENDMAX_OT_remove_measurement_cage,
    BLENDMAX_OT_restart_notice_popup,
    BLENDMAX_OT_restart_notice_later,
    BLENDMAX_MT_presentation,
    BLENDMAX_MT_main,
)


def register() -> None:
    for item in _CLASSES:
        bpy.utils.register_class(item)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)
    bpy.types.TOPBAR_MT_editor_menus.append(_menu_blendmax)
    restart_notice.register()


def unregister() -> None:
    restart_notice.unregister()
    bpy.types.TOPBAR_MT_editor_menus.remove(_menu_blendmax)
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for item in reversed(_CLASSES):
        bpy.utils.unregister_class(item)
