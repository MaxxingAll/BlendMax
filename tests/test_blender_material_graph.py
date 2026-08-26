from __future__ import annotations

import unittest

from blendmax_blender.material_graph import (
    canonical_name,
    find_texture_link,
    map_amount,
    map_is_enabled,
    physical_map_is_enabled,
    physical_roughness,
    rgba,
    vray_roughness,
)
from blendmax_blender.models import GraphLink, GraphNode


class BlenderMaterialGraphTests(unittest.TestCase):
    def test_slot_matching_ignores_spacing_and_punctuation(self):
        node = GraphNode(
            node_id="mat_1",
            kind="material",
            class_name="VRayMtl",
            name="Material",
            sub_textures=(
                GraphLink(5, "Reflection roughness", "tex_1"),
            ),
        )
        self.assertEqual(
            find_texture_link(node, "Reflection-Roughness").ref,
            "tex_1",
        )
        self.assertEqual(canonical_name("Self-illumination"), "selfillumination")

    def test_map_multiplier_and_enable_use_exporter_parameter_names(self):
        parameters = {
            "texmap_reflectionGlossiness_on": True,
            "texmap_reflectionGlossiness_multiplier": 35.0,
        }
        self.assertTrue(map_is_enabled(parameters, "Reflection roughness"))
        self.assertAlmostEqual(map_amount(parameters, "Reflection roughness"), 0.35)

    def test_map_multiplier_is_clamped(self):
        self.assertEqual(map_amount({"texmap_bump_multiplier": -20}, "Bump"), 0.0)
        self.assertEqual(map_amount({"texmap_bump_multiplier": 500}, "Bump"), 1.0)

    def test_glossiness_converts_to_roughness_unless_roughness_mode_is_on(self):
        self.assertAlmostEqual(vray_roughness({"reflection_glossiness": 0.8}), 0.2)
        self.assertAlmostEqual(
            vray_roughness(
                {"reflection_glossiness": 0.8, "brdf_useRoughness": True}
            ),
            0.8,
        )

    def test_physical_material_roughness_honors_the_invert_checkbox(self):
        self.assertAlmostEqual(physical_roughness({"roughness": 0.2}), 0.2)
        self.assertAlmostEqual(
            physical_roughness({"roughness": 0.2, "roughness_inv": True}),
            0.8,
        )
        self.assertAlmostEqual(
            physical_roughness(
                {"coat_roughness": 0.75, "coat_roughness_inv": True},
                "coat_roughness",
            ),
            0.25,
        )

    def test_physical_material_map_enable_uses_actual_max_slot_names(self):
        parameters = {
            "base_color_map_on": False,
            "roughness_map_on": True,
            "bump_map_on": False,
        }
        self.assertFalse(physical_map_is_enabled(parameters, "Base Color Map"))
        self.assertTrue(physical_map_is_enabled(parameters, "Roughness Map"))
        self.assertFalse(physical_map_is_enabled(parameters, "Bump Map"))
        self.assertTrue(physical_map_is_enabled(parameters, "Unknown Map"))

    def test_rgba_is_clamped_and_supplies_alpha(self):
        self.assertEqual(rgba([1.2, -1, 0.5]), (1.0, 0.0, 0.5, 1.0))


if __name__ == "__main__":
    unittest.main()
