from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from blendmax_blender.models import ObjectRecord


class FakeVector:
    def __init__(self, values):
        self.values = [float(value) for value in values]

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __add__(self, other):
        return FakeVector(first + second for first, second in zip(self, other))

    def __sub__(self, other):
        return FakeVector(first - second for first, second in zip(self, other))

    def __isub__(self, other):
        self.values = [first - second for first, second in zip(self, other)]
        return self


class FakeMatrix:
    def __init__(self, translation):
        self.translation = FakeVector(translation)

    def copy(self):
        return FakeMatrix(self.translation)


class FakeMeshObject:
    type = "MESH"

    def __init__(self, location, bound_box, parent=None):
        self.parent = parent
        self.location = FakeVector(location)
        self.bound_box = bound_box
        self.data = SimpleNamespace(vertices=(object(),))
        self.properties = {}

    @property
    def matrix_world(self):
        location = self.location
        if self.parent is not None:
            location = self.parent.matrix_world.translation + location
        return FakeMatrix(location)

    @matrix_world.setter
    def matrix_world(self, value):
        location = value.translation
        if self.parent is not None:
            location = location - self.parent.matrix_world.translation
        self.location = FakeVector(location)

    def __setitem__(self, key, value):
        self.properties[key] = value


class FakeEmptyObject:
    def __init__(self, name):
        self.name = name
        self.type = "EMPTY"
        self.data = None
        self.parent = None
        self.children = []
        self.location = FakeVector((0.0, 0.0, 0.0))
        self.scale = FakeVector((1.0, 1.0, 1.0))
        self.rotation_euler = FakeVector((0.0, 0.0, 0.0))
        self.rotation_mode = "XYZ"
        self.empty_display_type = "PLAIN_AXES"
        self.empty_display_size = 1.0
        self.properties = {}

    @property
    def matrix_world(self):
        return FakeMatrix(self.location)

    @matrix_world.setter
    def matrix_world(self, value):
        self.location = value.translation

    def __setitem__(self, key, value):
        self.properties[key] = value


class FakeObjectCollection:
    def __init__(self, objects=()):
        self.items = list(objects)

    def link(self, obj):
        self.items.append(obj)

    def __iter__(self):
        return iter(self.items)


class FakeBpyData:
    def __init__(self):
        self.created = []
        self.objects = SimpleNamespace(new=self.new_object)

    def new_object(self, name, _data):
        obj = FakeEmptyObject(name)
        self.created.append(obj)
        return obj


def load_adapter():
    fake_bpy = ModuleType("bpy")
    fake_bpy.data = FakeBpyData()
    fake_mathutils = ModuleType("mathutils")
    fake_mathutils.Vector = FakeVector
    fake_materials = ModuleType("blendmax_blender.blender_materials")
    fake_materials.MaterialBuilder = object

    adapter_path = (
        Path(__file__).resolve().parents[1]
        / "blendmax_blender"
        / "blender_adapter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._controller_bounds_test",
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


class BlenderControllerBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter()

    def _package(self, recommended_scale=1.0):
        group_record = ObjectRecord(
            object_id="group_1",
            fbx_name="BM_group",
            original_name="Imported Group",
            node_type="Dummy",
            superclass="helper",
            is_group_head=True,
        )
        mesh_record = ObjectRecord(
            object_id="mesh_1",
            fbx_name="BM_mesh",
            original_name="Mesh",
            node_type="Editable_Poly",
            superclass="GeometryClass",
            parent_id="group_1",
        )
        manifest = SimpleNamespace(
            asset_name="Test Asset",
            schema_version=1,
            objects=(group_record, mesh_record),
            bounds_minimum_m=(10.0, 20.0, 30.0),
            bounds_maximum_m=(12.0, 24.0, 36.0),
            recommended_scale=recommended_scale,
        )
        return SimpleNamespace(
            manifest=manifest,
            source_path=Path("Test Asset.blendmax"),
        )

    def test_promoted_controller_stays_transform_safe_and_uses_bounds_child(self):
        controller = FakeEmptyObject("Imported Group")
        controller.location = FakeVector((5.0, 6.0, 7.0))
        controller.scale = FakeVector((2.0, 3.0, 4.0))
        controller.rotation_euler = FakeVector((0.1, 0.2, 0.3))

        mesh = FakeMeshObject(
            (5.0, 14.0, 23.0),
            ((0.0, 0.0, 0.0), (2.0, 4.0, 6.0)),
            parent=controller,
        )
        controller.children.append(mesh)
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))
        package = self._package()

        result = self.adapter.BlenderAdapter._create_controller(
            collection,
            package,
            {"group_1": controller, "mesh_1": mesh},
            False,
            "Test Asset - BlendMax manifest.json",
        )

        self.assertIs(result, controller)
        self.assertEqual(tuple(controller.location), (11.0, 22.0, 33.0))
        self.assertEqual(tuple(controller.scale), (1.0, 1.0, 1.0))
        self.assertEqual(tuple(controller.rotation_euler), (0.0, 0.0, 0.0))
        self.assertEqual(controller.properties["blendmax_original_name"], "Imported Group")
        self.assertEqual(controller.properties["blendmax_controller_source"], "imported_group_head")
        self.assertEqual(tuple(mesh.matrix_world.translation), (10.0, 20.0, 30.0))
        self.assertIs(mesh.parent, controller)

        bounds = [obj for obj in collection.objects if obj is not controller and obj is not mesh]
        self.assertEqual(len(bounds), 1)
        bounds_display = bounds[0]
        self.assertEqual(bounds_display.empty_display_type, "CUBE")
        self.assertEqual(bounds_display.empty_display_size, 0.5)
        self.assertEqual(tuple(bounds_display.location), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(bounds_display.scale), (2.0, 4.0, 6.0))
        self.assertIs(bounds_display.parent, controller)

    def test_recommended_scale_remains_a_uniform_controller_transform(self):
        controller = FakeEmptyObject("Imported Group")
        mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((0.0, 0.0, 0.0), (2.0, 4.0, 6.0)),
            parent=controller,
        )
        controller.children.append(mesh)
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))

        self.adapter.BlenderAdapter._create_controller(
            collection,
            self._package(recommended_scale=1.5),
            {"group_1": controller, "mesh_1": mesh},
            True,
            "Test Asset - BlendMax manifest.json",
        )

        self.assertEqual(tuple(controller.scale), (1.5, 1.5, 1.5))
        bounds_display = [obj for obj in collection.objects if obj is not controller and obj is not mesh][0]
        self.assertEqual(tuple(bounds_display.scale), (2.0, 4.0, 6.0))

    def test_degenerate_bounds_are_not_artificially_clamped(self):
        controller = FakeEmptyObject("Imported Group")
        mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((0.0, 0.0, 0.0), (0.0, 4.0, 6.0)),
            parent=controller,
        )
        controller.children.append(mesh)
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))
        package = self._package()
        package.manifest.bounds_minimum_m = (0.0, 0.0, 0.0)
        package.manifest.bounds_maximum_m = (0.0, 4.0, 6.0)

        self.adapter.BlenderAdapter._create_controller(
            collection,
            package,
            {"group_1": controller, "mesh_1": mesh},
            False,
            "Test Asset - BlendMax manifest.json",
        )

        bounds_display = [obj for obj in collection.objects if obj is not controller and obj is not mesh][0]
        self.assertEqual(tuple(bounds_display.scale), (0.0, 4.0, 6.0))


if __name__ == "__main__":
    unittest.main()
