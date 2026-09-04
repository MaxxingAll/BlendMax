from __future__ import annotations

import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

from tools.build_blender_extension import build


class BlenderExtensionBuildTests(unittest.TestCase):
    def test_build_has_manifest_and_extension_at_archive_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build(Path(temporary) / "blendmax_importer.zip")
            with zipfile.ZipFile(output, "r") as archive:
                names = archive.namelist()
                metadata = tomllib.loads(
                    archive.read("blender_manifest.toml").decode("utf-8")
                )

            self.assertIn("__init__.py", names)
            self.assertIn("addon.py", names)
            self.assertNotIn("blendmax_blender/__init__.py", names)
            self.assertEqual(metadata["id"], "blendmax_importer")
            self.assertEqual(metadata["version"], "0.1.7")
            self.assertEqual(metadata["blender_version_min"], "4.2.0")

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = build(root / "first.zip")
            second = build(root / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
