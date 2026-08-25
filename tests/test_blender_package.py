from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from blendmax_blender.errors import PackageValidationError
from blendmax_blender.package import open_blendmax
from test_blender_manifest import valid_manifest


def write_package(path: Path, manifest=None, extra=None):
    manifest = manifest or valid_manifest()
    extra = extra or {}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("geometry.fbx", b"fbx")
        archive.writestr("textures/wood.png", b"image")
        for name, contents in extra.items():
            archive.writestr(name, contents)


class BlenderPackageTests(unittest.TestCase):
    def test_extracts_only_declared_import_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Chair.blendmax"
            write_package(path, extra={"notes.txt": b"not imported"})

            with open_blendmax(path) as package:
                self.assertEqual(package.geometry_path.read_bytes(), b"fbx")
                self.assertEqual(
                    package.texture_paths["textures/wood.png"].read_bytes(),
                    b"image",
                )
                self.assertFalse((package.root / "notes.txt").exists())

    def test_rejects_archive_traversal_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Unsafe.blendmax"
            write_package(path, extra={"../escape.txt": b"bad"})
            with self.assertRaisesRegex(PackageValidationError, "Unsafe archive path"):
                with open_blendmax(path):
                    pass

    def test_rejects_missing_declared_texture(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Missing.blendmax"
            raw = valid_manifest()
            raw["textures"][0]["package_path"] = "textures/missing.png"
            write_package(path, raw)
            with self.assertRaisesRegex(PackageValidationError, "texture is missing"):
                with open_blendmax(path):
                    pass

    def test_rejects_wrong_file_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Chair.zip"
            write_package(path)
            with self.assertRaisesRegex(PackageValidationError, r"\.blendmax"):
                with open_blendmax(path):
                    pass


if __name__ == "__main__":
    unittest.main()
