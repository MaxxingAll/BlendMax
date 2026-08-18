"""One-time BlendMax menu installer for Autodesk 3ds Max 2025.3."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from blendmax_install import InstallError, install_from_source  # noqa: E402


def _notify(message: str, title: str) -> None:
    try:
        from pymxs import runtime as rt

        rt.messageBox(str(message), title=title)
    except Exception:
        print("{0}: {1}".format(title, message))


def run() -> None:
    try:
        result = install_from_source(PROJECT_ROOT)
        _notify(
            (
                "BlendMax {version} installed.\n\n"
                "Location:\n{bundle_path}\n\n"
                "Restart 3ds Max, then use the BlendMax menu."
            ).format(**result),
            "BlendMax Installed",
        )
    except InstallError as exc:
        _notify(str(exc), "BlendMax Installation Failed")
    except Exception as exc:
        print(traceback.format_exc())
        _notify(
            "Unexpected installer error: {0}".format(exc),
            "BlendMax Installation Failed",
        )


run()
