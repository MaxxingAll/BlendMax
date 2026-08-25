"""Python implementations invoked by the 3ds Max BlendMax menu."""

from __future__ import annotations

import importlib
import sys
import traceback
import webbrowser
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parent
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


PROJECT_URL = "https://github.com/MaxxingAll/BlendMax"


def _fresh_core_callable(module_name: str, callable_name: str):
    """Load an action from the currently installed core, not Max's module cache."""

    importlib.invalidate_caches()
    stale_modules = [
        name
        for name in sys.modules
        if name == "blendmax_max" or name.startswith("blendmax_max.")
    ]
    for name in sorted(stale_modules, key=lambda value: value.count("."), reverse=True):
        sys.modules.pop(name, None)
    module = importlib.import_module(module_name)
    return getattr(module, callable_name)


def _runtime():
    from pymxs import runtime as rt

    return rt


def _notify(message: str, title: str = "BlendMax") -> None:
    try:
        _runtime().messageBox(str(message), title=title)
    except Exception:
        print("{0}: {1}".format(title, message))


def export_asset() -> None:
    run_interactive = _fresh_core_callable(
        "blendmax_max.max_entrypoint",
        "run_interactive",
    )
    run_interactive()


def join_mesh_by_material() -> None:
    run_interactive = _fresh_core_callable(
        "blendmax_max.cleanup_entrypoint",
        "run_interactive",
    )
    run_interactive()


def install_update() -> None:
    from blendmax_install import InstallError, install_from_zip

    try:
        archive = _runtime().getOpenFileName(
            caption="Install BlendMax Update",
            types="ZIP Archive (*.zip)|*.zip|",
        )
        if not archive:
            return
        result = install_from_zip(Path(str(archive)))
        _notify(
            (
                "BlendMax {version} installed.\n\n"
                "Location:\n{bundle_path}\n\n"
                "The Python update is active for the next BlendMax action.\n"
                "Restart 3ds Max only if the menu layout was changed."
            ).format(**result),
            "BlendMax Update Complete",
        )
    except InstallError as exc:
        _notify(str(exc), "BlendMax Update Failed")
    except Exception as exc:
        print(traceback.format_exc())
        _notify("Unexpected updater error: {0}".format(exc), "BlendMax Update Failed")


def open_project_page() -> None:
    if not webbrowser.open(PROJECT_URL):
        _notify(PROJECT_URL, "BlendMax Project Page")


def show_about() -> None:
    from blendmax_install import default_install_root

    core = _fresh_core_callable("blendmax_max", "__version__")
    # Loading one value refreshes the package; read the remaining metadata from
    # that same newly imported module so About cannot show a cached version.
    core_module = sys.modules["blendmax_max"]
    supported_vray_range = core_module.SUPPORTED_VRAY_RANGE
    target_max_version = core_module.TARGET_MAX_VERSION
    version = core

    bundle = default_install_root() / "BlendMax.bundle"
    _notify(
        (
            "BlendMax {version}\n\n"
            "Target: Autodesk 3ds Max {max_version}\n"
            "V-Ray: {vray_range}\n"
            "Implementation: Python with a 3ds Max 2025 menu bridge\n\n"
            "Installed at:\n{bundle}"
        ).format(
            version=version,
            max_version=target_max_version,
            vray_range=supported_vray_range,
            bundle=bundle,
        ),
        "About BlendMax",
    )
