from __future__ import annotations

import unittest

from blendmax_max.max_adapter import MaxRuntimeAdapter


class FakeColor:
    r = 255.0
    g = 127.5
    b = 0.0
    a = 255.0


class FakeUnits:
    DisplayType = "Generic"

    @staticmethod
    def decodeValue(value):
        return 1000.0


class FakeRenderers:
    current = object()


class FakeRuntime:
    undefined = object()
    units = FakeUnits()
    renderers = FakeRenderers()
    VRayMtl = object()
    maxFileName = "Example.max"

    @staticmethod
    def maxVersion():
        return [27000, 66, 0, 27, 3, 0, 30874, 2025, ".3"]

    @staticmethod
    def vrayVersion():
        return "V-Ray 7.40.02 for x64"

    @staticmethod
    def classOf(value):
        if isinstance(value, FakeColor):
            return "Color"
        return "V_Ray_7__update_4"


class MaxAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MaxRuntimeAdapter(runtime=FakeRuntime())

    def test_normalizes_max_color_to_zero_one(self):
        supported, value = self.adapter._primitive_value(FakeColor())
        self.assertTrue(supported)
        self.assertEqual(value, [1.0, 0.5, 0.0, 1.0])

    def test_detects_target_environment(self):
        metadata = self.adapter.source_metadata()
        self.assertEqual(metadata["max_version"], "2025.3")
        self.assertEqual(metadata["vray"]["version"], "V-Ray 7.40.02 for x64")
        self.assertTrue(metadata["compatibility"]["max_matches_target"])
        self.assertTrue(metadata["compatibility"]["vray_matches_target"])
        self.assertEqual(metadata["compatibility"]["warnings"], [])

    def test_prunes_unneeded_vray_defaults(self):
        filtered = self.adapter._filter_material_properties(
            "VRayMtl",
            {
                "Diffuse": [1.0, 0.0, 0.0, 1.0],
                "reflection_glossiness": 0.7,
                "reflection_subdivs": 8,
                "unrelated_internal_value": 123,
            },
        )
        self.assertIn("Diffuse", filtered)
        self.assertIn("reflection_glossiness", filtered)
        self.assertNotIn("reflection_subdivs", filtered)
        self.assertNotIn("unrelated_internal_value", filtered)

    def test_keeps_controls_only_for_connected_map_slot(self):
        controls = self.adapter._connected_map_controls(
            "VRayMtl",
            {
                "texmap_diffuse_on": True,
                "texmap_diffuse_multiplier": 100.0,
                "texmap_bump_on": True,
                "texmap_bump_multiplier": 30.0,
            },
            ["Diffuse"],
        )
        self.assertEqual(
            controls,
            {
                "texmap_diffuse_on": True,
                "texmap_diffuse_multiplier": 100.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
