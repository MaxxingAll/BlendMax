from __future__ import annotations

import unittest

from blendmax_max.alpha_opacity import (
    confirm_alpha_opacity,
    find_alpha_opacity_geometry,
    material_uses_alpha_opacity,
)


class FakeMaterial:
    def __init__(self, name, class_name="Standard", **properties):
        self.name = name
        self.class_name = class_name
        self.properties = properties
        self.sub_materials = []
        self.sub_textures = []


class FakeRuntime:
    undefined = object()

    def getPropNames(self, value):
        return list(value.properties)

    def getProperty(self, value, name):
        if name not in value.properties:
            raise AttributeError(name)
        return value.properties[name]

    def getNumSubMtls(self, value):
        return len(value.sub_materials)

    def getSubMtl(self, value, index):
        return value.sub_materials[index - 1]

    def getNumSubTexmaps(self, value):
        return len(value.sub_textures)

    def getSubTexmap(self, value, index):
        return value.sub_textures[index - 1]

    def getSubTexmapSlotName(self, value, index):
        return value.sub_textures[index - 1][0]

    def queryBox(self, message, title=""):
        self.last_message = message
        self.last_title = title
        return True


class FakeAdapter:
    def __init__(self, materials):
        self.rt = FakeRuntime()
        self.materials = materials
        self._nodes_by_id = {
            key: type("Node", (), {"name": key, "material": material})()
            for key, material in materials.items()
        }

    def _class_name(self, value):
        return value.class_name

    def _anim_id(self, value):
        return str(id(value))

    def _is_undefined(self, value):
        return value is None or value is self.rt.undefined


class AlphaOpacityTests(unittest.TestCase):
    def test_standard_enabled_opacity_map_is_detected(self):
        material = FakeMaterial(
            "Leaves",
            opacityMap="leaf_alpha.png",
            opacityMapEnable=True,
            opacity=100,
        )
        self.assertTrue(material_uses_alpha_opacity(FakeAdapter({"leaf": material}), material))

    def test_standard_disabled_opacity_map_is_not_detected(self):
        material = FakeMaterial(
            "Leaves",
            opacityMap="leaf_alpha.png",
            opacityMapEnable=False,
            opacity=100,
        )
        self.assertFalse(material_uses_alpha_opacity(FakeAdapter({"leaf": material}), material))

    def test_standard_constant_opacity_below_100_is_detected(self):
        material = FakeMaterial("Leaves", opacity=75)
        self.assertTrue(material_uses_alpha_opacity(FakeAdapter({"leaf": material}), material))

    def test_vray_enabled_opacity_map_is_detected(self):
        material = FakeMaterial(
            "Leaves",
            class_name="VRayMtl",
            texmap_opacity="leaf_alpha.png",
            texmap_opacity_on=True,
        )
        self.assertTrue(material_uses_alpha_opacity(FakeAdapter({"leaf": material}), material))

    def test_vray_disabled_opacity_map_is_not_detected(self):
        material = FakeMaterial(
            "Leaves",
            class_name="VRayMtl",
            texmap_opacity="leaf_alpha.png",
            texmap_opacity_on=False,
        )
        self.assertFalse(material_uses_alpha_opacity(FakeAdapter({"leaf": material}), material))

    def test_nested_multisub_opacity_protects_whole_geometry(self):
        multisub = FakeMaterial("TreeMulti", class_name="Multi/Sub")
        bark = FakeMaterial("Bark01", class_name="VRayMtl")
        leaves = FakeMaterial(
            "Leaves01",
            class_name="VRayMtl",
            texmap_opacity="leaf_alpha.png",
            texmap_opacity_on=True,
        )
        multisub.sub_materials = [bark, leaves]
        adapter = FakeAdapter({"Tree_01": multisub, "Rock_01": bark})

        findings = find_alpha_opacity_geometry(
            adapter,
            ["Tree_01", "Rock_01"],
        )

        self.assertEqual([finding.geometry_id for finding in findings], ["Tree_01"])

    def test_no_findings_does_not_request_user_decision(self):
        adapter = FakeAdapter({})
        decision = confirm_alpha_opacity(adapter, ())
        self.assertEqual(decision.action, "NONE")


if __name__ == "__main__":
    unittest.main()
