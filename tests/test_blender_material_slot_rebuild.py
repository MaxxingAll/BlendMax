"""Regression tests for BlenderAdapter._replace_material_slots.

Background: `Mesh.materials.clear()` resets every polygon's
`material_index` to 0 as a side effect once the slot list it points into
is emptied. BlendMax used to clear a mesh's material slots and then
`append()` its converted materials back on, which silently destroyed the
per-face slot assignment Blender's FBX importer had just established.

The fixture distribution below (0:70, 1:408, 2:888, 3:758, 4:2098,
5:8404 across 12,626 faces) is the real `LayerElementMaterial` layout
from a 3ds Max Multi/Sub-Object chair asset exported through BlendMax's
FBX pipeline, confirmed by parsing the FBX binary directly and by
reading `polygon.material_index` back from Blender's own native FBX
importer. Any rebuild strategy must reproduce this distribution exactly
after replacing the six material slots with BlendMax-authored materials.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

# The known-good per-face material_index distribution for the chair
# fixture, as read directly from geometry.fbx's LayerElementMaterial
# layer and confirmed by Blender's native (non-BlendMax) FBX importer.
CHAIR_FIXTURE_DISTRIBUTION = {
    0: 70,
    1: 408,
    2: 888,
    3: 758,
    4: 2098,
    5: 8404,
}


class FakePolygon:
    def __init__(self, material_index: int):
        self.material_index = material_index


class FakeMaterialSlots:
    """Minimal stand-in for Blender's bpy_prop_collection of materials."""

    def __init__(self, materials, polygons):
        self._items = list(materials)
        self._polygons = polygons

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __setitem__(self, index, value):
        self._items[index] = value

    def append(self, material):
        self._items.append(material)

    def pop(self, index):
        if index < 0:
            index += len(self._items)
        material = self._items.pop(index)
        for polygon in self._polygons:
            if polygon.material_index > 0 and polygon.material_index >= index:
                polygon.material_index -= 1
        return material

    def clear(self):
        self._items.clear()
        for polygon in self._polygons:
            polygon.material_index = 0


class FakeMeshData:
    def __init__(self, materials, polygons):
        self.polygons = list(polygons)
        self.materials = FakeMaterialSlots(materials, self.polygons)


class FakeMeshObject:
    type = "MESH"

    def __init__(self, name, materials, polygons):
        self.name = name
        self.data = FakeMeshData(materials, polygons)


def _polygons_from_distribution(distribution):
    polygons = []
    for material_index, count in distribution.items():
        polygons.extend(FakePolygon(material_index) for _ in range(count))
    return polygons


def load_adapter():
    """Load blender_adapter.py with a fake `bpy` so it imports without Blender."""
    fake_bpy = ModuleType("bpy")
    fake_mathutils = ModuleType("mathutils")
    fake_mathutils.Vector = object
    fake_materials = ModuleType("blendmax_blender.blender_materials")
    fake_materials.MaterialBuilder = object

    adapter_path = (
        Path(__file__).resolve().parents[1]
        / "blendmax_blender"
        / "blender_adapter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._material_rebuild_adapter_test",
        adapter_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load BlendMax Blender adapter test module.")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "bpy": fake_bpy,
            "mathutils": fake_mathutils,
            "blendmax_blender.blender_materials": fake_materials,
        },
    ):
        spec.loader.exec_module(module)
    return module


class ReplaceMaterialSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter()

    def _distribution(self, obj):
        return dict(Counter(p.material_index for p in obj.data.polygons))

    def test_rebuild_preserves_the_known_good_chair_distribution(self):
        # Simulate the mesh exactly as Blender's native FBX importer leaves
        # it: six original (FBX-created) material slots, and per-face
        # material_index values matching the real chair fixture.
        original_slots = ["fbx_mat_{0}".format(i) for i in range(6)]
        polygons = _polygons_from_distribution(CHAIR_FIXTURE_DISTRIBUTION)
        obj = FakeMeshObject("chair_shell", original_slots, polygons)

        converted_materials = tuple(
            "blendmax_mat_{0}".format(i) for i in range(6)
        )
        warnings = []
        self.adapter.BlenderAdapter._replace_material_slots(
            obj, converted_materials, warnings
        )

        self.assertEqual(tuple(obj.data.materials), converted_materials)
        self.assertEqual(
            self._distribution(obj), CHAIR_FIXTURE_DISTRIBUTION
        )
        self.assertEqual(warnings, [])

    def test_rebuild_never_calls_clear(self):
        # The whole point of the fix: the slot collection must never be
        # emptied out from under polygons that still reference it.
        original_slots = ["fbx_mat_{0}".format(i) for i in range(6)]
        polygons = _polygons_from_distribution(CHAIR_FIXTURE_DISTRIBUTION)
        obj = FakeMeshObject("chair_shell", original_slots, polygons)

        def _forbidden_clear():
            raise AssertionError(
                "_replace_material_slots must not call materials.clear(); "
                "doing so resets every polygon's material_index to 0."
            )

        obj.data.materials.clear = _forbidden_clear

        converted_materials = tuple(
            "blendmax_mat_{0}".format(i) for i in range(6)
        )
        self.adapter.BlenderAdapter._replace_material_slots(
            obj, converted_materials, []
        )
        self.assertEqual(
            self._distribution(obj), CHAIR_FIXTURE_DISTRIBUTION
        )

    def test_trailing_slots_are_trimmed_when_fewer_materials_are_assigned(self):
        original_slots = ["fbx_mat_{0}".format(i) for i in range(6)]
        polygons = [FakePolygon(0), FakePolygon(1), FakePolygon(1)]
        obj = FakeMeshObject("simple_part", original_slots, polygons)

        self.adapter.BlenderAdapter._replace_material_slots(
            obj, ("only_material",), []
        )

        self.assertEqual(len(obj.data.materials), 1)
        self.assertEqual(tuple(obj.data.materials), ("only_material",))
        self.assertEqual(self._distribution(obj), {0: 3})

    def test_faces_referencing_removed_slots_produce_a_warning_before_the_trim(self):
        original_slots = ["fbx_mat_{0}".format(i) for i in range(6)]
        polygons = _polygons_from_distribution(CHAIR_FIXTURE_DISTRIBUTION)
        obj = FakeMeshObject("chair_shell", original_slots, polygons)

        # Simulate a manifest/material graph that only produced 2 materials
        # for a mesh whose faces reference up to index 5. The defensive check
        # must run before Blender-style slot removal remaps those face indices.
        warnings = []
        self.adapter.BlenderAdapter._replace_material_slots(
            obj, ("mat_a", "mat_b"), warnings
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("chair_shell", warnings[0])
        self.assertIn("4 imported material slot(s) removed", warnings[0])
        self.assertIn("12148", warnings[0])
        self.assertEqual(
            self._distribution(obj),
            {0: 70, 1: 12556},
        )

    def test_no_warning_when_every_face_index_is_in_range(self):
        original_slots = ["fbx_mat_0", "fbx_mat_1"]
        polygons = [FakePolygon(0), FakePolygon(1), FakePolygon(1)]
        obj = FakeMeshObject("simple_part", original_slots, polygons)

        warnings = []
        self.adapter.BlenderAdapter._replace_material_slots(
            obj, ("mat_a", "mat_b"), warnings
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
