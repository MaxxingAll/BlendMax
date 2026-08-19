from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path

from blendmax_max.exporter import BlendMaxExporter
from blendmax_max.models import SceneNode


class FakeAdapter:
    def snapshot_scene(self):
        return [
            SceneNode(
                node_id="1",
                name="Chair",
                node_type="Editable_Poly",
                superclass="GeometryClass",
            )
        ]

    def bounds_in_meters(self, payload_ids):
        self.payload_ids = tuple(payload_ids)
        return {
            "minimum": [0.0, 0.0, 0.0],
            "maximum": [1.0, 1.0, 1.0],
            "dimensions": [1.0, 1.0, 1.0],
        }

    def capture_material_graph(self, payload_ids):
        return {
            "serialization": "generic_property_snapshot",
            "assignments": [{"object_id": "1", "material_ref": None}],
            "graph": [],
        }

    def discover_texture_references(self, material_data):
        return []

    @contextmanager
    def prepared_export(self, export_ids, selection_ids=None):
        self.export_ids = tuple(export_ids)
        self.selection_ids = tuple(selection_ids or export_ids)
        yield {"1": "BM_test_object"}

    def export_selected_fbx(self, output_path):
        Path(output_path).write_bytes(b"fake-fbx")
        return []

    def source_metadata(self):
        return {
            "application": "Autodesk 3ds Max",
            "scene_file": "Chair.max",
        }


class ExporterTests(unittest.TestCase):
    def test_end_to_end_package_with_fake_max_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "Chair.blendmax"
            summary = BlendMaxExporter(FakeAdapter()).export(output)

            self.assertEqual(summary["asset_name"], "Chair")
            self.assertEqual(summary["object_count"], 1)
            with zipfile.ZipFile(output, "r") as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["asset"]["name"], "Chair")
                self.assertEqual(manifest["schema"]["version"], "0.1.1")
                self.assertEqual(manifest["objects"][0]["fbx_name"], "BM_test_object")
                self.assertEqual(archive.read("geometry.fbx"), b"fake-fbx")

    def test_ignored_hierarchy_node_is_excluded_and_child_is_reparented(self):
        class GroupAdapter(FakeAdapter):
            def snapshot_scene(self):
                return [
                    SceneNode(
                        node_id="g",
                        name="ChairGroup",
                        node_type="GroupHead",
                        superclass="Helper",
                        is_group_head=True,
                        exportable=False,
                    ),
                    SceneNode(
                        node_id="helper",
                        name="RigHelper",
                        node_type="Dummy",
                        superclass="Helper",
                        parent_id="g",
                        is_group_member=True,
                        exportable=False,
                    ),
                    SceneNode(
                        node_id="mesh",
                        name="Chair",
                        node_type="Editable_Poly",
                        superclass="GeometryClass",
                        parent_id="helper",
                        is_group_member=True,
                    ),
                ]

            def capture_material_graph(self, payload_ids):
                return {
                    "serialization": "conversion_relevant_property_snapshot",
                    "assignments": [
                        {"object_id": "mesh", "material_ref": None}
                    ],
                    "graph": [],
                }

            @contextmanager
            def prepared_export(self, export_ids, selection_ids=None):
                self.export_ids = tuple(export_ids)
                self.selection_ids = tuple(selection_ids or export_ids)
                yield {node_id: "BM_" + node_id for node_id in export_ids}

        adapter = GroupAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "Chair.blendmax"
            BlendMaxExporter(adapter).export(output)
            with zipfile.ZipFile(output, "r") as archive:
                manifest = json.loads(archive.read("manifest.json"))

        self.assertEqual(adapter.export_ids, ("g", "mesh"))
        self.assertEqual(adapter.selection_ids, ("mesh",))
        self.assertEqual(
            [record["id"] for record in manifest["objects"]],
            ["g", "mesh"],
        )
        self.assertEqual(manifest["objects"][1]["parent_id"], "g")


if __name__ == "__main__":
    unittest.main()
