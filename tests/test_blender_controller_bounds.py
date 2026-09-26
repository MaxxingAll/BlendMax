from __future__ import annotations

import math
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from blendmax_blender.models import ObjectRecord

try:
    from fakes import (
    FakeEmptyObject,
    FakeMatrix,
    FakeMeshObject,
    FakeVector,
    load_blender_module,
)
except ImportError:  # dotted-module invocation from the repository root
    from tests.fakes import (
        FakeEmptyObject,
        FakeMatrix,
        FakeMeshObject,
        FakeVector,
        load_blender_module,
    )


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


class BlenderControllerBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_bpy = ModuleType("bpy")
        fake_bpy.data = FakeBpyData()
        fake_bpy.context = SimpleNamespace(
            view_layer=SimpleNamespace(update=lambda: None),
            selected_objects=(),
        )
        cls.scene = load_blender_module("blender_scene.py", vector=FakeVector, bpy=fake_bpy)

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
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))
        package = self._package()
        package.manifest.bounds_minimum_m = (10.0, 20.0, 30.0)
        package.manifest.bounds_maximum_m = (12.0, 24.0, 38.0)
        warnings = []

        result = self.scene._create_controller(
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

    def test_rotated_hierarchy_world_transforms_survive_full_controller_build(self):
        # End-to-end guard for the shear bug: unlike the isolated
        # _apply_bounds_scale() unit test, this runs the whole controller
        # build (hierarchy restore, root parenting, bounds scale) over a
        # genuinely rotated/scaled direct child plus a nested grandchild and
        # pins their world matrices, so any future step that lossily rewrites
        # transforms after the bounds scale fails here.
        root_basis = FakeMatrix.from_translation(
            1.5, -0.5, 2.0
        ) @ FakeMatrix.from_rotation_scale(
            math.radians(23.0),
            math.radians(-31.0),
            math.radians(17.0),
            1.2,
            0.7,
            1.8,
        )
        child_basis = FakeMatrix.from_translation(
            -0.5, 0.25, 0.75
        ) @ FakeMatrix.from_rotation_scale(
            math.radians(-11.0),
            math.radians(9.0),
            math.radians(28.0),
            0.9,
            1.1,
            0.6,
        )
        root_mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
            matrix_basis=root_basis,
        )
        child_mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)),
            parent=root_mesh,
            matrix_basis=child_basis,
        )
        collection = SimpleNamespace(
            objects=FakeObjectCollection((root_mesh, child_mesh))
        )
        records = (
            ObjectRecord(
                object_id="mesh_root",
                fbx_name="BM_root",
                original_name="Root Mesh",
                node_type="Editable_Poly",
                superclass="GeometryClass",
            ),
            ObjectRecord(
                object_id="mesh_child",
                fbx_name="BM_child",
                original_name="Child Mesh",
                node_type="Editable_Poly",
                superclass="GeometryClass",
                parent_id="mesh_root",
            ),
        )
        package = SimpleNamespace(
            manifest=SimpleNamespace(
                asset_name="Rotated Asset",
                schema_version=1,
                objects=records,
                bounds_minimum_m=(0.0, 0.0, 0.0),
                bounds_maximum_m=(1.0, 1.0, 1.0),
                recommended_scale=1.0,
            ),
            source_path=Path("Rotated Asset.blendmax"),
        )

        root_world_before = root_mesh.matrix_world.copy()
        child_world_before = child_mesh.matrix_world.copy()

        controller = self.scene._create_controller(
            collection,
            package,
            {"mesh_root": root_mesh, "mesh_child": child_mesh},
            False,
            "Rotated Asset - BlendMax manifest.json",
            [],
        )

        self.assertIs(root_mesh.parent, controller)
        self.assertIs(child_mesh.parent, root_mesh)
        self.assertGreater(min(float(value) for value in controller.scale), 0.0)
        self.assertNotEqual(tuple(controller.scale), (1.0, 1.0, 1.0))
        self.assertTrue(
            root_mesh.matrix_world.almost_equal(root_world_before, tolerance=1e-8),
            "Direct child world transform must survive bounds scaling "
            "without shear loss.",
        )
        self.assertTrue(
            child_mesh.matrix_world.almost_equal(child_world_before, tolerance=1e-8),
            "Grandchild world transform must be preserved transitively.",
        )

    def test_recommended_scale_multiplies_controller_bounds_scale(self):
        controller = FakeEmptyObject("Imported Group")
        mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((0.0, 0.0, 0.0), (2.0, 4.0, 6.0)),
            parent=controller,
        )
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))

        self.scene._create_controller(
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
        collection = SimpleNamespace(objects=FakeObjectCollection((controller, mesh)))
        package = self._package()
        package.manifest.bounds_minimum_m = (0.0, 0.0, 0.0)
        package.manifest.bounds_maximum_m = (0.0, 4.0, 6.0)

        self.scene._create_controller(
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
