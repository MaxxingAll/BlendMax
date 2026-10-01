"""Restart notice for BlendMax, with BlenderKit-style persisted state.

A state file records that a different BlendMax version is installed while
older code is still running. The notice is drawn from that record, and the
record is consumed once the updated code is actually running. BlendMax ships
no updater, so a timer compares the manifest version on disk with the version
captured when this Blender process first registered the add-on. When the
watch first detects a change it also asks for a one-shot restart dialog
(BlenderKit's popup pattern); the dialog is offered once per update, and the
preferences notice remains the persistent record.
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
_POPUP_DELAY_SECONDS = 0.2
_POPUP_RETRY_SECONDS = 2.0
_POPUP_MAX_ATTEMPTS = 5

_last_mtime = None
_disk_version = None
_needed = False
_popup_pending = False
_popup_shown = False
_popup_attempts = 0


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


def _write_state(just_updated, running, installed, popup_shown):
    """Write the persisted notice state, skipping identical content."""
    path = _state_path()
    if path is None:
        return
    state = {
        "just_updated": bool(just_updated),
        "running_version": running,
        "installed_version": installed,
        "popup_shown": bool(popup_shown),
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
    global _disk_version, _needed, _popup_shown

    changed = not _needed or _disk_version != disk
    _disk_version = disk
    _needed = True
    if changed:
        # A new update event may ask for the dialog again.
        _popup_shown = False
    _write_state(True, running_version(), disk, _popup_shown)
    if changed:
        _request_popup()
        _tag_redraw()


def _record_clear(disk):
    """Record that the running process and the installed code now match."""
    global _disk_version, _needed, _popup_pending, _popup_shown

    changed = _needed or _disk_version != disk
    _disk_version = disk
    _needed = False
    _popup_pending = False
    _popup_shown = False
    _write_state(False, running_version(), disk, False)
    if changed:
        _tag_redraw()


def _show_popup(window):
    """Invoke the restart dialog operator in `window`; may raise."""
    with bpy.context.temp_override(window=window):
        bpy.ops.blendmax.restart_notice_popup("INVOKE_DEFAULT")


def _request_popup():
    """Schedule the one-shot restart dialog; called once per update event."""
    global _popup_attempts, _popup_pending

    if _popup_shown:
        return
    _popup_pending = True
    timers = bpy.app.timers
    if not timers.is_registered(_popup_tick):
        _popup_attempts = 0
        timers.register(
            _popup_tick, first_interval=_POPUP_DELAY_SECONDS, persistent=False
        )


def _popup_tick():
    """Try once to show the restart dialog; bounded retries, then give up."""
    global _popup_attempts, _popup_pending, _popup_shown

    if not _popup_pending or _popup_shown:
        _popup_attempts = 0
        return None

    try:
        window = next(iter(bpy.context.window_manager.windows), None)
    except Exception:
        window = None
    if window is None or getattr(bpy.app, "background", False):
        return _popup_retry()

    try:
        _show_popup(window)
    except Exception:
        return _popup_retry()

    _popup_attempts = 0
    _popup_pending = False
    _popup_shown = True
    _write_state(True, running_version(), _disk_version, True)
    return None


def _popup_retry():
    """Count a failed dialog attempt and decide whether to try again."""
    global _popup_attempts

    _popup_attempts += 1
    if _popup_attempts <= _POPUP_MAX_ATTEMPTS:
        return _POPUP_RETRY_SECONDS
    return None


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
    global _popup_attempts, _popup_pending, _popup_shown

    _last_mtime = None
    _disk_version = None
    _needed = False
    _popup_pending = False
    _popup_shown = False
    _popup_attempts = 0

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
        _write_state(False, baseline, disk, False)
    elif baseline is not None:
        state = _read_state()
        _disk_version = state.get("installed_version")
        _needed = bool(state.get("just_updated"))
        _popup_shown = bool(state.get("popup_shown"))
        if disk is not None:
            if disk != baseline:
                # Re-registered while a different version is installed, for
                # example after disabling, updating, and re-enabling.
                _record_pending(disk)
            else:
                _record_clear(disk)
        if _needed and not _popup_shown:
            # A previous session could not show the dialog; try again.
            _request_popup()

    timers = bpy.app.timers
    if not timers.is_registered(_poll):
        timers.register(_poll, first_interval=0.0, persistent=True)


def unregister():
    timers = bpy.app.timers
    for callback in (_poll, _popup_tick):
        if timers.is_registered(callback):
            timers.unregister(callback)
