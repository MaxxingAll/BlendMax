"""Python implementations invoked by the 3ds Max BlendMax menu."""

from __future__ import annotations

import sys
import traceback
import webbrowser
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parent
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


PROJECT_URL = "https://github.com/MaxxingAll/BlendMax"


def _runtime():
    from pymxs import runtime as rt

    return rt


def _notify(message: str, title: str = "BlendMax") -> None:
    try:
        _runtime().messageBox(str(message), title=title)
    except Exception:
        print("{0}: {1}".format(title, message))


def export_asset() -> None:
    from blendmax_max.max_entrypoint import run_interactive

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
                "Restart 3ds Max to finish the update."
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
    from blendmax_max import (
        SUPPORTED_VRAY_RANGE,
        TARGET_MAX_VERSION,
        __version__,
    )

    bundle = default_install_root() / "BlendMax.bundle"
    _notify(
        (
            "BlendMax {version}\n\n"
            "Target: Autodesk 3ds Max {max_version}\n"
            "V-Ray: {vray_range}\n"
            "Implementation: Python with a 3ds Max 2025 menu bridge\n\n"
            "Installed at:\n{bundle}"
        ).format(
            version=__version__,
            max_version=TARGET_MAX_VERSION,
            vray_range=SUPPORTED_VRAY_RANGE,
            bundle=bundle,
        ),
        "About BlendMax",
    )
