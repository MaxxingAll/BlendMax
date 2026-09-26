"""Tests for the shared presentation-bounds foundation (#45/#46).

The pure bounds math (``blendmax_blender.presentation``) needs no Blender.
The scene-boundary gathering step (``blender_scene.presentation_bounds``) is
driven here with the shared ``FakeMatrix`` / ``FakeMeshObject`` /
``FakeEmptyObject`` doubles, which model the world-matrix and parenting
reads the gathering code performs.
"""

from __future__ import annotations

import dataclasses
import unittest
from types import ModuleType, SimpleNamespace

from blendmax_blender.placement import (
    bounds_from_points,
    grounded_anchor,
    merge_bounds,
)
from blendmax_blender.presentation import PresentationBounds

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


class PresentationBoundsValueTests(unittest.TestCase):
    """The pure data type: world-space min/max plus derived values."""

    def test_points_produce_world_space_minimum_and_maximum(self):
        bounds = PresentationBounds.from_points(
            [(1.0, 2.0, 3.0), (-4.0, 8.0, 0.5), (-4.0, -1.0, 6.0)]
        )
        self.assertEqual(bounds.minimum, (-4.0, -1.0, 0.5))
        self.assertEqual(bounds.maximum, (1.0, 8.0, 6.0))

    def test_dimensions_and_center_are_derived_from_the_bounds_pair(self):
        bounds = PresentationBounds(
            minimum=(0.0, 0.0, 0.0), maximum=(2.0, 4.0, 6.0)
        )
        self.assertEqual(bounds.dimensions, (2.0, 4.0, 6.0))
        self.assertEqual(bounds.center, (1.0, 2.0, 3.0))

    def test_asymmetric_bounds_with_negative_world_coordinates(self):
        bounds = PresentationBounds(
            minimum=(-8.0, -3.0, -1.5), maximum=(-2.0, 1.0, 4.5)
        )
        self.assertEqual(bounds.dimensions, (6.0, 4.0, 6.0))
        self.assertEqual(bounds.center, (-5.0, -1.0, 1.5))

    def test_a_single_point_is_valid_zero_volume_bounds(self):
        bounds = PresentationBounds.from_points([(7.0, -2.0, 0.0)])
        self.assertEqual(bounds.minimum, (7.0, -2.0, 0.0))
        self.assertEqual(bounds.maximum, (7.0, -2.0, 0.0))
        self.assertEqual(bounds.dimensions, (0.0, 0.0, 0.0))
        self.assertEqual(bounds.center, (7.0, -2.0, 0.0))

    def test_no_valid_geometry_is_none_not_a_fake_size(self):
        # Callers must handle "no geometry" explicitly; the foundation never
        # invents a unit cube to dodge the empty case.
        self.assertIsNone(PresentationBounds.from_points([]))
        self.assertIsNone(PresentationBounds.from_points(iter(())))

    def test_from_bounds_wraps_the_existing_placement_pipeline(self):
        pair = merge_bounds(
            [
                bounds_from_points([(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]),
                bounds_from_points([(4.0, -2.0, 3.0)]),
            ]
        )
        bounds = PresentationBounds.from_bounds(pair)
        self.assertEqual(bounds.minimum, (0.0, -2.0, 0.0))
        self.assertEqual(bounds.maximum, (4.0, 1.0, 3.0))
        self.assertEqual(bounds.dimensions, (4.0, 3.0, 3.0))
        # The existing placement helpers keep working on the derived pair.
        self.assertEqual(
            grounded_anchor((bounds.minimum, bounds.maximum)), (2.0, -0.5, 0.0)
        )

    def test_expanded_grows_every_side_without_moving_the_center(self):
        bounds = PresentationBounds(
            minimum=(0.0, 0.0, 0.0), maximum=(2.0, 4.0, 6.0)
        )
        grown = bounds.expanded(0.5)
        self.assertEqual(grown.minimum, (-0.5, -0.5, -0.5))
        self.assertEqual(grown.maximum, (2.5, 4.5, 6.5))
        self.assertEqual(grown.dimensions, (3.0, 5.0, 7.0))
        self.assertEqual(grown.center, bounds.center)
        # Framing is a derived copy; the raw asset bounds stay untouched.
        self.assertEqual(bounds.minimum, (0.0, 0.0, 0.0))
        self.assertEqual(bounds.maximum, (2.0, 4.0, 6.0))

    def test_source_root_is_carried_through_construction_and_derivation(self):
        direct = PresentationBounds.from_points([(0.0, 0.0, 0.0)], source_root="Root")
        self.assertEqual(direct.source_root, "Root")
        self.assertEqual(direct.expanded(0.5).source_root, "Root")
        self.assertIsNone(
            PresentationBounds.from_bounds(
                ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
            ).source_root
        )

    def test_presentation_bounds_are_frozen_value_objects(self):
        bounds = PresentationBounds(
            minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bounds.minimum = (9.0, 9.0, 9.0)
        self.assertEqual(
            bounds,
            PresentationBounds(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)),
        )
        self.assertEqual(hash(bounds), hash(bounds.expanded(0.0)))


class BlenderPresentationGatheringTests(unittest.TestCase):
    """The scene-boundary gathering step (``blender_scene.presentation_bounds``)."""

    @classmethod
    def setUpClass(cls):
        cls.scene = load_blender_module(
            "blender_scene.py", vector=FakeVector, bpy=ModuleType("bpy")
        )

    def test_gathers_world_space_bounds_from_a_translated_mesh(self):
        mesh = FakeMeshObject((10.0, 20.0, 30.0), ((0.0, 0.0, 0.0), (2.0, 4.0, 6.0)))
        bounds = self.scene.presentation_bounds([mesh])
        self.assertEqual(bounds.minimum, (10.0, 20.0, 30.0))
        self.assertEqual(bounds.maximum, (12.0, 24.0, 36.0))
        self.assertEqual(bounds.dimensions, (2.0, 4.0, 6.0))
        self.assertEqual(bounds.center, (11.0, 22.0, 33.0))
        self.assertIsNone(bounds.source_root)

    def test_scaled_world_matrix_is_honoured(self):
        mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            matrix_basis=FakeMatrix.translation_scale((1.0, 2.0, 3.0), (2.0, 2.0, 2.0)),
        )
        bounds = self.scene.presentation_bounds([mesh])
        self.assertEqual(bounds.minimum, (1.0, 2.0, 3.0))
        self.assertEqual(bounds.maximum, (3.0, 4.0, 5.0))

    def test_merges_multiple_objects_and_nested_descendants(self):
        root = FakeEmptyObject("Asset [BlendMax]")
        near = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
            parent=root,
        )
        far = FakeMeshObject(
            (4.0, 0.0, 0.0), ((0.0, 0.0, 0.0), (2.0, 2.0, 2.0)), parent=root
        )
        deeper = FakeMeshObject(
            (0.0, 6.0, 0.0), ((0.0, 0.0, 0.0), (1.0, 3.0, 1.0)), parent=far
        )
        # Passing a controller and its members together visits some objects
        # twice through the walk; merging is idempotent, so the result is the
        # same bounds either way.
        bounds = self.scene.presentation_bounds([root, near, far, deeper])
        self.assertEqual(bounds.minimum, (-1.0, -1.0, -1.0))
        self.assertEqual(bounds.maximum, (6.0, 9.0, 2.0))
        self.assertEqual(bounds.dimensions, (7.0, 10.0, 3.0))
        self.assertEqual(bounds.center, (2.5, 4.0, 0.5))

    def test_controller_only_selection_includes_descendant_meshes(self):
        controller = FakeEmptyObject("Chair [BlendMax]")
        seat = FakeMeshObject(
            (0.0, 0.0, 0.5),
            ((-0.5, -0.5, 0.0), (0.5, 0.5, 0.1)),
            parent=controller,
        )
        FakeMeshObject(
            (0.0, 0.0, 0.25),
            ((-0.05, -0.05, 0.0), (0.05, 0.05, 0.5)),
            parent=seat,
        )
        bounds = self.scene.presentation_bounds(
            [controller], source_root="Chair [BlendMax]"
        )
        self.assertEqual(bounds.minimum, (-0.5, -0.5, 0.5))
        self.assertEqual(bounds.maximum, (0.5, 0.5, 1.25))
        self.assertEqual(bounds.source_root, "Chair [BlendMax]")

    def test_hierarchy_without_geometry_yields_none(self):
        controller = FakeEmptyObject("Empty")
        empty_mesh = FakeMeshObject(
            (0.0, 0.0, 0.0),
            ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            parent=controller,
        )
        empty_mesh.data = SimpleNamespace(vertices=())
        self.assertIsNone(self.scene.presentation_bounds([]))
        self.assertIsNone(self.scene.presentation_bounds([controller]))
        self.assertIsNone(self.scene.presentation_bounds([empty_mesh]))


if __name__ == "__main__":
    unittest.main()
