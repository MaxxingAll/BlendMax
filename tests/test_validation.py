from __future__ import annotations

import unittest

from blendmax_max.errors import SceneValidationError
from blendmax_max.models import SceneNode
from blendmax_max.validation import evaluate_size_policy, validate_scene


def node(
    node_id,
    name,
    parent_id=None,
    group_head=False,
    group_member=False,
    exportable=True,
):
    return SceneNode(
        node_id=node_id,
        name=name,
        node_type="Editable_Poly",
        superclass="GeometryClass",
        parent_id=parent_id,
        is_group_head=group_head,
        is_group_member=group_member,
        exportable=exportable,
    )


class ValidationTests(unittest.TestCase):
    def test_accepts_one_standalone_object(self):
        result = validate_scene([node("1", "Chair")])
        self.assertEqual(result.mode, "object")
        self.assertEqual(result.payload_ids, ("1",))

    def test_rejects_multiple_ungrouped_objects(self):
        with self.assertRaises(SceneValidationError) as caught:
            validate_scene([node("1", "Chair"), node("2", "Table")])
        self.assertEqual(caught.exception.code, "MULTIPLE_OBJECTS")

    def test_accepts_one_group_and_members(self):
        nodes = [
            node("g", "ChairGroup", group_head=True, exportable=False),
            node("1", "Seat", parent_id="g", group_member=True),
            node("2", "Legs", parent_id="g", group_member=True),
        ]
        result = validate_scene(nodes)
        self.assertEqual(result.mode, "group")
        self.assertEqual(result.object_count, 2)
        self.assertEqual(result.export_ids, ("g", "1", "2"))

    def test_ignored_group_descendant_is_not_exported(self):
        nodes = [
            node("g", "ChairGroup", group_head=True, exportable=False),
            node("1", "Seat", parent_id="g", group_member=True),
            SceneNode(
                node_id="light",
                name="StudioLight",
                node_type="VRayLight",
                superclass="Light",
                parent_id="g",
                is_group_member=True,
                exportable=False,
            ),
        ]
        result = validate_scene(nodes)
        self.assertEqual(result.payload_ids, ("1",))
        self.assertEqual(result.export_ids, ("g", "1"))
        self.assertIn("StudioLight", result.warnings[0])

    def test_rejects_object_outside_group(self):
        nodes = [
            node("g", "ChairGroup", group_head=True, exportable=False),
            node("1", "Seat", parent_id="g", group_member=True),
            node("2", "OtherAsset"),
        ]
        with self.assertRaises(SceneValidationError) as caught:
            validate_scene(nodes)
        self.assertEqual(caught.exception.code, "MIXED_ASSETS")

    def test_rejects_more_than_fifteen_payload_objects(self):
        nodes = [node("g", "Group", group_head=True, exportable=False)]
        nodes.extend(
            node(str(index), "Part", parent_id="g", group_member=True)
            for index in range(16)
        )
        with self.assertRaises(SceneValidationError) as caught:
            validate_scene(nodes)
        self.assertEqual(caught.exception.code, "TOO_MANY_OBJECTS")

    def test_oversized_asset_produces_scale_recommendation(self):
        result = evaluate_size_policy((100.0, 20.0, 5.0))
        self.assertTrue(result.oversized)
        self.assertAlmostEqual(result.recommended_scale, 0.5)

    def test_tiny_asset_gets_roasted(self):
        with self.assertRaises(SceneValidationError) as caught:
            evaluate_size_policy((0.001, 0.002, 0.003))
        self.assertEqual(caught.exception.code, "TOO_SMALL")
        self.assertIn("magnifying glass", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
