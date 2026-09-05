from __future__ import annotations

import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from blendmax_blender.models import ImportSummary


class FakeSocket:
    def __init__(self, name, default_value=0.0, is_linked=False):
        self.name = name
        self.identifier = name
        self.default_value = default_value
        self.is_linked = is_linked


class FakeSockets:
    def __init__(self, sockets):
        self._items = {socket.name: socket for socket in sockets}

    def get(self, name):
        return self._items.get(name)

    def __getitem__(self, name):
        return self._items[name]


class FakeMaterial(dict):
    pass


class PhysicalMaterialIntegrationTests(unittest.TestCase):
    def _load_integration(self):
        fake_bpy = ModuleType("bpy")
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            sys.modules.pop("blendmax_blender.physical_material_integration", None)
            return importlib.import_module("blendmax_blender.physical_material_integration")

    def test_install_patches_builder_once_and_is_idempotent(self):
        integration = self._load_integration()
        materials = importlib.import_module("blendmax_blender.blender_materials")

        original = materials.MaterialBuilder._build_physical_mtl
        integration._PATCHED = False
        integration._ORIGINAL = None
        try:
            integration.install()
            self.assertTrue(integration._PATCHED)
            self.assertIs(integration._ORIGINAL, original)
            patched = materials.MaterialBuilder._build_physical_mtl
            self.assertIs(patched, integration._apply_physical_fidelity)

            integration.install()
            self.assertIs(materials.MaterialBuilder._build_physical_mtl, patched)
            self.assertIs(integration._ORIGINAL, original)
        finally:
            materials.MaterialBuilder._build_physical_mtl = original
            integration._PATCHED = False
            integration._ORIGINAL = None

    def test_wrapper_applies_fidelity_without_rebuilding_shader(self):
        integration = self._load_integration()

        bsdf = SimpleNamespace(
            inputs=FakeSockets(
                [
                    FakeSocket("Base Color", (0.25, 0.5, 0.75, 1.0)),
                    FakeSocket("Roughness", 0.4),
                    FakeSocket("Emission Strength", 1.0),
                ]
            )
        )
        output = SimpleNamespace(node=bsdf)
        material = FakeMaterial()
        graph_node = SimpleNamespace(
            parameters={
                "coating": 1.0,
                "coat_affect_color": 0.5,
                "trans_roughness_lock": False,
                "trans_roughness": 0.2,
                "trans_roughness_inv": True,
                "trans_depth": 4.0,
                "sss_color": [0.8, 0.4, 0.2, 1.0],
                "sss_scatter_color": [0.9, 0.2, 0.1, 1.0],
                "sss_depth": 6.0,
                "sss_scale": 0.5,
                "emission": 0.5,
                "emit_luminance": 1200.0,
                "emit_kelvin": 6500.0,
            }
        )

        calls = []

        def original(self, tree, node, mat, stack, x, y):
            calls.append((tree, node, mat, stack, x, y))
            return output

        integration._ORIGINAL = original
        result = integration._apply_physical_fidelity(
            object(), "tree", graph_node, material, (), 10, 20
        )

        self.assertIs(result, output)
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(bsdf.inputs["Roughness"].default_value, 0.4)
        self.assertEqual(material["blendmax_transparency_roughness"], 0.8)
        self.assertEqual(material["blendmax_transparency_depth_inverse"], 0.25)
        self.assertEqual(material["blendmax_sss_depth"], 3.0)
        self.assertEqual(material["blendmax_sss_scatter_color"], (0.9, 0.2, 0.1))
        self.assertEqual(material["blendmax_emission_luminance_nits"], 600.0)
        self.assertEqual(material["blendmax_emission_kelvin"], 6500.0)
        self.assertAlmostEqual(bsdf.inputs["Emission Strength"].default_value, 600.0)
        self.assertAlmostEqual(bsdf.inputs["Base Color"].default_value[0], 0.5)
        self.assertAlmostEqual(bsdf.inputs["Base Color"].default_value[1], 0.7071067812)
        self.assertAlmostEqual(bsdf.inputs["Base Color"].default_value[2], 0.8660254038)

    def test_import_path_installs_before_package_and_adapter_work(self):
        fake_bpy = ModuleType("bpy")
        fake_bpy.context = object()
        events = []

        fake_adapter_module = ModuleType("blendmax_blender.blender_adapter")

        class FakeAdapter:
            def __init__(self, context):
                events.append(("adapter", context))

            def import_package(self, package, apply_recommended_scale=True):
                events.append(("import", package, apply_recommended_scale))
                return ImportSummary(
                    asset_name="asset",
                    object_count=1,
                    material_count=1,
                    image_count=0,
                    warnings=(),
                    notes=(),
                )

        fake_adapter_module.BlenderAdapter = FakeAdapter
        fake_package_module = ModuleType("blendmax_blender.package")

        class FakePackageContext:
            def __enter__(self):
                events.append(("open",))
                return SimpleNamespace(manifest=SimpleNamespace(graph=()))

            def __exit__(self, *args):
                events.append(("close",))

        fake_package_module.open_blendmax = lambda path: FakePackageContext()

        def record_install():
            events.append(("install",))

        with patch.dict(
            sys.modules,
            {
                "bpy": fake_bpy,
                "blendmax_blender.blender_adapter": fake_adapter_module,
                "blendmax_blender.package": fake_package_module,
            },
        ), patch(
            "blendmax_blender.physical_material_integration.install",
            side_effect=record_install,
        ):
            importer = importlib.reload(importlib.import_module("blendmax_blender.importer"))
            importer.import_blendmax("asset.blendmax")

        self.assertEqual(
            [event[0] for event in events],
            ["install", "open", "adapter", "import", "close"],
        )


if __name__ == "__main__":
    unittest.main()
