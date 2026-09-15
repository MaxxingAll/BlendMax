"""One-restart state for BlendMax add-on installation notices."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"
_STATE_FILENAME = "blendmax_restart_notice.json"

# Win32 constants for the non-destructive liveness probe. Deliberately NOT
# PROCESS_TERMINATE: this code must never be able to end a process it only
# means to observe. See _windows_pid_is_alive().
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_INVALID_PARAMETER = 87
_ERROR_ACCESS_DENIED = 5


def _state_path(bpy) -> Path:
    directory = bpy.utils.user_resource(
        "CONFIG",
        path="blendmax",
        create=True,
    )
    return Path(directory) / _STATE_FILENAME


def _read_state(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, state: dict) -> bool:
    """Write state to disk.

    ``OSError`` is swallowed so Preferences/registration cannot crash if the
    config directory is unwritable. A failed write means the persistent
    one-shot flag may not survive a BlendMax module reload. The in-process
    cache in ``addon.py`` still prevents a second use until that reload.
    """

    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        return False
    return True


def _clear_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _persist_state(path: Path, state: dict) -> bool:
    if state:
        return _write_state(path, state)
    _clear_state(path)
    return True


def _windows_pid_is_alive(pid: int) -> bool:
    """Non-destructive liveness probe using a query-only process handle.

    ``os.kill(pid, 0)`` is not a safe probe on Windows. Verified on CPython
    3.11 (MSC v.1944, 64-bit): calling it against a live, unrelated child
    process terminates it — the child reaped with exit status 3221225794
    (``0xC0000142``, ``STATUS_DLL_INIT_FAILED``), the signature of
    ``TerminateProcess``. Windows has no "signal 0" concept, so CPython's
    ``os.kill`` maps the call onto a real termination.

    Persisted PIDs from a previous Blender session can be recycled by an
    unrelated process, and ``_pruned_consumed_pids`` calls this probe on those
    persisted values — so the old implementation could kill a bystander.

    This opens the process with ``PROCESS_QUERY_LIMITED_INFORMATION`` only, a
    handle that cannot terminate or signal anything, and classifies the failure
    by ``GetLastError``.
    """

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # ACCESS_DENIED means the process is there but owned by someone else:
        # still alive. INVALID_PARAMETER means no such PID.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _pid_is_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if _IS_WINDOWS:
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _consumed_pids_from_state(state: dict) -> list:
    pids = []
    stored = state.get("hot_reload_consumed_pids")
    if isinstance(stored, list):
        for pid in stored:
            if isinstance(pid, int) and pid not in pids:
                pids.append(pid)
    legacy = state.get("hot_reload_consumed_pid")
    if isinstance(legacy, int) and legacy not in pids:
        pids.append(legacy)
    return pids


def _pruned_consumed_pids(pids, current_pid: int) -> list:
    kept = []
    for pid in pids:
        if pid == current_pid or _pid_is_alive(pid):
            if pid not in kept:
                kept.append(pid)
    return kept


def _store_consumed_pids(state: dict, pids) -> None:
    state.pop("hot_reload_consumed_pid", None)
    if pids:
        state["hot_reload_consumed_pids"] = list(pids)
    else:
        state.pop("hot_reload_consumed_pids", None)


def _drop_restart_notice_fields(state: dict) -> None:
    state.pop("pending_pid", None)
    state.pop("hot_reload_pending_pid", None)


def restart_notice_required(bpy) -> bool:
    """Return whether the current Blender process still needs a restart.

    The first registration records the current process ID and shows the notice.
    A later Blender process consumes that state, which makes the notice vanish
    after one full Blender restart while keeping it visible through re-enables
    in the original process. A successful hot reload is represented by a
    one-shot current-process reload marker and consumes the notice on the first
    successful registration of the reloaded module.
    """

    path = _state_path(bpy)
    state = _read_state(path)
    current_pid = os.getpid()
    pending_pid = state.get("pending_pid")
    hot_reload_pending_pid = state.get("hot_reload_pending_pid")

    if hot_reload_pending_pid == current_pid:
        _drop_restart_notice_fields(state)
        _store_consumed_pids(
            state,
            _pruned_consumed_pids(_consumed_pids_from_state(state), current_pid),
        )
        _persist_state(path, state)
        return False

    if pending_pid is None:
        state["pending_pid"] = current_pid
        _store_consumed_pids(
            state,
            _pruned_consumed_pids(_consumed_pids_from_state(state), current_pid),
        )
        _write_state(path, state)
        return True

    if pending_pid == current_pid:
        return True

    _drop_restart_notice_fields(state)
    _store_consumed_pids(
        state,
        _pruned_consumed_pids(_consumed_pids_from_state(state), current_pid),
    )
    _persist_state(path, state)
    return False


def mark_hot_reload_pending(bpy) -> None:
    """Mark that the next successful registration is caused by a hot reload."""

    path = _state_path(bpy)
    current_pid = os.getpid()
    state = _read_state(path)
    state["pending_pid"] = current_pid
    state["hot_reload_pending_pid"] = current_pid
    _write_state(path, state)


def mark_hot_reload_failed(bpy) -> None:
    """Restore the normal same-process restart notice after a failed reload."""

    path = _state_path(bpy)
    current_pid = os.getpid()
    state = _read_state(path)
    state["pending_pid"] = current_pid
    state.pop("hot_reload_pending_pid", None)
    _write_state(path, state)


def hot_reload_consumed_for_current_process(bpy) -> bool:
    """Return whether this Blender process has already used Hot Reload."""

    path = _state_path(bpy)
    state = _read_state(path)
    return os.getpid() in _consumed_pids_from_state(state)


def mark_hot_reload_consumed(bpy) -> None:
    """Record that Hot Reload has been used in the current Blender process."""

    path = _state_path(bpy)
    current_pid = os.getpid()
    state = _read_state(path)
    pids = _pruned_consumed_pids(_consumed_pids_from_state(state), current_pid)
    if current_pid not in pids:
        pids.append(current_pid)
    _store_consumed_pids(state, pids)
    _write_state(path, state)


def unmark_hot_reload_consumed(bpy) -> None:
    """Remove the current process from the Hot Reload consumed set."""

    path = _state_path(bpy)
    current_pid = os.getpid()
    state = _read_state(path)
    pids = [
        pid
        for pid in _pruned_consumed_pids(_consumed_pids_from_state(state), current_pid)
        if pid != current_pid
    ]
    _store_consumed_pids(state, pids)
    _persist_state(path, state)
