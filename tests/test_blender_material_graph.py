from __future__ import annotations

import unittest

from blendmax_blender.material_graph import (
    ParameterView,
    canonical_name,
    find_texture_link,
    map_amount,
    map_is_enabled,
    physical_map_is_enabled,
    physical_roughness,
    rgba,
    vray_anisotropy,
    vray_roughness,
    vray_sheen_roughness,
    vray_thin_film,
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

    def test_vray_anisotropy_magnitude_and_rotation(self):
        magnitude, rotation = vray_anisotropy({"anisotropy": 0.4, "anisotropy_rotation": 0.3})
        self.assertAlmostEqual(magnitude, 0.4)
        self.assertAlmostEqual(rotation, 0.3)

    def test_negative_vray_anisotropy_adds_a_quarter_turn(self):
        magnitude, rotation = vray_anisotropy({"anisotropy": -0.6, "anisotropy_rotation": 0.5})
        self.assertAlmostEqual(magnitude, 0.6)
        self.assertAlmostEqual(rotation, 0.75)

    def test_vray_anisotropy_rotation_wraps_past_one(self):
        _magnitude, rotation = vray_anisotropy({"anisotropy": -1.0, "anisotropy_rotation": 0.9})
        self.assertAlmostEqual(rotation, 0.15)

    def test_vray_sheen_glossiness_inverts_to_roughness(self):
        self.assertAlmostEqual(vray_sheen_roughness({"sheen_glossiness": 0.8}), 0.2)
        self.assertAlmostEqual(vray_sheen_roughness({}), 0.2)

    def test_vray_thin_film_uses_minimum_when_enabled(self):
        ior, thickness = vray_thin_film(
            {
                "thinfilm_on": True,
                "thinfilm_ior": 1.4,
                "thinfilm_thickness_min": 300.0,
                "thinfilm_thickness_max": 600.0,
            }
        )
        self.assertAlmostEqual(ior, 1.4)
        self.assertAlmostEqual(thickness, 300.0)

    def test_vray_thin_film_disabled_maps_to_zero(self):
        ior, thickness = vray_thin_film(
            {
                "thinfilm_on": False,
                "thinfilm_ior": 1.4,
                "thinfilm_thickness_min": 300.0,
            }
        )
        self.assertAlmostEqual(ior, 1.4)
        self.assertAlmostEqual(thickness, 0.0)

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


class ParameterViewTests(unittest.TestCase):
    def test_lookup_is_case_insensitive_but_spelling_sensitive(self):
        view = ParameterView({"Reflection_Glossiness": 0.3})
        self.assertEqual(view.get("reflection_glossiness"), 0.3)
        self.assertEqual(view.get("REFLECTION_GLOSSINESS"), 0.3)
        self.assertEqual(view["Reflection_Glossiness"], 0.3)

    def test_punctuation_variants_are_not_silently_matched(self):
        view = ParameterView({"Reflection_Glossiness": 0.3})
        self.assertIsNone(view.get("reflection glossiness"))
        self.assertIsNone(view.get("reflection-glossiness"))
        self.assertIsNone(view.get("reflectionglossiness"))

    def test_explicit_alias_resolves_known_spelling_variants(self):
        view = ParameterView(
            {"Diffuse": [0.5, 0.5, 0.5, 1.0]},
            aliases={"diffuse color": "diffuse"},
        )
        self.assertEqual(view.get("Diffuse Color"), [0.5, 0.5, 0.5, 1.0])
        self.assertEqual(view.accessed, {"diffuse"})

    def test_alias_does_not_record_access_for_a_missing_target(self):
        view = ParameterView({}, aliases={"diffuse color": "diffuse"})
        self.assertIsNone(view.get("Diffuse Color"))
        self.assertFalse(view.accessed)

    def test_missing_key_returns_default_without_recording_access(self):
        view = ParameterView({})
        self.assertIsNone(view.get("anything"))
        self.assertFalse(view.accessed)

    def test_accessed_and_unmapped_track_reads(self):
        view = ParameterView(
            {
                "Diffuse": [1.0, 1.0, 1.0, 1.0],
                "anisotropy": 0.5,
                "coat_color": [0.0, 0.0, 0.0, 1.0],
            }
        )
        self.assertEqual(view.get("diffuse"), [1.0, 1.0, 1.0, 1.0])
        self.assertEqual(view.accessed, {"diffuse"})
        self.assertEqual(view.unmapped_keys(), ("anisotropy", "coat_color"))

    def test_unmapped_keys_are_sorted(self):
        view = ParameterView({"b": 1, "a": 2, "c": 3})
        self.assertEqual(view.unmapped_keys(), ("a", "b", "c"))

    def test_original_key_preserves_manifest_casing(self):
        view = ParameterView({"Reflection_Glossiness": 0.3})
        self.assertEqual(
            view.original_key("reflection_glossiness"),
            "Reflection_Glossiness",
        )


if __name__ == "__main__":
    unittest.main()
