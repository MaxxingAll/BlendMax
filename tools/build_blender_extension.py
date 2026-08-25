"""Build a deterministic, installable BlendMax Blender Extension ZIP."""

from __future__ import annotations

import argparse
import tomllib
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "blendmax_blender"
REQUIRED_FILES = ("__init__.py", "blender_manifest.toml")


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


def build(output: Path) -> Path:
    for name in REQUIRED_FILES:
        if not (SOURCE_ROOT / name).is_file():
            raise RuntimeError("Blender extension is missing {0}.".format(name))

    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in iter_extension_files():
            info = zipfile.ZipInfo(
                path.relative_to(SOURCE_ROOT).as_posix(),
                date_time=(2026, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
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
