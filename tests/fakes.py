"""Fake Blender node/tree objects, module loaders, and the stream doubles
shared by the archive-hardening suites.

The Blender material builder only touches bpy through `bpy.data` and the
shader-node factory, so tests can drive `_build_shader` with these minimal
stand-ins instead of requiring a real Blender install. `load_blender_module`
executes a blendmax_blender source file with stub ``bpy``/``mathutils``
installed, which is how the scene and materials suites import those modules
without Blender. The scene doubles
(`FakeMatrix`, `FakeMeshObject`, `FakeEmptyObject`) model the world-matrix
and parenting reads those suites exercise.
The stream doubles simulate a member stream that
out-produces its declared size -- which can only be done at the `ZipFile.open`
boundary, the layer the actual-byte budget sits above.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock
from unittest.mock import patch


class FakeSocket:
    def __init__(self, name, identifier=None, default_value=None):
        self.name = name
        self.identifier = identifier if identifier is not None else name
        self.default_value = default_value


class FakeSockets:
    def __init__(self, sockets):
        self._items = [
            socket if isinstance(socket, FakeSocket) else FakeSocket(socket)
            for socket in sockets
        ]

    def get(self, name):
        return next((item for item in self._items if item.name == name), None)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        found = self.get(key)
        if found is None:
            raise KeyError(key)
        return found


class FakeNode:
    PRINCIPLED_INPUTS = (
        "Base Color", "Base Weight", "Metallic", "Roughness", "IOR",
        "Specular IOR Level", "Specular Tint", "Transmission Weight", "Alpha",
        "Thin Wall", "Diffuse Roughness", "Anisotropic IOR Level",
        "Anisotropic Rotation", "Coat Weight", "Coat Roughness", "Coat IOR",
        "Coat Tint", "Sheen Weight", "Sheen Roughness", "Sheen Tint",
        "Subsurface Weight", "Emission Color", "Emission Strength",
        "Thin Film Thickness", "Thin Film IOR", "Normal",
    )

    def __init__(self, node_type):
        self.type = node_type
        self.label = ""
        self.location = (0.0, 0.0)
        if node_type == "ShaderNodeBsdfPrincipled":
            self.inputs = FakeSockets(self.PRINCIPLED_INPUTS)
            self.outputs = FakeSockets(("BSDF",))
        elif node_type == "ShaderNodeRGBToBW":
            self.inputs = FakeSockets(("Color",))
            self.outputs = FakeSockets(("Val",))
        elif node_type == "ShaderNodeMath":
            self.inputs = FakeSockets(("Value", "Value_001", "Value_002"))
            self.outputs = FakeSockets(("Value",))
            self.operation = ""
        else:
            raise AssertionError("Unexpected fake node type: {0}".format(node_type))


class FakeNodes:
    def __init__(self):
        self.created = []

    def new(self, node_type):
        node = FakeNode(node_type)
        self.created.append(node)
        return node


class FakeLinks:
    def __init__(self):
        self.created = []

    def new(self, output, target):
        self.created.append((output, target))


class FakeTree:
    def __init__(self):
        self.nodes = FakeNodes()
        self.links = FakeLinks()


def load_materials_module():
    fake_bpy = ModuleType("bpy")
    module_path = (
        Path(__file__).resolve().parents[1]
        / "blendmax_blender"
        / "blender_materials.py"
    )
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._materials_test",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load BlendMax material builder test module.")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"bpy": fake_bpy}):
        spec.loader.exec_module(module)
    return module


class _InflatingStream:
    """A member stream whose read() returns more bytes than it consumed."""

    def __init__(self, inner, factor):
        self._inner = inner
        self._factor = factor

    def read(self, size=-1):
        data = self._inner.read(size)
        return data * self._factor if data else data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _PumpingStream:
    """A member stream that emits ``total`` bytes in fixed-size pieces."""

    def __init__(self, total, piece):
        self._left = total
        self._piece = piece

    def read(self, size=-1):
        if self._left <= 0:
            return b""
        allowed = self._piece if size is None or size < 0 else min(self._piece, size)
        allowed = min(allowed, self._left)
        self._left -= allowed
        return b"z" * allowed

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _stream_for(target, build):
    """Patch ZipFile.open so ``target``'s stream is replaced by build(stream).

    Used by the #50 lying-header tests. Real zipfile verifies CRC and declared
    sizes when a member is read to the end, so a stream that lies about its
    size can only be simulated at the stream boundary -- which is exactly the
    layer the actual-byte budget sits above.
    """

    real_open = zipfile.ZipFile.open

    def wrapper(self, name_or_info, *args, **kwargs):
        stream = real_open(self, name_or_info, *args, **kwargs)
        name = getattr(name_or_info, "filename", name_or_info)
        if name == target:
            return build(stream)
        return stream

    return mock.patch.object(zipfile.ZipFile, "open", wrapper)


class FakeVector:
    """Minimal stand-in for ``mathutils.Vector``, shared by the scene suites."""

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

    @classmethod
    def from_translation(cls, x, y, z):
        return cls.translation_scale((x, y, z), (1.0, 1.0, 1.0))

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

    def almost_equal(self, other, tolerance=1e-9):
        return all(
            abs(left - right) <= tolerance
            for left_row, right_row in zip(self.rows, other.rows)
            for left, right in zip(left_row, right_row)
        )


class FakeMeshObject:
    type = "MESH"

    def __init__(self, location, bound_box, parent=None, matrix_basis=None):
        self.children = []
        self.parent = parent
        self.bound_box = bound_box
        self.data = SimpleNamespace(vertices=(object(),))
        self.properties = {}
        self.matrix_parent_inverse = FakeMatrix.identity()
        if matrix_basis is None:
            matrix_basis = FakeMatrix.translation_scale(location, (1.0, 1.0, 1.0))
        self._matrix_basis = matrix_basis.copy()

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, value):
        # Blender derives a parent's `children` tuple from each object's
        # `parent` pointer; keep both sides of that relationship in sync so
        # `controller.children` reads the same way it does in a real scene.
        old = getattr(self, "_parent", None)
        if old is not None and self in old.children:
            old.children.remove(self)
        self._parent = value
        if value is not None and self not in value.children:
            value.children.append(self)

    @property
    def matrix_basis(self):
        return self._matrix_basis

    @property
    def location(self):
        return self._matrix_basis.translation

    @property
    def matrix_world(self):
        if self.parent is None:
            return self._matrix_basis.copy()
        return (
            self.parent.matrix_world @ self.matrix_parent_inverse @ self._matrix_basis
        )

    @matrix_world.setter
    def matrix_world(self, value):
        if self.parent is None:
            self._matrix_basis = value.copy()
            return
        self._matrix_basis = (
            self.parent.matrix_world @ self.matrix_parent_inverse
        ).inverted() @ value

    def __setitem__(self, key, value):
        self.properties[key] = value


class FakeEmptyObject:
    def __init__(self, name):
        self.name = name
        self.type = "EMPTY"
        self.data = None
        self.children = []
        self.parent = None
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
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, value):
        old = getattr(self, "_parent", None)
        if old is not None and self in old.children:
            old.children.remove(self)
        self._parent = value
        if value is not None and self not in value.children:
            value.children.append(self)

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


def load_blender_module(file_name, *, vector, bpy=None):
    """Execute a blendmax_blender source file with stub bpy/mathutils modules.

    The Blender-side modules import ``bpy`` and ``mathutils`` at module level,
    so the tests exercise the real source by executing it with fakes installed
    in ``sys.modules``. ``vector`` becomes ``mathutils.Vector`` (its uses are
    per-suite); ``bpy`` lets a suite add the ``data``/``context`` attributes
    its code paths need.
    """

    module_name = "blendmax_blender." + Path(file_name).stem
    fake_bpy = bpy if bpy is not None else ModuleType("bpy")
    fake_mathutils = ModuleType("mathutils")
    fake_mathutils.Vector = vector
    module_path = Path(__file__).resolve().parents[1] / "blendmax_blender" / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load {0} for the tests.".format(module_name))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"bpy": fake_bpy, "mathutils": fake_mathutils}):
        spec.loader.exec_module(module)
    return module
