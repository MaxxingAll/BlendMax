from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from blendmax_blender.models import GraphLink, GraphNode


class FakeSocket:
    def __init__(self, name):
        self.name = name
        self.identifier = name
        self.default_value = None


class FakeSockets:
    def __init__(self, names):
        self._items = [FakeSocket(name) for name in names]

    def get(self, name):
        return next((item for item in self._items if item.name == name), None)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        found = self.get(key)
        if found is None:
            raise KeyError(key)
        return found


class FakeNode:
    PRINCIPLED_INPUTS = (
        "Base Color",
        "Base Weight",
        "Metallic",
        "Roughness",
        "IOR",
        "Specular IOR Level",
        "Specular Tint",
        "Transmission Weight",
        "Alpha",
        "Thin Wall",
        "Diffuse Roughness",
        "Anisotropic IOR Level",
        "Anisotropic Rotation",
        "Coat Weight",
        "Coat Roughness",
        "Coat IOR",
        "Coat Tint",
        "Sheen Weight",
        "Sheen Roughness",
        "Sheen Tint",
        "Subsurface Weight",
        "Emission Color",
        "Emission Strength",
        "Thin Film Thickness",
        "Thin Film IOR",
        "Normal",
    )

    def __init__(self, node_type):
        self.type = node_type
        self.label = ""
        self.location = (0.0, 0.0)
        if node_type == "ShaderNodeBsdfPrincipled":
            self.inputs = FakeSockets(self.PRINCIPLED_INPUTS)
            self.outputs = FakeSockets(("BSDF",))
        elif node_type == "ShaderNodeRGBToBW":
            self.inputs = FakeSockets(("Color",))
            self.outputs = FakeSockets(("Val",))
        elif node_type == "ShaderNodeMath":
            self.inputs = FakeSockets(("Value", "Value_001", "Value_002"))
            self.outputs = FakeSockets(("Value",))
            self.operation = ""
        else:
            raise AssertionError("Unexpected fake node type: {0}".format(node_type))


class FakeNodes:
    def __init__(self):
        self.created = []

    def new(self, node_type):
        node = FakeNode(node_type)
        self.created.append(node)
        return node


class FakeLinks:
    def __init__(self):
        self.created = []

    def new(self, output, target):
        self.created.append((output, target))


class FakeTree:
    def __init__(self):
        self.nodes = FakeNodes()
        self.links = FakeLinks()


def load_materials_module():
    fake_bpy = ModuleType("bpy")
    module_path = (
        Path(__file__).resolve().parents[1]
        / "blendmax_blender"
        / "blender_materials.py"
    )
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._physical_material_test",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load BlendMax material builder test module.")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"bpy": fake_bpy}):
        spec.loader.exec_module(module)
    return module


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
