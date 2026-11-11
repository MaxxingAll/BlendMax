from __future__ import annotations

import math
import unittest

from blendmax_blender.curve_uv import project_from_view, uv_fit


IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

# w equals -z, as in a camera looking down -Z: depth divides X and Y.
PERSPECTIVE = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
)


class ProjectFromViewTests(unittest.TestCase):
    def test_square_viewport_maps_its_corners_to_the_uv_square(self):
        result = project_from_view(
            [(-1, -1, 0), (1, 1, 0), (0, 0, 0)], IDENTITY, 100, 100
        )

        self.assertEqual(result.uvs, ((0.0, 0.0), (1.0, 1.0), (0.5, 0.5)))
        self.assertEqual(result.outside, 0)

    def test_screen_right_and_up_are_positive_u_and_v(self):
        centre, right, up = project_from_view(
            [(0, 0, 0), (0.5, 0, 0), (0, 0.5, 0)], IDENTITY, 100, 100
        ).uvs

        self.assertGreater(right[0], centre[0])
        self.assertEqual(right[1], centre[1])
        self.assertGreater(up[1], centre[1])
        self.assertEqual(up[0], centre[0])

    def test_wide_viewport_fills_u_and_centres_v(self):
        result = project_from_view([(-1, -1, 0), (1, 1, 0)], IDENTITY, 200, 100)

        self.assertEqual(result.uvs, ((0.0, 0.25), (1.0, 0.75)))

    def test_tall_viewport_fills_v_and_centres_u(self):
        result = project_from_view([(-1, -1, 0), (1, 1, 0)], IDENTITY, 100, 200)

        self.assertEqual(result.uvs, ((0.25, 0.0), (0.75, 1.0)))

    def test_equal_pixels_stay_equal_in_uv_space(self):
        # 100 x 50 pixels on a 200 x 100 viewport: half of each side on screen.
        low, high = project_from_view(
            [(-0.5, -0.5, 0), (0.5, 0.5, 0)], IDENTITY, 200, 100
        ).uvs

        self.assertAlmostEqual((high[0] - low[0]) / (high[1] - low[1]), 2.0)

    def test_perspective_divide_shrinks_with_distance(self):
        near, far = project_from_view(
            [(1, 0, -2), (1, 0, -4)], PERSPECTIVE, 100, 100
        ).uvs

        self.assertEqual(near, (0.75, 0.5))
        self.assertEqual(far, (0.625, 0.5))

    def test_outside_the_viewport_is_counted_and_not_clamped(self):
        result = project_from_view([(2, 0, 0), (0, -3, 0)], IDENTITY, 100, 100)

        self.assertEqual(result.uvs, ((1.5, 0.5), (0.5, -1.0)))
        self.assertEqual(result.outside, 2)

    def test_on_or_behind_the_viewpoint_stays_finite_and_counts_as_outside(self):
        result = project_from_view(
            [(1, 1, 0), (1, 1, 1e-12), (0.5, 0.5, 2)], PERSPECTIVE, 100, 100
        )

        self.assertEqual(result.outside, 3)
        for uv in result.uvs:
            self.assertTrue(all(math.isfinite(value) for value in uv))

    def test_degenerate_viewport_is_refused(self):
        for width, height in ((0, 100), (100, 0), (-1, 100), (0, 0)):
            with self.subTest(width=width, height=height):
                with self.assertRaisesRegex(ValueError, "no usable size"):
                    project_from_view([(0, 0, 0)], IDENTITY, width, height)

    def test_empty_input_is_an_empty_result(self):
        result = project_from_view([], IDENTITY, 100, 100)

        self.assertEqual(result.uvs, ())
        self.assertEqual(result.outside, 0)


class UvFitTests(unittest.TestCase):
    def test_long_side_spans_the_uv_square_and_short_side_is_centred(self):
        self.assertEqual(uv_fit(200, 100), (0.5, 0.5, 0.25, 0.5))
        self.assertEqual(uv_fit(100, 200), (0.25, 0.5, 0.5, 0.5))
        self.assertEqual(uv_fit(100, 100), (0.5, 0.5, 0.5, 0.5))

    def test_degenerate_viewport_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no usable size"):
            uv_fit(0, 100)


if __name__ == "__main__":
    unittest.main()
