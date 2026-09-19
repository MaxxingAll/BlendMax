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
    # Shared archive policy. It must be in the release because build_bundle()
    # copies it into Contents/python from the extracted release, and because
    # blendmax_install.py imports it as a top-level module.
    "blendmax_archive_policy.py",
    "run_blendmax_max.py",
    "blendmax_max",
    "appbundle",
    "tests",
    "tools",
)


ARCHIVE_POLICY_FILE = "blendmax_archive_policy.py"
# The template path whose copytree every installer version already performs.
BUNDLE_PYTHON_TEMPLATE = Path("appbundle") / "BlendMax.bundle" / "Contents" / "python"


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
    policy = PROJECT_ROOT / ARCHIVE_POLICY_FILE
    if not policy.is_file():
        raise RuntimeError("Shared archive policy is missing: {0}.".format(policy))

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_release_files():
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())
        # The shared policy is written into the bundle TEMPLATE as well as the
        # release root above, from the same source bytes.
        #
        # Why both: build_bundle() copies the release-root file, but an
        # installer deployed before this change does not know that file exists.
        # Its build_bundle() copies only the template, blendmax_max/ and
        # blendmax_install.py -- so without this entry, upgrading through an
        # older installer deploys the NEW installer next to NO policy, and the
        # bundle dies on first launch with ModuleNotFoundError. The template is
        # the one location every installer version, past and future, copies.
        archive.writestr(
            (BUNDLE_PYTHON_TEMPLATE / ARCHIVE_POLICY_FILE).as_posix(),
            policy.read_bytes(),
        )
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
