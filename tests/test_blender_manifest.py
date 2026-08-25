from __future__ import annotations

import unittest

from blendmax_blender.errors import ManifestValidationError
from blendmax_blender.manifest import ManifestIndex, parse_manifest


def valid_manifest():
    return {
        "schema": {"name": "BlendMax Manifest", "version": "0.1.1"},
        "asset": {
            "name": "Chair",
            "mode": "object",
            "root_id": "obj_1",
            "bounds_m": {
                "minimum": [0.0, 0.0, 0.0],
                "maximum": [1.0, 2.0, 3.0],
                "dimensions": [1.0, 2.0, 3.0],
            },
            "size_policy": {"recommended_blender_scale": 1.0},
        },
        "geometry": {"file": "geometry.fbx"},
        "objects": [
            {
                "id": "obj_1",
                "fbx_name": "BM_object",
                "original_name": "Chair",
                "node_type": "Editable_Poly",
                "superclass": "GeometryClass",
                "parent_id": None,
                "is_group_head": False,
                "is_group_member": False,
            }
        ],
        "materials": {
            "assignments": [{"object_id": "obj_1", "material_ref": "mat_1"}],
            "graph": [
                {
                    "id": "mat_1",
                    "kind": "material",
                    "class": "VRayMtl",
                    "name": "Chair V-Ray",
                    "parameters": {"Diffuse": [0.2, 0.3, 0.4, 1.0]},
                    "sub_materials": [],
                    "sub_textures": [
                        {"index": 1, "slot": "Diffuse", "ref": "tex_1"}
                    ],
                },
                {
                    "id": "tex_1",
                    "kind": "texture",
                    "class": "Bitmaptexture",
                    "name": "Wood",
                    "parameters": {"filename": "wood.png"},
                    "sub_materials": [],
                    "sub_textures": [],
                },
            ],
        },
        "textures": [
            {
                "graph_node_id": "tex_1",
                "parameter": "filename",
                "status": "copied",
                "package_path": "textures/wood.png",
            }
        ],
        "warnings": [],
    }


class BlenderManifestTests(unittest.TestCase):
    def test_parses_current_schema_and_builds_indexes(self):
        manifest = parse_manifest(valid_manifest())
        index = ManifestIndex(manifest)

        self.assertEqual(manifest.schema_version, "0.1.1")
        self.assertEqual(manifest.asset_name, "Chair")
        self.assertEqual(index.objects_by_fbx_name["bm_object"].object_id, "obj_1")
        self.assertEqual(index.nodes_by_id["mat_1"].class_name, "VRayMtl")
        self.assertEqual(
            index.textures_by_graph_node["tex_1"].package_path,
            "textures/wood.png",
        )

    def test_matches_legacy_texture_record_by_filename(self):
        raw = valid_manifest()
        raw["schema"]["version"] = "0.1.0"
        del raw["textures"][0]["graph_node_id"]
        manifest = parse_manifest(raw)
        index = ManifestIndex(manifest)

        self.assertEqual(
            index.textures_by_graph_node["tex_1"].package_path,
            "textures/wood.png",
        )

    def test_rejects_incompatible_schema_family(self):
        raw = valid_manifest()
        raw["schema"]["version"] = "0.2.0"
        with self.assertRaisesRegex(ManifestValidationError, "not compatible"):
            parse_manifest(raw)

    def test_rejects_duplicate_fbx_names_case_insensitively(self):
        raw = valid_manifest()
        duplicate = dict(raw["objects"][0])
        duplicate["id"] = "obj_2"
        duplicate["fbx_name"] = "bm_OBJECT"
        raw["objects"].append(duplicate)
        with self.assertRaisesRegex(ManifestValidationError, "Duplicate FBX"):
            parse_manifest(raw)


if __name__ == "__main__":
    unittest.main()
