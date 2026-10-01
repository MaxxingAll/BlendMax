"""Show when the installed BlendMax version differs from the loaded version."""

from __future__ import annotations

import tomllib
from pathlib import Path

import bpy


_MANIFEST = Path(__file__).resolve().parent / "blender_manifest.toml"
_NAMESPACE_KEY = "blendmax.running_version"
_POLL_SECONDS = 5.0

_last_mtime = None
_disk_version = None
_needed = False


def _read_manifest_version():
    """Return the manifest version, or None while the file is unavailable."""
    try:
        with _MANIFEST.open("rb") as manifest_file:
            version = tomllib.load(manifest_file).get("version")
    except Exception:
        return None
    return version if isinstance(version, str) and version else None


def running_version():
    """Return the BlendMax version captured for this Blender process."""
    return bpy.app.driver_namespace.get(_NAMESPACE_KEY)


def disk_version():
    """Return the last valid version read from the installed manifest."""
    return _disk_version


def restart_needed():
    """Return the cached restart state without touching the filesystem."""
    return _needed


def _tag_redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        pass


def _poll():
    global _last_mtime, _disk_version, _needed

    try:
        mtime = _MANIFEST.stat().st_mtime_ns
    except OSError:
        # Keep the last good state while the extension files are being replaced.
        return _POLL_SECONDS

    if mtime != _last_mtime:
        disk = _read_manifest_version()
        if disk is not None:
            _last_mtime = mtime
            changed = disk != _disk_version
            _disk_version = disk

            running = running_version()
            needed = running is not None and disk != running
            changed = changed or needed != _needed
            _needed = needed

            if changed:
                _tag_redraw()

    return _POLL_SECONDS


def draw_notice(layout):
    """Draw the cached restart action; this function performs no file I/O."""
    if not _needed:
        return False

    box = layout.box()
    column = box.column()
    row = column.row()
    row.alert = True
    row.operator("wm.quit_blender", text="Restart Blender", icon="ERROR")
    column.label(text="Installed BlendMax version: {0}".format(_disk_version))
    column.label(text="Running BlendMax version: {0}".format(running_version()))
    return True


def register():
    global _last_mtime, _disk_version, _needed

    _last_mtime = None
    _disk_version = None
    _needed = False

    namespace = bpy.app.driver_namespace
    if namespace.get(_NAMESPACE_KEY) is None:
        version = _read_manifest_version()
        if version is not None:
            namespace[_NAMESPACE_KEY] = version

    timers = bpy.app.timers
    if not timers.is_registered(_poll):
        timers.register(_poll, first_interval=0.0, persistent=True)


def unregister():
    timers = bpy.app.timers
    if timers.is_registered(_poll):
        timers.unregister(_poll)
