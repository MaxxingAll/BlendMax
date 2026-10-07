"""Regression tests for blender_adapter._DataSnapshot.rollback.

A failed import must remove every datablock it created. The rollback used to
track only objects, meshes, materials, images, texts and collections, so the
curves, armatures, cameras, lights and actions the FBX importer can also create
were left behind as orphan data.
"""

from __future__ import annotations

import unittest
from types import ModuleType, SimpleNamespace

try:
    from fakes import load_blender_module
except ImportError:  # dotted-module invocation from the repository root
    from tests.fakes import load_blender_module


class FakeDatablock:
    def __init__(self, name, users=0):
        self.name = name
        self.users = users

    def __repr__(self):
        return "FakeDatablock({0!r})".format(self.name)


class FakeDataCollection:
    def __init__(self, *items):
        self.items = list(items)

    def __iter__(self):
        return iter(list(self.items))

    def add(self, item):
        self.items.append(item)
        return item

    def remove(self, item, do_unlink=False):
        self.items.remove(item)


_COLLECTIONS = (
    "objects",
    "meshes",
    "curves",
    "armatures",
    "cameras",
    "lights",
    "actions",
    "materials",
    "images",
    "texts",
    "collections",
)


def _fake_bpy():
    bpy = ModuleType("bpy")
    bpy.data = SimpleNamespace(
        **{
            name: FakeDataCollection(FakeDatablock("existing " + name))
            for name in _COLLECTIONS
        }
    )
    return bpy


class DataSnapshotRollbackTests(unittest.TestCase):
    def setUp(self):
        self.bpy = _fake_bpy()
        self.adapter = load_blender_module(
            "blender_adapter.py", vector=object, bpy=self.bpy
        )

    def test_rollback_removes_every_datablock_type_the_import_created(self):
        snapshot = self.adapter._DataSnapshot()
        for name in _COLLECTIONS:
            getattr(self.bpy.data, name).add(FakeDatablock("new " + name))

        snapshot.rollback()

        for name in _COLLECTIONS:
            with self.subTest(collection=name):
                self.assertEqual(
                    [item.name for item in getattr(self.bpy.data, name)],
                    ["existing " + name],
                )

    def test_rollback_keeps_new_object_data_that_is_still_used(self):
        snapshot = self.adapter._DataSnapshot()
        for name in ("meshes", "curves", "armatures", "cameras", "lights"):
            getattr(self.bpy.data, name).add(FakeDatablock("shared " + name, users=1))

        snapshot.rollback()

        for name in ("meshes", "curves", "armatures", "cameras", "lights"):
            with self.subTest(collection=name):
                self.assertIn(
                    "shared " + name,
                    [item.name for item in getattr(self.bpy.data, name)],
                )

    def test_rollback_leaves_pre_existing_data_alone(self):
        snapshot = self.adapter._DataSnapshot()

        snapshot.rollback()

        for name in _COLLECTIONS:
            with self.subTest(collection=name):
                self.assertEqual(len(getattr(self.bpy.data, name).items), 1)


if __name__ == "__main__":
    unittest.main()
