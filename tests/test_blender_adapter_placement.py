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

    def __matmul__(self, point):
        return self.translation + point


class FakeMeshObject:
    type = "MESH"

    def __init__(self, location, bound_box, parent=None):
        self.parent = parent
        self.location = FakeVector(location)
        self.bound_box = bound_box
        self.data = SimpleNamespace(vertices=(object(),))
        self.world_assignments = 0

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
        self.world_assignments += 1


class FakeImportedObject:
    def __init__(self, name, object_type="MESH", data=None):
        self.name = name
        self.type = object_type
        self.data = data
        self.properties = {}

    def __setitem__(self, key, value):
        self.properties[key] = value


def load_adapter():
    fake_bpy = ModuleType("bpy")
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
        "blendmax_blender._placement_adapter_test",
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


class BlenderAdapterPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter()

    def test_nested_fbx_meshes_move_to_origin_by_translating_only_the_root(self):
        root = FakeMeshObject(
            (-4.6, -0.5, -0.05),
            ((-0.2, -0.2, 0.0), (0.2, 0.2, 0.3)),
        )
        child = FakeMeshObject(
            (0.6, 0.2, 0.1),
            ((-0.15, -0.1, 0.0), (0.15, 0.1, 0.5)),
            parent=root,
        )
        before_spacing = tuple(
            child.matrix_world.translation - root.matrix_world.translation
        )

        self.adapter.BlenderAdapter._rebase_imported_roots(
            (root, child),
            {"root": root, "child": child},
        )

        bounds = self.adapter.merge_bounds(
            (self.adapter._mesh_world_bounds(root), self.adapter._mesh_world_bounds(child))
        )
        self.assertIsNotNone(bounds)
        minimum, maximum = bounds
        self.assertAlmostEqual((minimum[0] + maximum[0]) * 0.5, 0.0)
        self.assertAlmostEqual((minimum[1] + maximum[1]) * 0.5, 0.0)
        self.assertAlmostEqual(minimum[2], 0.0)
        self.assertEqual(root.world_assignments, 1)
        self.assertEqual(child.world_assignments, 0)
        after_spacing = tuple(
            child.matrix_world.translation - root.matrix_world.translation
        )
        for before, after in zip(before_spacing, after_spacing):
            self.assertAlmostEqual(before, after)

    def test_separate_fbx_roots_receive_the_same_translation(self):
        first = FakeMeshObject(
            (-4.8, -0.5, 0.1),
            ((-0.2, -0.1, 0.0), (0.2, 0.1, 0.4)),
        )
        second = FakeMeshObject(
            (-3.8, 0.3, 0.0),
            ((-0.2, -0.1, 0.0), (0.2, 0.1, 0.6)),
        )
        before_spacing = tuple(
            second.matrix_world.translation - first.matrix_world.translation
        )

        self.adapter.BlenderAdapter._rebase_imported_roots(
            (first, second),
            {"first": first, "second": second},
        )

        bounds = self.adapter.merge_bounds(
            (self.adapter._mesh_world_bounds(first), self.adapter._mesh_world_bounds(second))
        )
        self.assertIsNotNone(bounds)
        minimum, maximum = bounds
        self.assertAlmostEqual((minimum[0] + maximum[0]) * 0.5, 0.0)
        self.assertAlmostEqual((minimum[1] + maximum[1]) * 0.5, 0.0)
        self.assertAlmostEqual(minimum[2], 0.0)
        self.assertEqual(first.world_assignments, 1)
        self.assertEqual(second.world_assignments, 1)
        after_spacing = tuple(
            second.matrix_world.translation - first.matrix_world.translation
        )
        for before, after in zip(before_spacing, after_spacing):
            self.assertAlmostEqual(before, after)

    def test_object_mapping_returns_undeclared_fbx_objects_separately(self):
        matched = FakeImportedObject("BM_declared")
        undeclared = FakeImportedObject("Untitled")
        record = ObjectRecord(
            object_id="mesh_1",
            fbx_name="BM_declared",
            original_name="Declared mesh",
            node_type="Editable_Poly",
            superclass="GeometryClass",
        )

        mapped, extras = self.adapter.BlenderAdapter._map_objects(
            (matched, undeclared),
            (record,),
            None,
            [],
            set(),
        )

        self.assertIs(mapped["mesh_1"], matched)
        self.assertEqual(extras, (undeclared,))
        self.assertEqual(matched.name, "Declared mesh")

    def test_group_head_adopts_imported_empty_node(self):
        imported_group = FakeImportedObject("BM_group", object_type="EMPTY")
        record = ObjectRecord(
            object_id="group_1",
            fbx_name="BM_group",
            original_name="Imported Group",
            node_type="Dummy",
            superclass="helper",
            is_group_head=True,
        )
        generated = set()

        mapped, extras = self.adapter.BlenderAdapter._map_objects(
            (imported_group,),
            (record,),
            None,
            [],
            generated,
        )

        self.assertIs(mapped["group_1"], imported_group)
        self.assertEqual(extras, ())
        self.assertEqual(generated, set())
        self.assertEqual(imported_group.name, "Imported Group")
        self.assertEqual(imported_group.properties["blendmax_object_id"], "group_1")

    def test_group_head_does_not_adopt_mesh_with_matching_name(self):
        imported_mesh = FakeImportedObject("BM_group", object_type="MESH")
        collection = SimpleNamespace(objects=SimpleNamespace(link=lambda _obj: None))
        generated = set()
        warnings = []
        created = []

        def new_object(name, data):
            created_object = FakeImportedObject(name, object_type="EMPTY", data=data)
            created.append(created_object)
            return created_object

        previous_data = getattr(self.adapter.bpy, "data", None)
        self.adapter.bpy.data = SimpleNamespace(objects=SimpleNamespace(new=new_object))
        try:
            record = ObjectRecord(
                object_id="group_1",
                fbx_name="BM_group",
                original_name="Imported Group",
                node_type="Dummy",
                superclass="helper",
                is_group_head=True,
            )
            mapped, extras = self.adapter.BlenderAdapter._map_objects(
                (imported_mesh,),
                (record,),
                collection,
                warnings,
                generated,
            )
        finally:
            if previous_data is None:
                del self.adapter.bpy.data
            else:
                self.adapter.bpy.data = previous_data

        self.assertEqual(extras, (imported_mesh,))
        self.assertEqual(warnings, [])
        self.assertEqual(generated, {"group_1"})
        self.assertEqual(len(created), 1)
        self.assertIs(mapped["group_1"], created[0])
        self.assertEqual(created[0].name, "Imported Group")
        self.assertEqual(created[0].properties["blendmax_object_id"], "group_1")

    def test_undeclared_fbx_mesh_and_orphan_data_are_removed(self):
        mesh = SimpleNamespace(users=1)
        undeclared = FakeImportedObject("Untitled", data=mesh)
        objects = SimpleNamespace(removed=[])
        meshes = SimpleNamespace(removed=[])

        def remove_object(item, **_kwargs):
            objects.removed.append(item)
            item.data.users = 0

        def remove_mesh(item):
            meshes.removed.append(item)

        objects.remove = remove_object
        meshes.remove = remove_mesh
        previous_data = getattr(self.adapter.bpy, "data", None)
        self.adapter.bpy.data = SimpleNamespace(objects=objects, meshes=meshes)
        try:
            self.adapter.BlenderAdapter._discard_undeclared_fbx_objects((undeclared,))
        finally:
            if previous_data is None:
                del self.adapter.bpy.data
            else:
                self.adapter.bpy.data = previous_data

        self.assertEqual(objects.removed, [undeclared])
        self.assertEqual(meshes.removed, [mesh])


if __name__ == "__main__":
    unittest.main()
