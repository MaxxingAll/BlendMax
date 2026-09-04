from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeNode, FakeSocket, FakeSockets, load_materials_module


materials = load_materials_module()
_set_default = materials._set_default
_socket = materials._socket


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
        node = FakeNode("ShaderNodeBsdfPrincipled")
        node.inputs = FakeSockets([target])

        _set_default(node, ("Roughness",), 0.5)

        self.assertEqual(target.default_value, "original")

    def test_set_default_updates_resolved_socket(self):
        target = FakeSocket("Specular", default_value="original")
        node = FakeNode("ShaderNodeBsdfPrincipled")
        node.inputs = FakeSockets([target])

        _set_default(node, ("Specular IOR Level", "Specular"), 0.25)

        self.assertEqual(target.default_value, 0.25)


if __name__ == "__main__":
    unittest.main()
