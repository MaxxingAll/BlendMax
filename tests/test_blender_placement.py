from __future__ import annotations

import unittest

from blendmax_blender.placement import (
    bounds_from_points,
    grounded_anchor,
    hierarchy_bounds,
    merge_bounds,
)


class BlenderPlacementTests(unittest.TestCase):
    def test_world_bounds_track_negative_and_positive_coordinates(self):
        bounds = bounds_from_points(
            ((-4.5, -0.6, 0.1), (-4.1, 0.2, 0.7), (-4.3, -0.1, -0.05))
        )

        self.assertEqual(bounds, ((-4.5, -0.6, -0.05), (-4.1, 0.2, 0.7)))

    def test_empty_geometry_has_no_bounds(self):
        self.assertIsNone(bounds_from_points(()))
        self.assertIsNone(merge_bounds(()))

    def test_grounded_anchor_centers_footprint_and_uses_lowest_point(self):
        anchor = grounded_anchor(((-4.6, -0.6, -0.001), (-4.0, 0.2, 0.51)))

        self.assertAlmostEqual(anchor[0], -4.3)
        self.assertAlmostEqual(anchor[1], -0.2)
        self.assertAlmostEqual(anchor[2], -0.001)

    def test_nested_groups_receive_only_their_descendant_geometry_bounds(self):
        branches = hierarchy_bounds(
            {
                "root": None,
                "plant_a": "root",
                "plant_b": "root",
                "leaf_a": "plant_a",
                "pot_a": "plant_a",
                "leaf_b": "plant_b",
            },
            {
                "leaf_a": ((-4.6, -0.5, 0.1), (-4.2, -0.1, 0.6)),
                "pot_a": ((-4.5, -0.4, 0.0), (-4.3, -0.2, 0.2)),
                "leaf_b": ((-4.0, 0.2, 0.05), (-3.6, 0.5, 0.7)),
            },
        )

        self.assertEqual(branches["plant_a"], ((-4.6, -0.5, 0.0), (-4.2, -0.1, 0.6)))
        self.assertEqual(branches["plant_b"], ((-4.0, 0.2, 0.05), (-3.6, 0.5, 0.7)))
        self.assertEqual(branches["root"], ((-4.6, -0.5, 0.0), (-3.6, 0.5, 0.7)))

    def test_parent_cycle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "parent cycle"):
            hierarchy_bounds({"first": "second", "second": "first"}, {})


if __name__ == "__main__":
    unittest.main()
