from __future__ import annotations

import unittest

from blendmax_max.cleanup import (
    build_cleanup_plan,
    format_face_bitarray,
    material_id_lookup,
)
from blendmax_max.errors import CleanupError
from blendmax_max.models import SceneNode


def node(
    node_id,
    parent_id=None,
    *,
    geometry=True,
    shape=False,
    node_type=None,
    superclass=None,
    group_head=False,
    hidden_or_frozen=False,
):
    resolved_node_type = (
        node_type
        if node_type is not None
        else ("Line" if shape else ("Editable_Poly" if geometry else "Dummy"))
    )
    resolved_superclass = (
        superclass
        if superclass is not None
        else ("Shape" if shape else ("GeometryClass" if geometry else "Helper"))
    )
    return SceneNode(
        node_id=node_id,
        name=node_id,
        node_type=resolved_node_type,
        superclass=resolved_superclass,
        parent_id=parent_id,
        is_group_head=group_head,
        is_group_member=parent_id is not None,
        exportable=geometry and not hidden_or_frozen,
        hidden_or_frozen=hidden_or_frozen,
    )


class CleanupPlanningTests(unittest.TestCase):
    def test_visible_meshes_are_planned_and_nested_groups_are_removable(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node("nested", "root", geometry=False, group_head=True),
            node("a", "nested"),
            node("b", "root"),
        ]

        plan = build_cleanup_plan(nodes, "root")

        self.assertEqual(plan.visible_geometry_ids, ("a", "b"))
        self.assertEqual(plan.shape_ids, ())
        self.assertEqual(plan.removable_group_ids, ("nested",))

    def test_detects_only_shapes_inside_selected_root(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node("mesh", "root"),
            node("nested", "root", geometry=False, group_head=True),
            node("shape_a", "root", geometry=False, shape=True),
            node("shape_b", "nested", geometry=False, shape=True),
            node("outside_shape", geometry=False, shape=True),
        ]

        plan = build_cleanup_plan(nodes, "root")

        self.assertEqual(plan.shape_ids, ("shape_a", "shape_b"))

    def test_detects_spline_class_name_even_if_superclass_is_unexpected(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node("mesh", "root"),
            node(
                "spline",
                "root",
                geometry=False,
                node_type="Editable_Spline",
                superclass="Unknown",
            ),
        ]

        plan = build_cleanup_plan(nodes, "root")

        self.assertEqual(plan.shape_ids, ("spline",))

    def test_hidden_or_frozen_object_anywhere_in_scene_aborts_cleanup(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node("visible", "root"),
            node("hidden_outside_root", hidden_or_frozen=True),
        ]

        with self.assertRaisesRegex(CleanupError, "hidden or frozen objects"):
            build_cleanup_plan(nodes, "root")

    def test_hidden_group_aborts_cleanup(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node(
                "hidden_group",
                "root",
                geometry=False,
                group_head=True,
                hidden_or_frozen=True,
            ),
            node("hidden_mesh", "hidden_group"),
            node("visible", "root"),
        ]

        with self.assertRaisesRegex(CleanupError, "hidden or frozen objects"):
            build_cleanup_plan(nodes, "root")

    def test_requires_visible_geometry(self):
        nodes = [
            node("root", geometry=False, group_head=True),
            node("helper", "root", geometry=False),
        ]

        with self.assertRaisesRegex(CleanupError, "no geometry"):
            build_cleanup_plan(nodes, "root")

    def test_requires_a_group_root(self):
        with self.assertRaisesRegex(CleanupError, "Root Group not Detected"):
            build_cleanup_plan([node("mesh")], "mesh")

    def test_multi_sub_lookup_uses_explicit_material_ids(self):
        red = object()
        blue = object()

        lookup = material_id_lookup([19, 3], [red, blue])

        self.assertIs(lookup[19], red)
        self.assertIs(lookup[3], blue)

    def test_face_bitarray_is_sorted_unique_and_compact(self):
        self.assertEqual(
            format_face_bitarray([9, 3, 2, 1, 3, 7, 8]),
            "#{1..3,7..9}",
        )
        self.assertEqual(format_face_bitarray([]), "#{}")


if __name__ == "__main__":
    unittest.main()
