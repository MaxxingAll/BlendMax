from __future__ import annotations

import unittest

from blendmax_blender.presentation import PresentationBounds
from blendmax_blender.presentation_cage import (
    cage_geometry,
    default_grid_divisions,
    measurement_envelope,
)


class MeasurementCageGeometryTests(unittest.TestCase):
    def test_default_grid_gives_two_by_two_cells_on_a_two_metre_face(self):
        asset = PresentationBounds.from_bounds(((0, 0, 0), (2, 2, 2)))
        envelope = measurement_envelope(asset, 1.0)
        divisions = default_grid_divisions(envelope.dimensions)
        vertices, edges = cage_geometry(
            (envelope.minimum, envelope.maximum), divisions
        )

        self.assertEqual(envelope.dimensions, (2.0, 2.0, 2.0))
        self.assertEqual(divisions, (2, 2, 2))
        self.assertEqual(divisions[0] * divisions[1], 4)
        top_face_edges = [
            (vertices[start], vertices[end])
            for start, end in edges
            if vertices[start][2] == 2.0 and vertices[end][2] == 2.0
        ]
        x_grid_lines = [
            edge for edge in top_face_edges if edge[0][1] == edge[1][1]
        ]
        y_grid_lines = [
            edge for edge in top_face_edges if edge[0][0] == edge[1][0]
        ]
        self.assertEqual(len(x_grid_lines), 3)
        self.assertEqual(len(y_grid_lines), 3)
        self.assertEqual({edge[0][1] for edge in x_grid_lines}, {0.0, 1.0, 2.0})
        self.assertEqual({edge[0][0] for edge in y_grid_lines}, {0.0, 1.0, 2.0})

    def test_default_grid_follows_a_four_by_three_by_two_metre_envelope(self):
        asset = PresentationBounds.from_bounds(((0, 0, 0), (4, 3, 2)))
        envelope = measurement_envelope(asset, 1.0)
        divisions = default_grid_divisions(envelope.dimensions)
        vertices, edges = cage_geometry(
            (envelope.minimum, envelope.maximum), divisions
        )

        self.assertEqual(envelope.dimensions, (4.0, 3.0, 2.0))
        self.assertEqual(divisions, (4, 3, 2))
        self.assertEqual(divisions[0] * divisions[1], 12)
        top_face_edges = [
            (vertices[start], vertices[end])
            for start, end in edges
            if vertices[start][2] == 2.0 and vertices[end][2] == 2.0
        ]
        self.assertEqual(len(top_face_edges), divisions[0] + divisions[1] + 2)
        x_grid_lines = [
            edge for edge in top_face_edges if edge[0][1] == edge[1][1]
        ]
        y_grid_lines = [
            edge for edge in top_face_edges if edge[0][0] == edge[1][0]
        ]
        self.assertEqual(len(x_grid_lines), divisions[1] + 1)
        self.assertEqual(len(y_grid_lines), divisions[0] + 1)
        self.assertEqual(
            {edge[0][1] for edge in x_grid_lines}, {0.0, 1.0, 2.0, 3.0}
        )
        self.assertEqual(
            {edge[0][0] for edge in y_grid_lines}, {0.0, 1.0, 2.0, 3.0, 4.0}
        )

    def test_default_grid_keeps_degenerate_axes_at_one_division(self):
        self.assertEqual(default_grid_divisions((0.0, 2.0, 3.0)), (1, 2, 3))

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

    def test_awkward_fractional_bounds_keep_shared_boundary_vertices_unique(self):
        bounds = ((-0.3, -0.3, -0.3), (1.7, 1.9, 2.3))
        vertices, edges = cage_geometry(bounds, (3, 3, 3))

        self.assertEqual(len(vertices), 32)
        self.assertEqual(len(vertices), len(set(vertices)))
        self.assertEqual(len(edges), len(set(edges)))
        self.assertIn(bounds[0], vertices)
        self.assertIn(bounds[1], vertices)

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


class MeasurementEnvelopeTests(unittest.TestCase):
    def test_quantizes_multiple_dimensions_from_the_minimum_corner(self):
        asset = PresentationBounds.from_bounds(
            ((10.0, -5.0, 2.0), (13.6, -2.5, 3.5))
        )

        envelope = measurement_envelope(asset, 1.0)

        self.assertEqual(envelope.dimensions, (4.0, 3.0, 2.0))
        self.assertEqual(envelope.minimum, asset.minimum)
        self.assertEqual(envelope.maximum, (14.0, -2.0, 4.0))
        self.assertTrue(
            all(
                lower <= asset_lower <= asset_upper <= upper
                for lower, asset_lower, asset_upper, upper in zip(
                    envelope.minimum,
                    asset.minimum,
                    asset.maximum,
                    envelope.maximum,
                )
            )
        )

    def test_exact_increment_dimensions_do_not_grow(self):
        asset = PresentationBounds.from_bounds(
            ((-3.0, 4.0, 0.0), (0.0, 6.0, 4.0))
        )

        envelope = measurement_envelope(asset, 1.0)

        self.assertEqual(envelope.dimensions, (3.0, 2.0, 4.0))
        self.assertEqual(envelope.minimum, asset.minimum)
        self.assertEqual(envelope.maximum, asset.maximum)

    def test_different_increments_quantize_up_to_the_next_multiple(self):
        asset = PresentationBounds.from_bounds(((0.0, 0.0, 0.0), (3.6, 3.6, 3.6)))

        self.assertEqual(measurement_envelope(asset, 0.5).dimensions[0], 4.0)
        self.assertEqual(measurement_envelope(asset, 2.0).dimensions[0], 4.0)

    def test_near_exact_increment_snaps_measurement_but_contains_asset(self):
        asset = PresentationBounds.from_bounds(
            ((0.0, 0.0, 0.0), (3.0000000001, 1.0, 1.0))
        )

        envelope = measurement_envelope(asset, 1.0)

        self.assertEqual(envelope.dimensions[0], 3.0)
        self.assertGreaterEqual(envelope.maximum[0], asset.maximum[0])
        self.assertEqual(envelope.maximum[1:], asset.maximum[1:])

    def test_small_positive_extent_does_not_snap_down_to_zero(self):
        asset = PresentationBounds.from_bounds(
            ((0.0, 0.0, 0.0), (1e-10, 0.0, 0.0))
        )

        envelope = measurement_envelope(asset, 1.0)

        self.assertEqual(envelope.dimensions[0], 1.0)
        self.assertGreaterEqual(envelope.maximum[0], asset.maximum[0])

    def test_degenerate_dimensions_remain_zero(self):
        asset = PresentationBounds.from_bounds(
            ((2.0, -1.0, 4.0), (2.0, 1.5, 5.0))
        )

        envelope = measurement_envelope(asset, 1.0)

        self.assertEqual(envelope.dimensions, (0.0, 3.0, 1.0))
        self.assertEqual(envelope.minimum[0], envelope.maximum[0])

    def test_invalid_increments_are_rejected(self):
        asset = PresentationBounds.from_bounds(((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))
        for increment in (0.0, -1.0, float("inf"), float("nan"), None):
            with self.subTest(increment=increment):
                with self.assertRaises(ValueError):
                    measurement_envelope(asset, increment)

    def test_grid_divisions_begin_at_the_anchored_minimum_corner(self):
        asset = PresentationBounds.from_bounds(
            ((10.0, -5.0, 2.0), (13.6, -2.5, 3.5))
        )
        envelope = measurement_envelope(asset, 1.0)

        vertices, _edges = cage_geometry(
            (envelope.minimum, envelope.maximum),
            (4, 3, 2),
        )

        for x_position in range(10, 15):
            self.assertIn((float(x_position), -5.0, 2.0), vertices)


if __name__ == "__main__":
    unittest.main()
