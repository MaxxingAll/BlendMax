"""Fake Blender node/tree objects, module loaders, and the stream doubles
shared by the archive-hardening suites.

The Blender material builder only touches bpy through `bpy.data` and the
shader-node factory, so tests can drive `_build_shader` with these minimal
stand-ins instead of requiring a real Blender install. `load_blender_module`
executes a blendmax_blender source file with stub ``bpy``/``mathutils``
installed, which is how the scene and materials suites import those modules
without Blender. The stream doubles simulate a member stream that
out-produces its declared size -- which can only be done at the `ZipFile.open`
boundary, the layer the actual-byte budget sits above.
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType
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
