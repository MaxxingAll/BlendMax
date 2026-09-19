"""Tests for the Roadmap #4 facade/module boundary.

``MaxRuntimeAdapter`` keeps one thin delegation per moved method because
``MaxCleanupAdapter`` inherits the class. These tests pin that boundary:
forwarding targets and arguments, subclass resolution, the unchanged call
signatures, and the constants that stay importable from the facade.
"""

from __future__ import annotations

import inspect
import unittest
from unittest import mock

from blendmax_max import max_export, max_materials, max_scene
from blendmax_max.max_adapter import MaxRuntimeAdapter
from blendmax_max.max_cleanup_adapter import MaxCleanupAdapter


SENTINEL = object()

# (method, owning module, call arguments after the adapter)
MOVED_DELEGATIONS = (
    ("snapshot_scene", max_scene, ()),
    ("source_metadata", max_scene, ()),
    ("_parse_vray_version", max_scene, ("7.00.02",)),
    ("_parse_max_version", max_scene, (["2025", ".3"],)),
    ("bounds_in_meters", max_scene, (("1",),)),
    ("_node_bounds", max_scene, (SENTINEL,)),
    ("_evaluated_mesh_bounds", max_scene, (SENTINEL,)),
    ("_primitive_value", max_materials, (5,)),
    ("_primitive_properties", max_materials, (SENTINEL,)),
    ("_filter_material_properties", max_materials, ("VRayMtl", {})),
    ("_connected_map_controls", max_materials, ("VRayMtl", {}, ())),
    ("capture_material_graph", max_materials, (("1",),)),
    ("discover_texture_references", max_materials, ({},)),
    ("_resolve_texture_path", max_materials, ("maps/wood.png",)),
    ("prepared_export", max_export, (("1",),)),
    ("export_selected_fbx", max_export, ("geometry.fbx",)),
)

# The call contract as it existed before the split; the wrappers must not move it.
ORIGINAL_SIGNATURES = {
    "snapshot_scene": ("self",),
    "source_metadata": ("self",),
    "_parse_vray_version": ("self", "raw_version"),
    "_parse_max_version": ("self", "raw_version"),
    "bounds_in_meters": ("self", "payload_ids"),
    "_node_bounds": ("node",),
    "_evaluated_mesh_bounds": ("self", "node"),
    "_primitive_value": ("self", "value"),
    "_primitive_properties": ("self", "animatable"),
    "_filter_material_properties": ("self", "class_name", "properties"),
    "_connected_map_controls": ("self", "class_name", "properties", "slot_names"),
    "capture_material_graph": ("self", "payload_ids"),
    "discover_texture_references": ("self", "material_data"),
    "_resolve_texture_path": ("self", "value"),
    "prepared_export": ("self", "export_ids", "selection_ids"),
    "export_selected_fbx": ("self", "output_path"),
}


class MaxAdapterDelegationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MaxRuntimeAdapter(runtime=object())

    def test_facade_delegates_every_moved_method_to_its_module(self):
        self.assertEqual(len(MOVED_DELEGATIONS), 16)
        for name, module, args in MOVED_DELEGATIONS:
            with self.subTest(method=name):
                if name == "prepared_export":
                    with mock.patch.object(module, name) as patched:
                        with self.adapter.prepared_export(*args):
                            pass
                    patched.assert_called_once_with(self.adapter, ("1",), None)
                    continue
                with mock.patch.object(module, name, return_value=SENTINEL) as patched:
                    result = getattr(self.adapter, name)(*args)
                self.assertIs(result, SENTINEL)
                expected = args if name == "_node_bounds" else (self.adapter,) + args
                patched.assert_called_once_with(*expected)

    def test_cleanup_subclass_resolves_every_delegation(self):
        self.assertTrue(issubclass(MaxCleanupAdapter, MaxRuntimeAdapter))
        resolved = 0
        for name, _module, _args in MOVED_DELEGATIONS:
            with self.subTest(method=name):
                self.assertIs(
                    getattr(MaxCleanupAdapter, name),
                    getattr(MaxRuntimeAdapter, name),
                    "MaxCleanupAdapter no longer resolves %s through the facade" % name,
                )
            resolved += 1
        self.assertEqual(resolved, 16)

    def test_wrapper_signatures_match_the_pre_split_contract(self):
        self.assertEqual(len(ORIGINAL_SIGNATURES), 16)
        for name, expected in ORIGINAL_SIGNATURES.items():
            with self.subTest(method=name):
                signature = inspect.signature(getattr(MaxRuntimeAdapter, name))
                self.assertEqual(tuple(signature.parameters), expected)
        selection_default = inspect.signature(
            MaxRuntimeAdapter.prepared_export
        ).parameters["selection_ids"].default
        self.assertIsNone(selection_default)

    def test_constants_remain_importable_from_the_facade(self):
        from blendmax_max.max_adapter import (
            VRAY_MAP_SLOT_ALIASES,
            VRAY_MTL_PROPERTIES,
        )

        self.assertIs(VRAY_MTL_PROPERTIES, max_materials.VRAY_MTL_PROPERTIES)
        self.assertIs(VRAY_MAP_SLOT_ALIASES, max_materials.VRAY_MAP_SLOT_ALIASES)
        self.assertIn("diffuse", VRAY_MTL_PROPERTIES)
        self.assertEqual(
            VRAY_MAP_SLOT_ALIASES["reflectionroughness"],
            "reflectionglossiness",
        )


if __name__ == "__main__":
    unittest.main()
