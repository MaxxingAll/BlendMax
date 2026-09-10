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
    """Homogeneous 4x4 matrix fake.

    Mirrors the Blender relationships these tests depend on:
    ``child.matrix_world = parent.matrix_world @ matrix_parent_inverse @
    matrix_basis``. Bases are translation @ axis-aligned scale; rotations are
    intentionally ignored because the adapter normalizes the controller
    rotation before applying bounds scale.
    """

    def __init__(self, rows):
        self.rows = tuple(tuple(float(value) for value in row) for row in rows)

    @classmethod
    def identity(cls):
        return cls(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @classmethod
    def translation_scale(cls, translation, scale):
        tx, ty, tz = (float(value) for value in translation)
        sx, sy, sz = (float(value) for value in scale)
        return cls(
            (
                (sx, 0.0, 0.0, tx),
                (0.0, sy, 0.0, ty),
                (0.0, 0.0, sz, tz),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @property
    def translation(self):
        return FakeVector((self.rows[0][3], self.rows[1][3], self.rows[2][3]))

    @translation.setter
    def translation(self, value):
        rows = [list(row) for row in self.rows]
        rows[0][3], rows[1][3], rows[2][3] = (
            float(component) for component in value
        )
        self.rows = tuple(tuple(row) for row in rows)

    def copy(self):
        return FakeMatrix(self.rows)

    def __matmul__(self, other):
        if isinstance(other, FakeMatrix):
            return FakeMatrix(
                tuple(
                    tuple(
                        sum(self.rows[row][k] * other.rows[k][column] for k in range(4))
                        for column in range(4)
                    )
                    for row in range(4)
                )
            )
        if isinstance(other, FakeVector):
            values = list(other) + [1.0]
            return FakeVector(
                sum(self.rows[row][k] * values[k] for k in range(4))
                for row in range(3)
            )
        raise TypeError("FakeMatrix can only multiply FakeMatrix or FakeVector")

    def inverted(self):
        augmented = [
            list(row) + list(identity_row)
            for row, identity_row in zip(self.rows, FakeMatrix.identity().rows)
        ]
        for column in range(4):
            pivot = max(
                range(column, 4),
                key=lambda row: abs(augmented[row][column]),
            )
            if abs(augmented[pivot][column]) < 1e-12:
                raise ValueError("FakeMatrix is singular")
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
            divisor = augmented[column][column]
            augmented[column] = [value / divisor for value in augmented[column]]
            for row in range(4):
                if row == column:
                    continue
                factor = augmented[row][column]
                augmented[row] = [
                    left - factor * right
                    for left, right in zip(augmented[row], augmented[column])
                ]
        return FakeMatrix(tuple(row[4:] for row in augmented))


class FakeMeshObject:
    type = "MESH"

    def __init__(self, location, bound_box, parent=None):
        self.parent = parent
        self.location = FakeVector(location)
        self.bound_box = bound_box
        self.data = SimpleNamespace(vertices=(object(),))
        self.properties = {}
        self.matrix_parent_inverse = FakeMatrix.identity()

    @property
    def matrix_basis(self):
        return FakeMatrix.translation_scale(self.location, (1.0, 1.0, 1.0))

    @property
    def matrix_world(self):
        basis = self.matrix_basis
        if self.parent is None:
            return basis
        return self.parent.matrix_world @ self.matrix_parent_inverse @ basis

    @matrix_world.setter
    def matrix_world(self, value):
        if self.parent is None:
            self.location = FakeVector(value.translation)
            return
        parent_space = (
            self.parent.matrix_world @ self.matrix_parent_inverse
        ).inverted() @ value
        self.location = FakeVector(parent_space.translation)

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
        self.hide_select = False
        self.hide_render = False
        self.properties = {}
        self.matrix_parent_inverse = FakeMatrix.identity()

    @property
    def matrix_basis(self):
        return FakeMatrix.translation_scale(self.location, self.scale)

    @property
    def matrix_world(self):
        basis = self.matrix_basis
        if self.parent is None:
            return basis
        return self.parent.matrix_world @ self.matrix_parent_inverse @ basis

    @matrix_world.setter
    def matrix_world(self, value):
        # Empties in these tests only appear as controllers, so a world write
        # only needs to reposition them; scale and rotation stay authored.
        if self.parent is None:
            self.location = FakeVector(value.translation)
            return
        parent_space = (
            self.parent.matrix_world @ self.matrix_parent_inverse
        ).inverted() @ value
        self.location = FakeVector(parent_space.translation)

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
    fake_bpy.context = SimpleNamespace(
        view_layer=SimpleNamespace(update=lambda: None),
        selected_objects=(),
    )
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

    def test_promoted_controller_is_the_selectable_bounds_cube(self):
        controller = FakeEmptyObject("Imported Group")
        controller.location = FakeVector((5.0, 6.0, 7.0))
        controller.scale = FakeVector((2.0, 4.0, 8.0))
        controller.rotation_euler = FakeVector((0.1, 0.2, 0.3))

        mesh = FakeMeshObject(
            (5.0, 14.0, 23.0),
            ((0.0, 0.0, 0.0), (2.0, 4.0, 8.0)),
            parent=controller,
        )
        # FBX-style parenting: the child's parent inverse cancels the
        # controller's initial scale so its world corners sit exactly on the
        # manifest bounds.
        mesh.matrix_parent_inverse = FakeMatrix.translation_scale(
            (0.0, 0.0, 0.0), (0.5, 0.25, 0.125)
        )
        controller.children.append(mesh)
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))
        package = self._package()
        package.manifest.bounds_minimum_m = (10.0, 20.0, 30.0)
        package.manifest.bounds_maximum_m = (12.0, 24.0, 38.0)
        warnings = []

        result = self.adapter.BlenderAdapter._create_controller(
            collection,
            package,
            {"group_1": controller, "mesh_1": mesh},
            False,
            "Test Asset - BlendMax manifest.json",
            warnings,
        )

        self.assertIs(result, controller)
        self.assertEqual(controller.name, "Test Asset [BlendMax]")
        self.assertEqual(controller.empty_display_type, "CUBE")
        self.assertEqual(controller.empty_display_size, 0.5)
        self.assertEqual(tuple(controller.location), (11.0, 22.0, 34.0))
        self.assertEqual(tuple(controller.rotation_euler), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(controller.scale), (2.0, 4.0, 8.0))
        self.assertFalse(controller.hide_select)
        self.assertFalse(controller.hide_render)
        self.assertEqual(controller.properties["blendmax_original_name"], "Imported Group")
        self.assertEqual(controller.properties["blendmax_controller_source"], "imported_group_head")
        self.assertEqual(
            controller.properties["blendmax_original_rotation_euler"],
            (0.1, 0.2, 0.3),
        )
        self.assertEqual(
            controller.properties["blendmax_original_scale"],
            (2.0, 4.0, 8.0),
        )
        self.assertEqual(tuple(mesh.matrix_world.translation), (10.0, 20.0, 30.0))
        self.assertIs(mesh.parent, controller)
        self.assertEqual(
            [
                obj
                for obj in collection.objects
                if obj is not controller and obj is not mesh
            ],
            [],
        )

    def test_recommended_scale_multiplies_controller_bounds_scale(self):
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
            [],
        )

        self.assertEqual(tuple(controller.scale), (3.0, 6.0, 9.0))
        self.assertEqual(
            [
                obj
                for obj in collection.objects
                if obj is not controller and obj is not mesh
            ],
            [],
        )

    def test_degenerate_bounds_keep_controller_matrix_invertible(self):
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
            [],
        )

        self.assertEqual(tuple(controller.scale), (1e-6, 4.0, 6.0))
        self.assertGreater(controller.scale[0], 0.0)
        self.assertEqual(
            [
                obj
                for obj in collection.objects
                if obj is not controller and obj is not mesh
            ],
            [],
        )


if __name__ == "__main__":
    unittest.main()
