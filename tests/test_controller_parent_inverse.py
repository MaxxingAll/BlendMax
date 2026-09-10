from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class FakeMatrix:
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
    def from_translation(cls, x, y, z):
        matrix = cls.identity().rows
        rows = [list(row) for row in matrix]
        rows[0][3] = x
        rows[1][3] = y
        rows[2][3] = z
        return cls(rows)

    @classmethod
    def from_rotation_scale(cls, rx, ry, rz, sx, sy, sz):
        cx, sx_ = math.cos(rx), math.sin(rx)
        cy, sy_ = math.cos(ry), math.sin(ry)
        cz, sz_ = math.cos(rz), math.sin(rz)
        rz_matrix = cls(
            (
                (cz, -sz_, 0.0, 0.0),
                (sz_, cz, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        ry_matrix = cls(
            (
                (cy, 0.0, sy_, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (-sy_, 0.0, cy, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        rx_matrix = cls(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, cx, -sx_, 0.0),
                (0.0, sx_, cx, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        scale = cls(
            (
                (sx, 0.0, 0.0, 0.0),
                (0.0, sy, 0.0, 0.0),
                (0.0, 0.0, sz, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        return rz_matrix @ ry_matrix @ rx_matrix @ scale

    def copy(self):
        return FakeMatrix(self.rows)

    def __matmul__(self, other):
        if not isinstance(other, FakeMatrix):
            raise TypeError("FakeMatrix only supports matrix multiplication")
        return FakeMatrix(
            tuple(
                tuple(
                    sum(self.rows[row][k] * other.rows[k][column] for k in range(4))
                    for column in range(4)
                )
                for row in range(4)
            )
        )

    def inverted(self):
        augmented = [
            list(row) + list(identity_row)
            for row, identity_row in zip(
                self.rows,
                FakeMatrix.identity().rows,
            )
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

    def almost_equal(self, other, tolerance=1e-9):
        return all(
            abs(left - right) <= tolerance
            for left_row, right_row in zip(self.rows, other.rows)
            for left, right in zip(left_row, right_row)
        )


class FakeChild:
    def __init__(self, matrix_basis, parent=None):
        self.matrix_basis = matrix_basis.copy()
        self._matrix_parent_inverse = FakeMatrix.identity()
        self.parent = parent
        self.children = []
        self.scale = (1.0, 1.0, 1.0)

    @property
    def matrix_parent_inverse(self):
        return self._matrix_parent_inverse

    @matrix_parent_inverse.setter
    def matrix_parent_inverse(self, value):
        self._matrix_parent_inverse = value.copy()

    @property
    def matrix_world(self):
        if self.parent is None:
            return self.matrix_basis.copy()
        return self.parent.matrix_world @ self.matrix_parent_inverse @ self.matrix_basis


class FakeController:
    def __init__(self):
        self.location = (3.0, 5.0, 7.0)
        self.scale = (1.0, 1.0, 1.0)
        self.children = []

    @property
    def matrix_world(self):
        tx, ty, tz = self.location
        sx, sy, sz = self.scale
        return FakeMatrix.from_translation(tx, ty, tz) @ FakeMatrix(
            (
                (sx, 0.0, 0.0, 0.0),
                (0.0, sy, 0.0, 0.0),
                (0.0, 0.0, sz, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )


def load_adapter():
    fake_bpy = ModuleType("bpy")
    fake_bpy.context = SimpleNamespace(
        view_layer=SimpleNamespace(update=lambda: None),
    )
    fake_mathutils = ModuleType("mathutils")
    fake_mathutils.Vector = object
    fake_materials = ModuleType("blendmax_blender.blender_materials")
    fake_materials.MaterialBuilder = object
    fake_errors = ModuleType("blendmax_blender.errors")
    fake_errors.BlendMaxImportError = RuntimeError
    fake_manifest = ModuleType("blendmax_blender.manifest")
    fake_manifest.ManifestIndex = object
    fake_models = ModuleType("blendmax_blender.models")
    fake_models.ImportSummary = object
    fake_models.ObjectRecord = object
    fake_models.PackageContents = object
    fake_placement = ModuleType("blendmax_blender.placement")
    fake_placement.bounds_from_points = lambda points: None
    fake_placement.grounded_anchor = lambda bounds: (0.0, 0.0, 0.0)
    fake_placement.hierarchy_bounds = lambda parent_ids, object_bounds: {}
    fake_placement.merge_bounds = lambda items: None

    adapter_path = Path(__file__).resolve().parents[1] / "blendmax_blender" / "blender_adapter.py"
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._controller_parent_inverse_test",
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
            "blendmax_blender.errors": fake_errors,
            "blendmax_blender.manifest": fake_manifest,
            "blendmax_blender.models": fake_models,
            "blendmax_blender.placement": fake_placement,
        },
    ):
        spec.loader.exec_module(module)
    return module


def test_anisotropic_bounds_scale_preserves_rotated_direct_child_and_grandchild_world_matrices():
    adapter = load_adapter()
    controller = FakeController()
    child = FakeChild(
        FakeMatrix.from_translation(2.0, -1.0, 4.0)
        @ FakeMatrix.from_rotation_scale(
            math.radians(23.0),
            math.radians(-31.0),
            math.radians(17.0),
            1.2,
            0.7,
            1.8,
        ),
        parent=controller,
    )
    grandchild = FakeChild(
        FakeMatrix.from_translation(-0.5, 0.25, 0.75)
        @ FakeMatrix.from_rotation_scale(
            math.radians(-11.0),
            math.radians(9.0),
            math.radians(28.0),
            0.9,
            1.1,
            0.6,
        ),
        parent=child,
    )
    controller.children.append(child)
    child.children.append(grandchild)

    child_world_before = child.matrix_world.copy()
    grandchild_world_before = grandchild.matrix_world.copy()
    child_basis_before = child.matrix_basis.copy()
    parent_inverse_before = child.matrix_parent_inverse.copy()

    adapter.BlenderAdapter._apply_bounds_scale(
        controller,
        (2.0, 4.0, 6.0),
    )

    assert controller.scale == (2.0, 4.0, 6.0)
    assert not child.matrix_parent_inverse.almost_equal(parent_inverse_before)
    assert child.matrix_parent_inverse.almost_equal(
        controller.matrix_world.inverted() @ FakeMatrix.from_translation(3.0, 5.0, 7.0)
    )
    assert child.matrix_basis.almost_equal(child_basis_before)
    assert child.matrix_world.almost_equal(child_world_before)
    assert grandchild.matrix_world.almost_equal(grandchild_world_before)
