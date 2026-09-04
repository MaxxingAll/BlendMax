"""Fake Blender node/tree objects and a materials-module loader.

The Blender material builder only touches bpy through `bpy.data` and the
shader-node factory, so tests can drive `_build_shader` with these minimal
stand-ins instead of requiring a real Blender install.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
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
