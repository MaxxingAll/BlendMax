from __future__ import annotations

import unittest

from blendmax_blender.presentation_cage import cage_geometry


class MeasurementCageGeometryTests(unittest.TestCase):
    def test_unit_divisions_produce_only_the_outer_box(self):
        vertices, edges = cage_geometry(
            ((0.0, 0.0, 0.0), (2.0, 3.0, 4.0)),
            (1, 1, 1),
        )
        self.assertEqual(len(vertices), 8)
        self.assertEqual(len(edges), 12)
        self.assertEqual(len(edges), len(set(edges)))
        self.assertTrue(all(start != end for start, end in edges))

    def test_axis_divisions_add_grid_lines_on_the_matching_faces(self):
        vertices, edges = cage_geometry(
            ((0.0, 0.0, 0.0), (2.0, 3.0, 4.0)),
            (2, 3, 4),
        )
        self.assertEqual(len(vertices), 32)
        self.assertEqual(len(edges), 36)
        self.assertIn((0.0, 0.0, 0.0), vertices)
        self.assertIn((2.0, 3.0, 4.0), vertices)

    def test_fractional_bounds_are_preserved(self):
        vertices, _edges = cage_geometry(
            ((-1.5, 2.25, 0.5), (3.5, 5.25, 4.5)),
            (2, 2, 2),
        )
        self.assertIn((-1.5, 2.25, 0.5), vertices)
        self.assertIn((3.5, 5.25, 4.5), vertices)

    def test_invalid_division_count_is_rejected(self):
        with self.assertRaises(ValueError):
            cage_geometry(((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), (1, 2))
        with self.assertRaises(ValueError):
            cage_geometry(((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), (1, 0, 1))

    def test_degenerate_axis_does_not_create_zero_length_edges(self):
        vertices, edges = cage_geometry(
            ((0.0, 0.0, 0.0), (0.0, 2.0, 3.0)),
            (2, 2, 2),
        )
        self.assertTrue(vertices)
        self.assertTrue(edges)
        self.assertTrue(all(start != end for start, end in edges))


if __name__ == "__main__":
    unittest.main()
