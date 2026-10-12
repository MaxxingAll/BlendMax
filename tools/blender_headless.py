"""Run Blender in background mode without the user's legacy add-ons.

Some add-ons cannot run headless: V-Ray for Blender Community Edition refuses
background mode and keeps relaunching its ZmqServer, so ``blender -b`` never
exits. ``--factory-startup`` avoids that but also drops the user preferences
and therefore the installed BlendMax extension.

This runner points ``BLENDER_USER_SCRIPTS`` at an empty temporary folder for
one run instead. Legacy add-ons live in ``scripts/addons`` and are not found,
while the user preferences (``config``) and the extensions (``extensions``,
where BlendMax is installed) still load. Nothing on disk is changed.

The run also skips the user's startup scripts, presets and templates. Do not
save preferences from such a run: the skipped add-ons could be recorded as
disabled.

Usage::

    python tools/blender_headless.py [--blender PATH] [--timeout SECONDS] -- \\
        [blender arguments]

``-b`` is always passed. Blender is found from ``--blender``, then the
``BLENDER`` environment variable, then the default Blender 5.2 install path on
Windows, then ``blender`` on ``PATH``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Optional, Sequence

_WINDOWS_DEFAULT = Path(
    r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)


def find_blender(
    explicit: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Return the Blender executable to run, or raise FileNotFoundError."""

    values = os.environ if environ is None else environ
    for candidate in (explicit, values.get("BLENDER")):
        if candidate:
            return candidate
    if os.name == "nt" and _WINDOWS_DEFAULT.is_file():
        return str(_WINDOWS_DEFAULT)
    found = shutil.which("blender")
    if found:
        return found
    raise FileNotFoundError(
        "Blender was not found; pass --blender or set the BLENDER variable."
    )


def headless_command(blender: str, arguments: Sequence[str]) -> list:
    """Return the argv for a background run; ``-b`` is added once.

    Only Blender's own options (before a ``--`` separator) are filtered:
    everything after ``--`` belongs to the user's script and is passed on
    untouched, even when it contains ``-b``.
    """

    arguments = list(arguments)
    split = arguments.index("--") if "--" in arguments else len(arguments)
    own = [item for item in arguments[:split] if item not in {"-b", "--background"}]
    return [blender, "-b", *own, *arguments[split:]]


def headless_environment(
    empty_scripts: str,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    """Return a copy of the environment with an empty user scripts folder."""

    values = dict(os.environ if environ is None else environ)
    values["BLENDER_USER_SCRIPTS"] = empty_scripts
    return values


def run(
    arguments: Sequence[str],
    blender: Optional[str] = None,
    timeout: Optional[float] = None,
) -> int:
    """Run Blender headless and return its exit code."""

    executable = find_blender(blender)
    with tempfile.TemporaryDirectory(prefix="blender_empty_scripts_") as empty:
        completed = subprocess.run(
            headless_command(executable, arguments),
            env=headless_environment(empty),
            timeout=timeout,
        )
    return completed.returncode


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blender", help="Blender executable to run")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Stop Blender after this many seconds",
    )
    parser.add_argument(
        "blender_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to Blender (after --)",
    )
    options = parser.parse_args(argv)
    arguments = list(options.blender_args)
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    try:
        return run(arguments, blender=options.blender, timeout=options.timeout)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(
            "Blender did not finish within {0} seconds.".format(options.timeout),
            file=sys.stderr,
        )
        return 124


if __name__ == "__main__":
    sys.exit(main())
