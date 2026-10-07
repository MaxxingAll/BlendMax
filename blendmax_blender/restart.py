"""Relaunch Blender for the BlendMax update notice.

Blender has no restart operator, so a restart is a new detached Blender
process followed by a quit of this one. The new process is spawned first and
the quit only runs once the spawn succeeded; when no new Blender can be
started the running session is left untouched. Unsaved changes are resolved
before spawning, because Blender's own quit prompt can still be cancelled
after the new process already exists.
"""

from __future__ import annotations

import os
import subprocess

import bpy


SAVE = "SAVE"
DISCARD = "DISCARD"

# subprocess only defines these on Windows; the values are the Win32 flags.
_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
_CREATE_NEW_PROCESS_GROUP = getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
)


def _is_windows():
    return os.name == "nt"


def is_dirty():
    """Return True when the open file has unsaved changes."""
    return bool(bpy.data.is_dirty)


def executable_path():
    """Return the Blender executable to relaunch, or "" when unknown.

    On Windows a sibling ``blender-launcher.exe`` is preferred because it
    starts Blender without a console window.
    """
    binary = bpy.app.binary_path
    if not binary:
        return ""
    if _is_windows():
        launcher = os.path.join(os.path.dirname(binary), "blender-launcher.exe")
        if os.path.isfile(launcher):
            return launcher
    return binary


def build_command():
    """Return the argv for the new Blender, or None without an executable.

    The original ``sys.argv`` is never forwarded: it may carry ``-b`` or
    ``--python`` arguments that must not run again. A saved file is reopened.
    """
    executable = executable_path()
    if not executable:
        return None
    command = [executable]
    filepath = bpy.data.filepath
    if filepath:
        command.append(filepath)
    return command


def launch(command):
    """Start `command` as a detached process; may raise OSError."""
    options = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": os.path.dirname(command[0]) or None,
    }
    if _is_windows():
        options["creationflags"] = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return subprocess.Popen(command, **options)


def restart_blender(report, unsaved_action=DISCARD):
    """Relaunch Blender and quit this session; return an operator result set.

    `report` is the operator's ``report`` method. `unsaved_action` decides
    what happens to unsaved changes (``SAVE`` or ``DISCARD``).
    """
    if is_dirty() and unsaved_action == SAVE:
        if not bpy.data.filepath:
            report({"ERROR"}, "Save the file first (File > Save As), then restart.")
            return {"CANCELLED"}
        if "FINISHED" not in bpy.ops.wm.save_mainfile():
            report(
                {"ERROR"},
                "The file could not be saved; Blender was not restarted.",
            )
            return {"CANCELLED"}

    command = build_command()
    if command is None:
        report(
            {"ERROR"},
            "Could not start a new Blender: the Blender executable is "
            "unknown; quit and reopen Blender manually.",
        )
        return {"CANCELLED"}
    try:
        launch(command)
    except OSError as error:
        report(
            {"ERROR"},
            "Could not start a new Blender: {0}; quit and reopen Blender "
            "manually.".format(error),
        )
        return {"CANCELLED"}

    # EXEC_DEFAULT does not prompt: unsaved changes were resolved above.
    bpy.ops.wm.quit_blender("EXEC_DEFAULT")
    return {"FINISHED"}
