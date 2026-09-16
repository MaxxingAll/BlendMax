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

    def test_rejects_duplicate_object_ids(self):
        raw = valid_manifest()
        duplicate = dict(raw["objects"][0])
        duplicate["fbx_name"] = "BM_other"
        raw["objects"].append(duplicate)
        with self.assertRaisesRegex(ManifestValidationError, "Duplicate object id"):
            parse_manifest(raw)


class ManifestReferenceTests(unittest.TestCase):
    """Cross-references must resolve, or the manifest is rejected.

    Every pointer below is validated for EXISTENCE only. ``GraphLink.ref`` is
    not checked against an expected ``kind``: consumers resolve a ref by the
    target's ``class_name`` (``blender_materials.py``), so a link to a node of
    unexpected kind still resolves -- validating kind would invent a constraint
    the code does not rely on.
    """

    def _with_parent(self, parent_id):
        raw = valid_manifest()
        raw["objects"][0]["parent_id"] = parent_id
        return raw

    def test_valid_parent_reference_parses(self):
        raw = valid_manifest()
        child = dict(raw["objects"][0])
        child["id"] = "obj_2"
        child["fbx_name"] = "BM_child"
        child["parent_id"] = "obj_1"
        raw["objects"].append(child)

        manifest = parse_manifest(raw)

        parents = {item.object_id: item.parent_id for item in manifest.objects}
        self.assertEqual(parents["obj_2"], "obj_1")

    def test_null_parent_remains_valid(self):
        manifest = parse_manifest(self._with_parent(None))
        self.assertIsNone(manifest.objects[0].parent_id)

    def test_dangling_parent_id_is_rejected(self):
        raw = self._with_parent("obj_missing")
        with self.assertRaisesRegex(
            ManifestValidationError, r"objects\[0\]\.parent_id references unknown object id"
        ):
            parse_manifest(raw)

    def test_valid_assignment_object_id_parses(self):
        manifest = parse_manifest(valid_manifest())
        self.assertEqual(manifest.assignments[0].object_id, "obj_1")

    def test_dangling_assignment_object_id_is_rejected(self):
        raw = valid_manifest()
        raw["materials"]["assignments"][0]["object_id"] = "obj_missing"
        with self.assertRaisesRegex(
            ManifestValidationError,
            r"materials\.assignments\[0\]\.object_id references unknown object id",
        ):
            parse_manifest(raw)

    def test_valid_material_ref_parses(self):
        manifest = parse_manifest(valid_manifest())
        self.assertEqual(manifest.assignments[0].material_ref, "mat_1")

    def test_null_material_ref_remains_valid(self):
        raw = valid_manifest()
        raw["materials"]["assignments"][0]["material_ref"] = None
        manifest = parse_manifest(raw)
        self.assertIsNone(manifest.assignments[0].material_ref)

    def test_dangling_material_ref_is_rejected(self):
        raw = valid_manifest()
        raw["materials"]["assignments"][0]["material_ref"] = "mat_missing"
        with self.assertRaisesRegex(
            ManifestValidationError,
            r"materials\.assignments\[0\]\.material_ref references unknown graph id",
        ):
            parse_manifest(raw)

    def test_valid_sub_textures_ref_parses(self):
        manifest = parse_manifest(valid_manifest())
        node = next(item for item in manifest.graph if item.node_id == "mat_1")
        self.assertEqual([link.ref for link in node.sub_textures], ["tex_1"])

    def test_dangling_sub_textures_ref_is_rejected(self):
        raw = valid_manifest()
        raw["materials"]["graph"][0]["sub_textures"][0]["ref"] = "tex_missing"
        with self.assertRaisesRegex(
            ManifestValidationError,
            r"materials\.graph\[0\]\.sub_textures\[0\]\.ref references unknown graph id",
        ):
            parse_manifest(raw)

    def test_valid_sub_materials_ref_parses(self):
        raw = valid_manifest()
        raw["materials"]["graph"][0]["sub_materials"] = [
            {"index": 1, "slot": "Base", "ref": "mat_2"}
        ]
        raw["materials"]["graph"].append(
            {
                "id": "mat_2",
                "kind": "material",
                "class": "VRayMtl",
                "name": "Inner",
                "parameters": {},
                "sub_materials": [],
                "sub_textures": [],
            }
        )

        manifest = parse_manifest(raw)

        node = next(item for item in manifest.graph if item.node_id == "mat_1")
        self.assertEqual([link.ref for link in node.sub_materials], ["mat_2"])

    def test_dangling_sub_materials_ref_is_rejected(self):
        raw = valid_manifest()
        raw["materials"]["graph"][0]["sub_materials"] = [
            {"index": 1, "slot": "Base", "ref": "mat_missing"}
        ]
        with self.assertRaisesRegex(
            ManifestValidationError,
            r"materials\.graph\[0\]\.sub_materials\[0\]\.ref references unknown graph id",
        ):
            parse_manifest(raw)

    def test_link_kind_mismatch_is_allowed(self):
        """A sub_textures link pointing at a material node must still parse.

        Consumers dispatch on class_name, not kind, so this resolves at import
        time. Rejecting it would be a constraint the importer does not have.
        """
        raw = valid_manifest()
        raw["materials"]["graph"][0]["sub_textures"][0]["ref"] = "mat_1"
        manifest = parse_manifest(raw)
        node = next(item for item in manifest.graph if item.node_id == "mat_1")
        self.assertEqual([link.ref for link in node.sub_textures], ["mat_1"])

    def test_dangling_reference_is_rejected_before_ManifestIndex(self):
        """The malformed manifest must never reach the index."""
        raw = self._with_parent("obj_missing")
        with self.assertRaises(ManifestValidationError):
            manifest = parse_manifest(raw)
            ManifestIndex(manifest)  # unreachable

    def test_legacy_zero_one_zero_texture_matching_still_works(self):
        """Preserved: schema 0.1.0 records without graph ids still match."""
        raw = valid_manifest()
        raw["schema"]["version"] = "0.1.0"
        del raw["textures"][0]["graph_node_id"]
        manifest = parse_manifest(raw)
        index = ManifestIndex(manifest)
        self.assertEqual(
            index.textures_by_graph_node["tex_1"].package_path,
            "textures/wood.png",
        )

    def test_valid_manifest_round_trips_unchanged(self):
        """A fully valid manifest parses with every reference intact."""
        raw = valid_manifest()
        child = dict(raw["objects"][0])
        child["id"] = "obj_2"
        child["fbx_name"] = "BM_child"
        child["parent_id"] = "obj_1"
        raw["objects"].append(child)
        raw["materials"]["assignments"].append(
            {"object_id": "obj_2", "material_ref": "mat_1"}
        )

        manifest = parse_manifest(raw)
        index = ManifestIndex(manifest)

        self.assertEqual(len(manifest.objects), 2)
        self.assertEqual(len(manifest.assignments), 2)
        self.assertEqual(index.objects_by_id["obj_2"].parent_id, "obj_1")
        self.assertEqual(index.nodes_by_id["mat_1"].class_name, "VRayMtl")

    # --- only None means "absent"; other falsy values are references -------

    def test_empty_string_parent_id_is_a_reference_not_absent(self):
        """Only ``None`` means "no parent".

        Broadening this to any falsy value would also absorb a numeric ``0``,
        which previously became the reference ``"0"`` and was validated. The
        parser keeps ``is not None`` semantics for both fields.
        """
        raw = valid_manifest()
        raw["objects"][0]["parent_id"] = ""
        with self.assertRaisesRegex(
            ManifestValidationError, r"parent_id references unknown object id: ''\."
        ):
            parse_manifest(raw)

    def test_empty_string_material_ref_is_a_reference_not_absent(self):
        raw = valid_manifest()
        raw["materials"]["assignments"][0]["material_ref"] = ""
        with self.assertRaisesRegex(
            ManifestValidationError, r"material_ref references unknown graph id: ''\."
        ):
            parse_manifest(raw)

    def test_numeric_zero_parent_id_is_a_reference_not_absent(self):
        """A falsy-but-present value must not be silently absorbed."""
        raw = valid_manifest()
        raw["objects"][0]["parent_id"] = 0
        with self.assertRaisesRegex(
            ManifestValidationError, r"parent_id references unknown object id: '0'\."
        ):
            parse_manifest(raw)

    def test_numeric_zero_material_ref_is_a_reference_not_absent(self):
        raw = valid_manifest()
        raw["materials"]["assignments"][0]["material_ref"] = 0
        with self.assertRaisesRegex(
            ManifestValidationError, r"material_ref references unknown graph id: '0'\."
        ):
            parse_manifest(raw)

    def test_error_message_quotes_the_offending_ref(self):
        """A bare value renders an empty string as nothing after the colon."""
        raw = self._with_parent("obj_missing")
        with self.assertRaisesRegex(
            ManifestValidationError, r"unknown object id: 'obj_missing'\."
        ):
            parse_manifest(raw)

    # --- textures[*].graph_node_id is the same class of pointer ------------

    def test_valid_texture_graph_node_id_parses(self):
        manifest = parse_manifest(valid_manifest())
        self.assertEqual(manifest.textures[0].graph_node_id, "tex_1")

    def test_dangling_texture_graph_node_id_is_rejected(self):
        """Otherwise the index keys a texture under a node that does not exist
        and the texture silently never binds."""
        raw = valid_manifest()
        raw["textures"][0]["graph_node_id"] = "tex_missing"
        with self.assertRaisesRegex(
            ManifestValidationError,
            r"textures\[0\]\.graph_node_id references unknown graph id: 'tex_missing'\.",
        ):
            parse_manifest(raw)

    def test_absent_texture_graph_node_id_is_allowed(self):
        """Legacy 0.1.0 records have no graph_node_id at all."""
        raw = valid_manifest()
        del raw["textures"][0]["graph_node_id"]
        manifest = parse_manifest(raw)
        self.assertIsNone(manifest.textures[0].graph_node_id)

    # --- existence is not enough for parent_id: cycles --------------------

    def test_parent_cycle_is_rejected(self):
        """Existence alone leaves parent_id half-validated: a cycle passed
        every target check and only failed later in hierarchy_bounds, which
        raises a bare ValueError outside the importer's error handling."""
        raw = valid_manifest()
        first = dict(raw["objects"][0])
        first.update(id="obj_1", fbx_name="BM_a", parent_id="obj_2")
        second = dict(raw["objects"][0])
        second.update(id="obj_2", fbx_name="BM_b", parent_id="obj_1")
        raw["objects"] = [first, second]
        raw["asset"]["root_id"] = "obj_1"

        with self.assertRaisesRegex(ManifestValidationError, "parent cycle"):
            parse_manifest(raw)

    def test_self_parent_is_rejected(self):
        raw = valid_manifest()
        raw["objects"][0]["parent_id"] = "obj_1"
        with self.assertRaisesRegex(ManifestValidationError, "parent cycle"):
            parse_manifest(raw)

    def test_valid_nested_chain_is_not_a_cycle(self):
        raw = valid_manifest()
        chain = []
        for index, parent in enumerate((None, "obj_1", "obj_2"), start=1):
            item = dict(raw["objects"][0])
            item.update(
                id="obj_{0}".format(index),
                fbx_name="BM_{0}".format(index),
                parent_id=parent,
            )
            chain.append(item)
        raw["objects"] = chain
        raw["asset"]["root_id"] = "obj_1"

        manifest = parse_manifest(raw)

        parents = {item.object_id: item.parent_id for item in manifest.objects}
        self.assertEqual(parents, {"obj_1": None, "obj_2": "obj_1", "obj_3": "obj_2"})


if __name__ == "__main__":
    unittest.main()
