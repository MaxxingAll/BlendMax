from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from blendmax_max.package import copy_texture_files, create_archive, write_manifest


class PackageTests(unittest.TestCase):
    def test_archive_contains_expected_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            stage.mkdir()
            (stage / "geometry.fbx").write_bytes(b"dummy-fbx")
            write_manifest(stage / "manifest.json", {"schema": {"version": "0.1.0"}})

            output = create_archive(stage, root / "Chair.blendmax")
            with zipfile.ZipFile(output, "r") as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    ["geometry.fbx", "manifest.json"],
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["schema"]["version"], "0.1.0")

    def test_texture_copy_records_missing_and_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            texture = root / "wood.png"
            texture.write_bytes(b"texture")
            records = copy_texture_files(
                [
                    str(texture),
                    str(root / "missing.png"),
                    "None",
                    "undefined",
                    None,
                ],
                root / "package" / "textures",
            )
            self.assertEqual(records[0]["status"], "copied")
            self.assertEqual(records[0]["package_path"], "textures/wood.png")
            self.assertEqual(records[1]["status"], "missing")
            self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
