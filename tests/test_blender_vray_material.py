from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from blendmax_blender.models import GraphNode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeTree, load_materials_module


def extract_vray_parameter_lookups():
    """Collect every literal parameter key the VRayMtl path can read.

    Walks `_build_vray_mtl` and the four `vray_*` helper functions and
    returns the set of string keys passed to `parameters.get(...)`,
    `scalar(parameters, ...)`, or `parameters[...]`. Slot/map lookups that
    take a dynamic key (e.g. `map_amount(parameters, link.slot)`) are not
    literals and are therefore intentionally excluded.
    """
    repo = Path(__file__).resolve().parents[1]

    def collect(path, func_names):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in func_names:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        func = sub.func
                        if (
                            isinstance(func, ast.Name)
                            and func.id == "scalar"
                            and len(sub.args) >= 2
                        ):
                            arg = sub.args[1]
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                found.add(arg.value)
                        elif (
                            isinstance(func, ast.Attribute)
                            and func.attr == "get"
                            and isinstance(func.value, ast.Name)
                            and func.value.id == "parameters"
                            and sub.args
                        ):
                            arg = sub.args[0]
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                found.add(arg.value)
                    if isinstance(sub, ast.Subscript):
                        if (
                            isinstance(sub.value, ast.Name)
                            and sub.value.id == "parameters"
                            and isinstance(sub.slice, ast.Constant)
                            and isinstance(sub.slice.value, str)
                        ):
                            found.add(sub.slice.value)
        return found

    keys = collect(
        repo / "blendmax_blender" / "blender_materials.py",
        {"_build_vray_mtl"},
    )
    keys |= collect(
        repo / "blendmax_blender" / "material_graph.py",
        {"vray_roughness", "vray_anisotropy", "vray_sheen_roughness", "vray_thin_film"},
    )
    return keys


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

    def test_known_unmapped_parameters_are_silent(self):
        graph_node = GraphNode(
            node_id="mat_known_unmapped",
            kind="material",
            class_name="VRayMtl",
            name="Known unmapped material",
            parameters={
                "Diffuse": [0.8, 0.8, 0.8, 1.0],
                "reflection_glossiness": 0.5,
                "anisotropy_axis": 2,
                "coat_darkening": 0.4,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)
        self.assertEqual(warnings, [])

    def test_unknown_unmapped_parameters_are_still_reported(self):
        graph_node = GraphNode(
            node_id="mat_unknown_unmapped",
            kind="material",
            class_name="VRayMtl",
            name="Unknown unmapped material",
            parameters={
                "Diffuse": [0.8, 0.8, 0.8, 1.0],
                "vray_future_parameter": 123,
            },
        )
        _builder, warnings, _tree, _shader = self.build(graph_node)

        self.assertEqual(
            warnings,
            [
                "VRayMtl parameter 'vray_future_parameter' has no Blender mapping yet; "
                "its value remains in the stored manifest."
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

    def test_duplicate_unmapped_parameters_are_silent_across_materials(self):
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

        self.assertEqual(warnings, [])


class VRayExporterContractTests(unittest.TestCase):
    """Cross-check the importer's parameter vocabulary against the exporter's.

    The exporter only stores VRayMtl properties that are listed in
    `VRAY_MTL_PROPERTIES` (plus `texmap_*` map controls for connected slots),
    so these tests guard both directions of the name contract without needing
    a running 3ds Max or Blender.
    """

    @classmethod
    def setUpClass(cls):
        cls.materials = load_materials_module()
        from blendmax_max.max_adapter import VRAY_MTL_PROPERTIES

        cls.VRAY_MTL_PROPERTIES = VRAY_MTL_PROPERTIES

    def build(self, graph_node):
        warnings = []
        builder = self.materials.MaterialBuilder(
            SimpleNamespace(node=lambda ref: graph_node if ref == graph_node.node_id else None),
            Path("."),
            warnings,
        )
        builder._build_shader(FakeTree(), graph_node.node_id, SimpleNamespace(), (), 0.0, 0.0)
        return warnings

    def test_every_vray_parameter_lookup_is_exporter_reachable(self):
        keys = extract_vray_parameter_lookups()
        # Sanity: the extractor must actually find the known lookups, so a
        # refactor that renames a function cannot silently empty the set.
        self.assertGreater(len(keys), 20)
        self.assertIn("reflection_glossiness", keys)

        whitelist = {name.casefold() for name in self.VRAY_MTL_PROPERTIES}
        for key in sorted(keys):
            folded = key.casefold()
            self.assertTrue(
                folded in whitelist or folded.startswith("texmap_"),
                "Importer lookup {0!r} is not reachable from the exporter.".format(key),
            )

    def test_full_whitelist_reads_expected_parameters(self):
        graph_node = GraphNode(
            node_id="mat_full",
            kind="material",
            class_name="VRayMtl",
            name="Full whitelist",
            parameters={name: None for name in self.VRAY_MTL_PROPERTIES},
        )
        warnings = self.build(graph_node)

        mapped = {
            "Diffuse",
            "Reflection",
            "Refraction",
            "selfIllumination",
            "selfIllumination_multiplier",
            "reflection_metalness",
            "reflection_glossiness",
            "reflection_IOR",
            "refraction_ior",
            "reflection_weight",
            "reflection_lockIOR",
            "coat_amount",
            "coat_color",
            "coat_glossiness",
            "coat_ior",
            "diffuse_roughness",
            "refraction_thinwalled",
            "anisotropy",
            "anisotropy_rotation",
            "sheen_color",
            "sheen_glossiness",
            "thinfilm_on",
            "thinfilm_ior",
            "thinfilm_thickness_min",
            "thinfilm_thickness_max",
            "brdf_useRoughness",
            "refraction_glossiness",
        }
        for name in mapped:
            self.assertFalse(
                any("'{0}'".format(name.casefold()) in message for message in warnings),
                "{0} should be mapped but was reported unmapped".format(name),
            )

        known_unmapped = {
            "anisotropy_axis",
            "coat_darkening",
            "option_cutoff",
            "reflection_fresnel",
            "refraction_dispersion",
            "selfillumination_gi",
            "translucency_amount",
        }
        for name in known_unmapped:
            self.assertFalse(
                any("'{0}'".format(name.casefold()) in message for message in warnings),
                "{0} is intentionally unsupported and should stay silent".format(name),
            )


if __name__ == "__main__":
    unittest.main()
