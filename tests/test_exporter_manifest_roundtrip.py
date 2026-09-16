from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from blendmax_blender.errors import ManifestValidationError
from blendmax_blender.manifest import ManifestIndex, parse_manifest
from blendmax_max.exporter import BlendMaxExporter
from blendmax_max.models import SceneNode


class NestedAdapter:
    """A group with an unexported helper mid-hierarchy.

    Node 3's parent (2) is a helper that is not exportable, so the exporter must
    walk up to the nearest EXPORTED ancestor and remap the parent reference. If
    it emitted the raw parent id, the manifest would carry a dangling pointer
    and this test would catch it.
    """

    def snapshot_scene(self):
        return [
            SceneNode(
                node_id="1",
                name="Root",
                node_type="Dummy",
                superclass="Helper",
                is_group_head=True,
            ),
            SceneNode(
                node_id="2",
                name="HiddenHelper",
                node_type="Dummy",
                superclass="Helper",
                parent_id="1",
                exportable=False,
            ),
            SceneNode(
                node_id="3",
                name="Mesh",
                node_type="Editable_Poly",
                superclass="GeometryClass",
                parent_id="2",
            ),
        ]

    def bounds_in_meters(self, payload_ids):
        return {
            "minimum": [0.0, 0.0, 0.0],
            "maximum": [1.0, 1.0, 1.0],
            "dimensions": [1.0, 1.0, 1.0],
        }

    def capture_material_graph(self, payload_ids):
        return {
            "serialization": "generic_property_snapshot",
            "assignments": [{"object_id": "3", "material_ref": "mat_1"}],
            "graph": [
                {
                    "id": "mat_1",
                    "kind": "material",
                    "class": "VRayMtl",
                    "name": "Surface",
                    "parameters": {},
                    "sub_materials": [],
                    "sub_textures": [
                        {"index": 1, "slot": "Diffuse", "ref": "tex_1"}
                    ],
                },
                {
                    "id": "tex_1",
                    "kind": "texture",
                    "class": "Bitmaptexture",
                    "name": "Albedo",
                    "parameters": {"filename": "albedo.png"},
                    "sub_materials": [],
                    "sub_textures": [],
                },
            ],
        }

    def discover_texture_references(self, material_data):
        # Must return at least one reference, otherwise the manifest carries no
        # texture records and the graph_node_id assertion below silently
        # asserts nothing. copy_texture_files still emits a record with a
        # graph_node_id even when the file cannot be resolved, so no fixture
        # image is needed.
        return [
            {
                "graph_node_id": "tex_1",
                "parameter": "filename",
                "raw_path": "albedo.png",
                "resolved_path": "albedo.png",
            }
        ]

    def prepared_export(self, export_ids, selection_ids=None):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            self.export_ids = tuple(export_ids)
            # The exporter looks up an FBX name for every exported node, so the
            # mapping must cover them all -- not just the payload mesh.
            yield {str(node_id): "BM_{0}".format(node_id) for node_id in export_ids}

        return _ctx()

    def export_selected_fbx(self, output_path):
        Path(output_path).write_bytes(b"fake-fbx")
        return []

    def source_metadata(self):
        return {"application": "Autodesk 3ds Max", "scene_file": "Nested.max"}


class ExporterManifestRoundTripTests(unittest.TestCase):
    """parse_manifest must accept what the exporter actually writes.

    Every other manifest test starts from a hand-written dict. This is the seam
    where a new hard failure in parse_manifest would break real packages, so it
    round-trips genuine exporter output.
    """

    def _manifest_from_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            # export() appends the .blendmax suffix itself.
            output = Path(temporary) / "Nested"
            BlendMaxExporter(NestedAdapter()).export(output)
            with zipfile.ZipFile(str(output) + ".blendmax", "r") as archive:
                return json.loads(archive.read("manifest.json"))

    def test_exporter_output_parses(self):
        manifest = parse_manifest(self._manifest_from_export())
        self.assertTrue(manifest.objects)

    def test_unexported_parent_is_remapped_to_an_exported_ancestor(self):
        """The dangling-parent hazard: node 3's parent (2) is not exported."""
        manifest = parse_manifest(self._manifest_from_export())
        index = ManifestIndex(manifest)

        mesh = next(item for item in manifest.objects if item.object_id == "3")
        self.assertIsNotNone(
            mesh.parent_id,
            "the mesh should inherit the nearest exported ancestor",
        )
        self.assertIn(mesh.parent_id, index.objects_by_id)
        # The unexported helper (node 2) must not appear as a target.
        self.assertNotEqual(mesh.parent_id, "2")
        self.assertEqual(mesh.parent_id, "1")

    def test_exported_references_all_resolve(self):
        manifest = parse_manifest(self._manifest_from_export())
        index = ManifestIndex(manifest)

        for assignment in manifest.assignments:
            self.assertIn(assignment.object_id, index.objects_by_id)
            if assignment.material_ref is not None:
                self.assertIn(assignment.material_ref, index.nodes_by_id)
        for node in manifest.graph:
            for link in node.sub_materials:
                self.assertIn(link.ref, index.nodes_by_id)
            for link in node.sub_textures:
                self.assertIn(link.ref, index.nodes_by_id)
        for texture in manifest.textures:
            if texture.graph_node_id is not None:
                self.assertIn(texture.graph_node_id, index.nodes_by_id)

    def test_reference_assertions_are_not_vacuous(self):
        """Guards the test above from asserting over empty collections.

        The texture-pointer loop only runs if the manifest actually carries
        texture records, and graph_node_id is the field the validation change
        added -- so an empty list would make that assertion meaningless.
        """
        manifest = parse_manifest(self._manifest_from_export())

        self.assertTrue(manifest.objects, "no objects emitted")
        self.assertTrue(manifest.assignments, "no assignments emitted")
        self.assertTrue(manifest.graph, "no graph nodes emitted")
        self.assertTrue(
            any(node.sub_textures for node in manifest.graph),
            "no graph links emitted; the link loop would be vacuous",
        )
        self.assertTrue(
            manifest.textures,
            "no texture records emitted; the graph_node_id loop would be vacuous",
        )
        self.assertTrue(
            any(item.graph_node_id is not None for item in manifest.textures),
            "no texture carries a graph_node_id; the pointer check would be vacuous",
        )

    def test_dangling_texture_pointer_in_exporter_output_is_rejected(self):
        """Dangling the emitted pointer proves the field is really validated."""
        raw = self._manifest_from_export()
        record = next(
            item for item in raw["textures"] if item.get("graph_node_id") is not None
        )
        record["graph_node_id"] = "tex_nope"

        with self.assertRaisesRegex(ManifestValidationError, "graph_node_id"):
            parse_manifest(raw)


if __name__ == "__main__":
    unittest.main()
