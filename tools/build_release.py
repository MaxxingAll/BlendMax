"""Build a distributable BlendMax release ZIP from the source tree."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
INCLUDED_ROOTS = (
    "README.md",
    "CHANGELOG.md",
    "TEST_MATRIX.md",
    "install_blendmax.py",
    "blendmax_install.py",
    "run_blendmax_max.py",
    "blendmax_max",
    "appbundle",
    "tests",
    "tools",
)


def version() -> str:
    contents = (PROJECT_ROOT / "blendmax_max" / "__init__.py").read_text(
        encoding="utf-8"
    )
    match = VERSION_PATTERN.search(contents)
    if not match:
        raise RuntimeError("Could not read BlendMax version.")
    return match.group(1)


def iter_release_files():
    for name in INCLUDED_ROOTS:
        path = PROJECT_ROOT / name
        if path.is_file():
            yield path
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if "__pycache__" in child.parts or child.suffix in {".pyc", ".pyo"}:
                continue
            yield child


def build(output: Path) -> Path:
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_release_files():
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT.parent / "BlendMax_Max_v{0}.zip".format(version()),
    )
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
