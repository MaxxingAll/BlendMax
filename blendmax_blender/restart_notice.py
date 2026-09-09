"""One-restart state for BlendMax add-on installation notices."""

from __future__ import annotations

import json
import os
from pathlib import Path

_STATE_FILENAME = "blendmax_restart_notice.json"


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


def _write_state(path: Path, state: dict) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def _clear_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


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
        state.pop("pending_pid", None)
        state.pop("hot_reload_pending_pid", None)
        if state:
            _write_state(path, state)
        else:
            _clear_state(path)
        return False

    if pending_pid is None:
        state["pending_pid"] = current_pid
        _write_state(path, state)
        return True

    if pending_pid == current_pid:
        return True

    _clear_state(path)
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
    return state.get("hot_reload_consumed_pid") == os.getpid()


def mark_hot_reload_consumed(bpy) -> None:
    """Record that Hot Reload has been used in the current Blender process."""

    path = _state_path(bpy)
    state = _read_state(path)
    state["hot_reload_consumed_pid"] = os.getpid()
    _write_state(path, state)
