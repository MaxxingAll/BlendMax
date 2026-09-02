from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from blendmax_blender.models import GraphLink, GraphNode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeSocket, FakeTree, load_materials_module


class BlenderPhysicalMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = load_materials_module()

    def builder_for(self, graph_node):
        index = SimpleNamespace(node=lambda ref: graph_node if ref == graph_node.node_id else None)
        warnings = []
        builder = self.materials.MaterialBuilder(index, Path("."), warnings)
        return builder, warnings

    def test_physical_material_dispatches_to_principled_without_fallback_warning(self):
        graph_node = GraphNode(
            node_id="mat_ring",
            kind="material",
            class_name="PhysicalMaterial",
            name="Ring metal",
            parameters={
                "base_color": [0.2, 0.3, 0.4, 1.0],
                "base_weight": 0.9,
                "roughness": 0.0,
                "roughness_inv": True,
                "metalness": 0.7,
                "reflectivity": 1.0,
                "transparency": 0.0,
                "trans_ior": 1.52,
                "coating": 0.25,
                "coat_roughness": 0.2,
                "thin_walled": True,
                "emission": 0.0,
            },
        )
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

        principled = tree.nodes.created[0]
        self.assertIs(shader, principled.outputs[0])
        self.assertEqual(warnings, [])
        self.assertEqual(
            principled.inputs["Base Color"].default_value,
            (0.2, 0.3, 0.4, 1.0),
        )
        self.assertAlmostEqual(principled.inputs["Base Weight"].default_value, 0.9)
        self.assertAlmostEqual(principled.inputs["Metallic"].default_value, 0.7)
        self.assertAlmostEqual(principled.inputs["Roughness"].default_value, 1.0)
        self.assertAlmostEqual(principled.inputs["IOR"].default_value, 1.52)
        self.assertAlmostEqual(
            principled.inputs["Specular IOR Level"].default_value,
            0.5,
        )
        self.assertAlmostEqual(principled.inputs["Coat Weight"].default_value, 0.25)
        self.assertTrue(principled.inputs["Thin Wall"].default_value)

    def test_physical_base_color_map_links_to_principled_base_color(self):
        graph_node = GraphNode(
            node_id="mat_bitmap",
            kind="material",
            class_name="Physical_Material",
            name="Mapped physical material",
            parameters={
                "base_color": [0.5, 0.5, 0.5, 1.0],
                "base_color_map_on": True,
            },
            sub_textures=(GraphLink(2, "Base Color Map", "tex_color"),),
        )
        builder, warnings = self.builder_for(graph_node)
        texture_output = FakeSocket("Texture Color")
        builder._texture_output = lambda *_args, **_kwargs: texture_output
        tree = FakeTree()

        builder._build_shader(
            tree,
            graph_node.node_id,
            SimpleNamespace(),
            (),
            0.0,
            0.0,
        )

        principled = tree.nodes.created[0]
        self.assertIn(
            (texture_output, principled.inputs["Base Color"]),
            tree.links.created,
        )
        self.assertEqual(warnings, [])

    def test_disabled_physical_base_color_map_is_not_linked(self):
        graph_node = GraphNode(
            node_id="mat_disabled",
            kind="material",
            class_name="PhysicalMaterial",
            name="Disabled map",
            parameters={"base_color_map_on": False},
            sub_textures=(GraphLink(2, "Base Color Map", "tex_color"),),
        )
        builder, warnings = self.builder_for(graph_node)
        builder._texture_output = lambda *_args, **_kwargs: FakeSocket("Texture Color")
        tree = FakeTree()

        builder._build_shader(
            tree,
            graph_node.node_id,
            SimpleNamespace(),
            (),
            0.0,
            0.0,
        )

        principled = tree.nodes.created[0]
        self.assertFalse(
            any(target is principled.inputs["Base Color"] for _, target in tree.links.created)
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
