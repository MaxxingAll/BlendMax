from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from blendmax_blender.models import GraphNode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeTree, load_materials_module


class BlenderVRayMtlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = load_materials_module()

    def builder_for(self, graph_node):
        index = SimpleNamespace(node=lambda ref: graph_node if ref == graph_node.node_id else None)
        warnings = []
        builder = self.materials.MaterialBuilder(index, Path("."), warnings)
        return builder, warnings

    def build(self, graph_node):
        builder, warnings = self.builder_for(graph_node)
        tree = FakeTree()
        shader = builder._build_shader(
            tree,
            graph_node.node_id,
            SimpleNamespace(),
            (),
            0.0,
            0.0,
        )
        return builder, warnings, tree, shader

    def test_parameter_lookup_is_case_insensitive(self):
        graph_node = GraphNode(
            node_id="mat_cased",
            kind="material",
            class_name="VRayMtl",
            name="Cased material",
            parameters={
                "DIFFUSE": [1.0, 0.0, 0.0, 1.0],
                "Reflection_Glossiness": 0.7,
                "Reflection_IOR": 1.6,
                "brdf_UseRoughness": True,
            },
        )
        _builder, warnings, tree, _shader = self.build(graph_node)

        principled = tree.nodes.created[0]
        self.assertEqual(
            principled.inputs["Base Color"].default_value,
            (1.0, 0.0, 0.0, 1.0),
        )
        # Glossiness is respected as roughness mode and honored verbatim.
        self.assertAlmostEqual(principled.inputs["Roughness"].default_value, 0.7)
        self.assertAlmostEqual(principled.inputs["IOR"].default_value, 1.6)
        self.assertEqual(warnings, [])

    def test_unmapped_parameters_are_reported_once_each(self):
        graph_node = GraphNode(
            node_id="mat_unmapped",
            kind="material",
            class_name="VRayMtl",
            name="Unmapped material",
            parameters={
                "Diffuse": [0.8, 0.8, 0.8, 1.0],
                "reflection_glossiness": 0.5,
                "anisotropy_axis": 2,
                "coat_darkening": 0.4,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)

        self.assertEqual(
            warnings,
            [
                "VRayMtl parameter 'anisotropy_axis' has no Blender mapping yet; "
                "its value remains in the stored manifest.",
                "VRayMtl parameter 'coat_darkening' has no Blender mapping yet; "
                "its value remains in the stored manifest.",
            ],
        )

    def test_surface_parameters_map_to_principled_defaults(self):
        graph_node = GraphNode(
            node_id="mat_surface",
            kind="material",
            class_name="VRayMtl",
            name="Surface material",
            parameters={
                "anisotropy": -0.6,
                "anisotropy_rotation": 0.5,
                "sheen_color": [1.0, 0.0, 0.0, 1.0],
                "sheen_glossiness": 0.8,
                "thinfilm_on": True,
                "thinfilm_ior": 1.4,
                "thinfilm_thickness_min": 300.0,
                "thinfilm_thickness_max": 600.0,
            },
        )
        _builder, warnings, tree, _shader = self.build(graph_node)

        principled = tree.nodes.created[0]
        self.assertAlmostEqual(principled.inputs["Anisotropic IOR Level"].default_value, 0.6)
        self.assertAlmostEqual(principled.inputs["Anisotropic Rotation"].default_value, 0.75)
        self.assertAlmostEqual(principled.inputs["Sheen Weight"].default_value, 0.2126)
        self.assertAlmostEqual(principled.inputs["Sheen Roughness"].default_value, 0.2)
        self.assertEqual(principled.inputs["Sheen Tint"].default_value, (1.0, 0.0, 0.0, 1.0))
        self.assertAlmostEqual(principled.inputs["Thin Film IOR"].default_value, 1.4)
        self.assertAlmostEqual(principled.inputs["Thin Film Thickness"].default_value, 300.0)
        self.assertEqual(warnings, [])

    def test_thin_film_off_maps_to_zero_thickness_without_warning(self):
        graph_node = GraphNode(
            node_id="mat_nofilm",
            kind="material",
            class_name="VRayMtl",
            name="No film",
            parameters={
                "thinfilm_on": False,
                "thinfilm_ior": 1.4,
                "thinfilm_thickness_min": 300.0,
                "thinfilm_thickness_max": 600.0,
            },
        )
        _builder, warnings, tree, _shader = self.build(graph_node)

        principled = tree.nodes.created[0]
        self.assertAlmostEqual(principled.inputs["Thin Film Thickness"].default_value, 0.0)
        self.assertAlmostEqual(principled.inputs["Thin Film IOR"].default_value, 1.4)
        self.assertEqual(warnings, [])

    def test_coat_tint_diffuse_roughness_and_thin_wall_map_directly(self):
        graph_node = GraphNode(
            node_id="mat_direct",
            kind="material",
            class_name="VRayMtl",
            name="Direct mappings",
            parameters={
                "coat_color": [1.0, 0.0, 0.0, 1.0],
                "diffuse_roughness": 0.35,
                "refraction": [1.0, 1.0, 1.0, 1.0],
                "refraction_thinwalled": True,
                "refraction_glossiness": 1.0,
            },
        )
        _builder, warnings, tree, _shader = self.build(graph_node)

        principled = tree.nodes.created[0]
        self.assertEqual(
            principled.inputs["Coat Tint"].default_value,
            (1.0, 0.0, 0.0, 1.0),
        )
        self.assertAlmostEqual(principled.inputs["Diffuse Roughness"].default_value, 0.35)
        self.assertTrue(principled.inputs["Thin Wall"].default_value)
        self.assertEqual(warnings, [])

    def test_divergent_refraction_glossiness_warns(self):
        graph_node = GraphNode(
            node_id="mat_frosted",
            kind="material",
            class_name="VRayMtl",
            name="Frosted glass",
            parameters={
                "refraction": [1.0, 1.0, 1.0, 1.0],
                "reflection_glossiness": 0.9,
                "refraction_glossiness": 0.3,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)

        self.assertEqual(len(warnings), 1)
        self.assertIn("refraction roughness is approximated", warnings[0])

    def test_matching_refraction_glossiness_does_not_warn(self):
        graph_node = GraphNode(
            node_id="mat_matching",
            kind="material",
            class_name="VRayMtl",
            name="Matching glass",
            parameters={
                "refraction": [1.0, 1.0, 1.0, 1.0],
                "reflection_glossiness": 0.8,
                "refraction_glossiness": 0.8,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)
        self.assertEqual(warnings, [])

    def test_texmap_controls_are_not_reported_as_unmapped(self):
        graph_node = GraphNode(
            node_id="mat_texmap_controls",
            kind="material",
            class_name="VRayMtl",
            name="Texture controls",
            parameters={
                "Diffuse": [0.8, 0.8, 0.8, 1.0],
                "texmap_diffuse_multiplier": 65.0,
                "texmap_reflectionGlossiness_on": True,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)
        self.assertEqual(warnings, [])

    def test_duplicate_unmapped_parameters_are_deduplicated_across_materials(self):
        builder, warnings = self.builder_for(
            GraphNode(node_id="x", kind="material", class_name="VRayMtl", name="x")
        )
        builder.index = SimpleNamespace(
            node=lambda ref: (
                GraphNode(
                    node_id="m1",
                    kind="material",
                    class_name="VRayMtl",
                    name="m1",
                    parameters={"anisotropy_axis": 0},
                )
                if ref == "m1"
                else GraphNode(
                    node_id="m2",
                    kind="material",
                    class_name="VRayMtl",
                    name="m2",
                    parameters={"anisotropy_axis": 1},
                )
                if ref == "m2"
                else None
            )
        )
        for ref in ("m1", "m2"):
            builder._build_shader(FakeTree(), ref, SimpleNamespace(), (), 0.0, 0.0)

        anisotropy_warnings = [
            message for message in warnings if "anisotropy_axis" in message
        ]
        self.assertEqual(len(anisotropy_warnings), 1)


if __name__ == "__main__":
    unittest.main()
