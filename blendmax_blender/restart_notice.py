"""Restart notice for BlendMax, with BlenderKit-style persisted state.

A state file records that a different BlendMax version is installed while
older code is still running. The notice is drawn from that record, and the
record is consumed once the updated code is actually running. BlendMax ships
no updater, so a timer compares the manifest version on disk with the version
captured when this Blender process first registered the add-on.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import bpy


_MANIFEST = Path(__file__).resolve().parent / "blender_manifest.toml"
_NAMESPACE_KEY = "blendmax.running_version"
_STATE_FILENAME = "blendmax_restart_state.json"
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


def _state_path():
    """Return the persisted state file path, or None when unavailable."""
    try:
        directory = bpy.utils.user_resource("CONFIG", path="blendmax", create=True)
    except Exception:
        return None
    if not directory:
        return None
    return Path(directory) / _STATE_FILENAME


def _read_state():
    """Return the persisted notice state; unreadable content means empty."""
    path = _state_path()
    if path is None:
        return {}
    try:
        with path.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except Exception:
        return {}
    return state if isinstance(state, dict) else {}


def _write_state(just_updated, running, installed):
    """Write the persisted notice state, skipping identical content."""
    path = _state_path()
    if path is None:
        return
    state = {
        "just_updated": bool(just_updated),
        "running_version": running,
        "installed_version": installed,
    }
    try:
        if _read_state() == state:
            return
        with path.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, indent=2, sort_keys=True)
            state_file.write("\n")
    except Exception:
        # The notice still works; only the persisted record is lost.
        pass


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


def _record_pending(disk):
    """Record that `disk` is installed while older code is still running."""
    global _disk_version, _needed

    changed = not _needed or _disk_version != disk
    _disk_version = disk
    _needed = True
    _write_state(True, running_version(), disk)
    if changed:
        _tag_redraw()


def _record_clear(disk):
    """Record that the running process and the installed code now match."""
    global _disk_version, _needed

    changed = _needed or _disk_version != disk
    _disk_version = disk
    _needed = False
    _write_state(False, running_version(), disk)
    if changed:
        _tag_redraw()


def _poll():
    global _last_mtime

    try:
        mtime = _MANIFEST.stat().st_mtime_ns
    except OSError:
        # Keep the last good state while the extension files are being replaced.
        return _POLL_SECONDS

    if mtime == _last_mtime:
        return _POLL_SECONDS

    disk = _read_manifest_version()
    if disk is None:
        # Keep the last good state; retry when the manifest next changes.
        return _POLL_SECONDS
    _last_mtime = mtime

    running = running_version()
    if running is None:
        return _POLL_SECONDS

    if disk != running:
        _record_pending(disk)
    else:
        _record_clear(disk)

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
    """Capture this process's baseline version and start the update watch."""
    global _last_mtime, _disk_version, _needed

    _last_mtime = None
    _disk_version = None
    _needed = False

    namespace = bpy.app.driver_namespace
    baseline = namespace.get(_NAMESPACE_KEY)
    disk = _read_manifest_version()

    if baseline is None and disk is not None:
        # First register of this Blender process: the code that just loaded is
        # the code on disk, so any pending state left by an earlier session
        # has been consumed by this start.
        baseline = disk
        namespace[_NAMESPACE_KEY] = baseline
        _disk_version = disk
        _write_state(False, baseline, disk)
    elif baseline is not None:
        state = _read_state()
        _disk_version = state.get("installed_version")
        _needed = bool(state.get("just_updated"))
        if disk is not None:
            if disk != baseline:
                # Re-registered while a different version is installed, for
                # example after disabling, updating, and re-enabling.
                _record_pending(disk)
            else:
                _record_clear(disk)

    timers = bpy.app.timers
    if not timers.is_registered(_poll):
        timers.register(_poll, first_interval=0.0, persistent=True)


def unregister():
    timers = bpy.app.timers
    if timers.is_registered(_poll):
        timers.unregister(_poll)
