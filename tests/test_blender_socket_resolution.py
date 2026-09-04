from __future__ import annotations

import sys
import types
import unittest


if "bpy" not in sys.modules:
    sys.modules["bpy"] = types.ModuleType("bpy")

from blendmax_blender.blender_materials import _set_default, _socket


class FakeSocket:
    def __init__(self, name, identifier=None, default_value=None):
        self.name = name
        self.identifier = identifier if identifier is not None else name
        self.default_value = default_value


class FakeSockets:
    def __init__(self, sockets):
        self._sockets = list(sockets)

    def get(self, name):
        for socket in self._sockets:
            if socket.name == name:
                return socket
        return None

    def __iter__(self):
        return iter(self._sockets)


class FakeNode:
    def __init__(self, sockets):
        self.inputs = FakeSockets(sockets)


class SocketResolutionTests(unittest.TestCase):
    def test_exact_name_match(self):
        target = FakeSocket("Base Color")
        self.assertIs(_socket(FakeSockets([target]), "Base Color"), target)

    def test_fallback_name_match_uses_first_available_socket(self):
        target = FakeSocket("Specular")
        self.assertIs(
            _socket(
                FakeSockets([target]),
                "Specular IOR Level",
                "Specular",
            ),
            target,
        )

    def test_canonicalized_name_match(self):
        target = FakeSocket("ThinFilmThickness")
        self.assertIs(
            _socket(FakeSockets([target]), "Thin Film Thickness"),
            target,
        )

    def test_identifier_match(self):
        target = FakeSocket("Legacy", identifier="Thin Film IOR")
        self.assertIs(
            _socket(FakeSockets([target]), "Thin Film IOR"),
            target,
        )

    def test_missing_socket_returns_none(self):
        self.assertIsNone(
            _socket(FakeSockets([FakeSocket("Base Color")]), "Roughness")
        )

    def test_set_default_skips_missing_socket(self):
        target = FakeSocket("Base Color", default_value="original")
        node = FakeNode([target])

        _set_default(node, ("Roughness",), 0.5)

        self.assertEqual(target.default_value, "original")

    def test_set_default_updates_resolved_socket(self):
        target = FakeSocket("Specular")
        node = FakeNode([target])

        _set_default(node, ("Specular IOR Level", "Specular"), 0.25)

        self.assertEqual(target.default_value, 0.25)


if __name__ == "__main__":
    unittest.main()
