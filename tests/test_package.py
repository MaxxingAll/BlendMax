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
            write_manifest(stage / "manifest.json", {"schema": {"version": "0.1.1"}})

            output = create_archive(stage, root / "Chair.blendmax")
            with zipfile.ZipFile(output, "r") as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    ["geometry.fbx", "manifest.json"],
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["schema"]["version"], "0.1.1")

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

    def test_texture_record_links_graph_property_to_package_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            texture = root / "wood.png"
            texture.write_bytes(b"texture")
            records = copy_texture_files(
                [
                    {
                        "graph_node_id": "tex_42",
                        "parameter": "filename",
                        "raw_path": "maps/wood.png",
                        "resolved_path": str(texture),
                    }
                ],
                root / "package" / "textures",
            )

            self.assertEqual(
                records[0],
                {
                    "graph_node_id": "tex_42",
                    "parameter": "filename",
                    "raw_path": "maps/wood.png",
                    "source_path": str(texture),
                    "status": "copied",
                    "package_path": "textures/wood.png",
                },
            )

    def test_duplicate_texture_filenames_receive_distinct_package_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first" / "shared.png"
            second = root / "second" / "shared.png"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            records = copy_texture_files(
                [
                    {
                        "graph_node_id": "tex_1",
                        "parameter": "filename",
                        "raw_path": "first/shared.png",
                        "resolved_path": str(first),
                    },
                    {
                        "graph_node_id": "tex_2",
                        "parameter": "filename",
                        "raw_path": "second/shared.png",
                        "resolved_path": str(second),
                    },
                ],
                root / "package" / "textures",
            )

            self.assertNotEqual(records[0]["package_path"], records[1]["package_path"])
            self.assertTrue((root / "package" / records[0]["package_path"]).is_file())
            self.assertTrue((root / "package" / records[1]["package_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
