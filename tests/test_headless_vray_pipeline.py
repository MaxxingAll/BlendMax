"""Headless integration tests for simulated 3ds Max/V-Ray material captures.

These fixtures represent the manifest payload that BlendMax's Max exporter
would hand to the Blender importer. The tests deliberately run with ordinary
Python and a fake bpy shader tree, covering manifest parsing -> ManifestIndex
-> VRayMtl dispatch -> Principled defaults without launching 3ds Max, V-Ray or
Blender.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from blendmax_blender.manifest import ManifestIndex, parse_manifest
from blendmax_blender.material_graph import find_texture_link, map_amount, map_is_enabled
from fakes import FakeTree, load_materials_module


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name):
    return parse_manifest(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


class HeadlessVRayPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = load_materials_module()

    def build_fixture(self, name):
        manifest = load_fixture(name)
        index = ManifestIndex(manifest)
        assignment = manifest.assignments[0]
        warnings = []
        builder = self.materials.MaterialBuilder(index, Path("."), warnings)
        tree = FakeTree()
        shader = builder._build_shader(
            tree,
            assignment.material_ref,
            SimpleNamespace(),
            (),
            0.0,
            0.0,
        )
        return manifest, index, warnings, tree, shader

    def test_basic_fixture_reaches_vray_builder_from_manifest(self):
        manifest, index, warnings, tree, _shader = self.build_fixture("vraymtl_basic.json")

        self.assertEqual(manifest.asset_name, "Headless Basic VRayMtl")
        self.assertEqual(index.assignments_by_object["obj_basic"].material_ref, "mat_basic")
        self.assertEqual(index.node("mat_basic").class_name, "VRayMtl")

        principled = tree.nodes.created[0]
        self.assertEqual(principled.label, "Basic Chrome")
        self.assertEqual(principled.inputs["Base Color"].default_value, (0.18, 0.2, 0.22, 1.0))
        self.assertAlmostEqual(principled.inputs["Metallic"].default_value, 0.65)
        self.assertAlmostEqual(principled.inputs["Roughness"].default_value, 0.35)
        self.assertAlmostEqual(principled.inputs["IOR"].default_value, 1.62)
        self.assertEqual(warnings, [])

    def test_surface_fixture_exercises_pending_vray_conversions(self):
        _manifest, _index, warnings, tree, _shader = self.build_fixture("vraymtl_surface.json")
        principled = tree.nodes.created[0]

        self.assertAlmostEqual(principled.inputs["Anisotropic IOR Level"].default_value, 0.6)
        self.assertAlmostEqual(principled.inputs["Anisotropic Rotation"].default_value, 0.75)
        self.assertAlmostEqual(principled.inputs["Sheen Weight"].default_value, 0.2126)
        self.assertAlmostEqual(principled.inputs["Sheen Roughness"].default_value, 0.2)
        self.assertEqual(principled.inputs["Sheen Tint"].default_value, (1.0, 0.0, 0.0, 1.0))
        self.assertAlmostEqual(principled.inputs["Thin Film IOR"].default_value, 1.4)
        self.assertAlmostEqual(principled.inputs["Thin Film Thickness"].default_value, 300.0)
        self.assertEqual(principled.inputs["Coat Tint"].default_value, (0.2, 0.4, 0.6, 1.0))
        self.assertAlmostEqual(principled.inputs["Diffuse Roughness"].default_value, 0.35)
        self.assertTrue(principled.inputs["Thin Wall"].default_value)
        self.assertTrue(any("refraction roughness is approximated" in item for item in warnings))

    def test_map_fixture_parses_links_and_exporter_controls(self):
        manifest = load_fixture("vraymtl_maps.json")
        index = ManifestIndex(manifest)
        material = index.node("mat_maps")

        self.assertEqual(manifest.schema_version, "0.1.1")
        self.assertEqual(len(material.sub_textures), 5)
        self.assertEqual(find_texture_link(material, "Diffuse").ref, "tex_diffuse")
        self.assertEqual(find_texture_link(material, "Reflection roughness").ref, "tex_gloss")
        self.assertFalse(map_is_enabled(material.parameters, "Refraction"))
        self.assertTrue(map_is_enabled(material.parameters, "Diffuse"))
        self.assertAlmostEqual(map_amount(material.parameters, "Diffuse"), 0.65)
        self.assertAlmostEqual(map_amount(material.parameters, "Reflection"), 0.25)
        self.assertAlmostEqual(map_amount(material.parameters, "Bump"), 1.0)
        self.assertEqual(index.node("tex_diffuse").parameters["path"], "textures/albedo.png")
        self.assertEqual(index.node("tex_bump").parameters["path"], "textures/bump.png")
        self.assertEqual(index.textures_by_graph_node["tex_gloss"].package_path, "textures/gloss.png")

    def test_fixture_preserves_unmapped_parameters_for_diagnostics(self):
        raw = json.loads((FIXTURES / "vraymtl_basic.json").read_text(encoding="utf-8"))
        raw["materials"]["graph"][0]["parameters"]["future_vray_parameter"] = 123
        manifest = parse_manifest(raw)
        index = ManifestIndex(manifest)
        warnings = []
        builder = self.materials.MaterialBuilder(index, Path("."), warnings)
        builder._build_shader(FakeTree(), "mat_basic", SimpleNamespace(), (), 0.0, 0.0)
        self.assertTrue(any("future_vray_parameter" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
