from __future__ import annotations

import unittest

from blendmax_blender.physical_material_fidelity import (
    coat_affected_color,
    coating_affect_factors,
    emission_luminance,
    sss_parameters,
    transparency_depth_inverse,
    transparency_roughness,
)


class PhysicalMaterialFidelityTests(unittest.TestCase):
    def test_locked_transparency_roughness_follows_reflection(self):
        self.assertAlmostEqual(
            transparency_roughness({"trans_roughness_lock": True}, 0.37), 0.37
        )

    def test_unlocked_transparency_roughness_honors_inversion(self):
        self.assertAlmostEqual(
            transparency_roughness(
                {"trans_roughness_lock": False, "trans_roughness": 0.2, "trans_roughness_inv": True},
                0.8,
            ),
            0.8,
        )

    def test_transparency_depth_is_encoded_as_inverse_depth(self):
        self.assertAlmostEqual(transparency_depth_inverse({"trans_depth": 4.0}), 0.25)
        self.assertEqual(transparency_depth_inverse({"trans_depth": 0.0}), 0.0)

    def test_sss_depth_combines_depth_and_scale(self):
        color, scatter, depth = sss_parameters(
            {
                "sss_color": [0.8, 0.4, 0.2, 1.0],
                "sss_scatter_color": [0.9, 0.2, 0.1, 1.0],
                "sss_depth": 6.0,
                "sss_scale": 0.5,
            }
        )
        self.assertEqual(color, (0.8, 0.4, 0.2, 1.0))
        self.assertEqual(scatter, (0.9, 0.2, 0.1, 1.0))
        self.assertEqual(depth, 3.0)

    def test_emission_uses_physical_luminance(self):
        self.assertAlmostEqual(
            emission_luminance({"emission": 0.5, "emit_luminance": 1200.0}), 600.0
        )

    def test_coating_effects_are_weighted(self):
        self.assertEqual(
            coating_affect_factors(
                {"coating": 0.8, "coat_affect_color": 0.5, "coat_affect_roughness": 0.25}
            ),
            (0.4, 0.2),
        )

    def test_coating_affect_color_matches_documented_power_rule(self):
        result = coat_affected_color(
            (0.25, 0.5, 0.75, 1.0),
            {"coating": 1.0, "coat_affect_color": 0.5},
        )
        self.assertAlmostEqual(result[0], 0.125)
        self.assertAlmostEqual(result[1], 0.3535533906)
        self.assertAlmostEqual(result[2], 0.6495190528)
        self.assertEqual(result[3], 1.0)


if __name__ == "__main__":
    unittest.main()
