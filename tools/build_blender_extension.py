"""Build a deterministic, installable BlendMax Blender Extension ZIP."""

from __future__ import annotations

import argparse
import tomllib
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "blendmax_blender"
REQUIRED_FILES = ("__init__.py", "blender_manifest.toml")

# The shared archive policy. It lives at the repository root because the Blender
# and 3ds Max artifacts cannot import each other, so each build copies it in.
# It is written to the extension root, which is this package's root once
# installed, so package.py can reach it as a sibling module.
SHARED_POLICY = PROJECT_ROOT / "blendmax_archive_policy.py"


def manifest() -> dict:
    return tomllib.loads(
        (SOURCE_ROOT / "blender_manifest.toml").read_text(encoding="utf-8")
    )


def iter_extension_files():
    for path in sorted(SOURCE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def _write_entry(archive, name, data):
    """Add one entry deterministically, so builds are reproducible."""

    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build(output: Path) -> Path:
    for name in REQUIRED_FILES:
        if not (SOURCE_ROOT / name).is_file():
            raise RuntimeError("Blender extension is missing {0}.".format(name))
    if not SHARED_POLICY.is_file():
        raise RuntimeError(
            "Shared archive policy is missing: {0}.".format(SHARED_POLICY)
        )

    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in iter_extension_files():
            _write_entry(
                archive,
                path.relative_to(SOURCE_ROOT).as_posix(),
                path.read_bytes(),
            )
        _write_entry(archive, SHARED_POLICY.name, SHARED_POLICY.read_bytes())
    return destination


def main() -> None:
    metadata = manifest()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "dist"
        / "blendmax_importer-{0}.zip".format(metadata["version"]),
    )
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
