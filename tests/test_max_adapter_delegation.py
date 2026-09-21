"""Tests for the Roadmap #4 facade/module boundary.

``MaxRuntimeAdapter`` keeps one thin delegation per moved method because
``MaxCleanupAdapter`` inherits the class, and the extracted modules call each
other through the adapter instance so subclass overrides keep governing the
public operations. These tests pin that boundary: forwarding targets and
arguments, subclass resolution, the unchanged call signatures, the constants
that stay importable from the facade, and override behaviour driven through the
public facade operations.
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


class MaxAdapterSubclassDispatchTests(unittest.TestCase):
    """Overrides of moved helpers must keep governing the public operations.

    The split moved helpers out of the class, but internal call sites stay on
    the adapter instance (``adapter._resolve_texture_path(...)``), so a
    subclass override is still the implementation that runs. These tests pin
    that compatibility through the public facade operations, not through the
    module helpers.
    """

    def test_source_metadata_uses_overridden_max_version_parser(self):
        calls = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _parse_max_version(self, raw_version):
                calls.append(list(raw_version))
                return "OVERRIDDEN-MAX"

        metadata = ProjectAdapter(runtime=_MetaRuntime()).source_metadata()

        self.assertEqual(calls, [["2025", ".3 Update"]])
        self.assertEqual(metadata["max_version"], "OVERRIDDEN-MAX")
        self.assertFalse(metadata["compatibility"]["max_matches_target"])
        self.assertEqual(len(metadata["compatibility"]["warnings"]), 1)

    def test_source_metadata_uses_overridden_vray_version_parser(self):
        calls = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _parse_vray_version(self, raw_version):
                calls.append(raw_version)
                return (7, 1, 5)

        metadata = ProjectAdapter(runtime=_MetaRuntime()).source_metadata()

        self.assertEqual(calls, ['#("7.00.02", "00000", "probe")'])
        self.assertEqual(metadata["vray"]["parsed_version"], "7.01.05")
        self.assertTrue(metadata["compatibility"]["vray_matches_target"])

    def test_bounds_in_meters_uses_overridden_evaluated_bounds(self):
        calls = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _evaluated_mesh_bounds(self, node):
                calls.append(getattr(node, "name", None))
                return [10.0, 20.0, 30.0], [40.0, 50.0, 60.0]

        adapter = ProjectAdapter(runtime=_BoundsRuntime())
        adapter._nodes_by_id = {"1": _DispatchNode()}
        bounds = adapter.bounds_in_meters(("1",))

        self.assertEqual(calls, ["Bounded"])
        self.assertEqual(bounds["minimum"], [0.01, 0.02, 0.03])
        self.assertEqual(bounds["maximum"], [0.04, 0.05, 0.06])

    def test_bounds_fallback_uses_overridden_node_bounds(self):
        calls = []

        class ProjectAdapter(MaxRuntimeAdapter):
            @staticmethod
            def _node_bounds(node):
                calls.append(getattr(node, "name", None))
                return [-1.0, -2.0, -3.0], [1.0, 2.0, 3.0]

        adapter = ProjectAdapter(runtime=_FailingEvaluatedRuntime())
        adapter._nodes_by_id = {"1": _DispatchNode()}
        bounds = adapter.bounds_in_meters(("1",))

        self.assertEqual(calls, ["Bounded"])
        self.assertEqual(bounds["minimum"], [-0.001, -0.002, -0.003])
        self.assertEqual(bounds["maximum"], [0.001, 0.002, 0.003])

    def test_texture_discovery_uses_overridden_path_resolver(self):
        calls = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _resolve_texture_path(self, value):
                calls.append(value)
                return "/project/maps/" + value

        references = ProjectAdapter(runtime=object()).discover_texture_references({
            "graph": [
                {"id": "tex_1", "kind": "texture",
                 "parameters": {"filename": "wood.png"}},
            ]
        })

        self.assertEqual(calls, ["wood.png"])
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["resolved_path"], "/project/maps/wood.png")

    def test_material_graph_uses_overridden_helpers(self):
        log = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _primitive_properties(self, animatable):
                log.append("properties")
                return {"OVR": 1}

            def _filter_material_properties(self, class_name, properties):
                log.append("filter")
                return {"FILTERED": True}

            def _connected_map_controls(self, class_name, properties, slot_names):
                log.append("connected")
                return {"CONNECTED": True}

        adapter = ProjectAdapter(runtime=_MaterialRuntime())
        node = _DispatchNode(name="Object")
        node.material = _DispatchMaterial()
        adapter._nodes_by_id = {"1": node}
        graph = adapter.capture_material_graph(("1",))

        self.assertEqual(log, ["properties", "filter", "connected"])
        entry = graph["graph"][0]
        self.assertEqual(entry["parameters"], {"FILTERED": True, "CONNECTED": True})
        self.assertEqual(entry["parameter_count"], 2)

    def test_material_graph_uses_overridden_primitive_value(self):
        seen = []

        class ProjectAdapter(MaxRuntimeAdapter):
            def _primitive_value(self, value):
                seen.append(value)
                return True, "OVR"

        adapter = ProjectAdapter(runtime=_MaterialRuntime())
        node = _DispatchNode(name="Object")
        node.material = _DispatchMaterial()
        adapter._nodes_by_id = {"1": node}
        graph = adapter.capture_material_graph(("1",))

        self.assertEqual(seen, [123])
        entry = graph["graph"][0]
        self.assertEqual(entry["parameters"], {"Diffuse": "OVR"})


class _Units:
    DisplayType = "Generic"

    @staticmethod
    def decodeValue(_value):
        return 1000.0


class _Renderers:
    current = object()


class _MetaRuntime:
    undefined = object()
    units = _Units()
    renderers = _Renderers()
    VRayMtl = object()
    maxFileName = "Scene.max"

    @staticmethod
    def maxVersion():
        return [2025, ".3 Update"]

    @staticmethod
    def vrayVersion():
        return '#("7.00.02", "00000", "probe")'

    @staticmethod
    def classOf(_value):
        return "V_Ray_7"


class _BoundsRuntime:
    undefined = object()
    units = _Units()


class _FailingEvaluatedRuntime(_BoundsRuntime):
    numverts = 1

    def snapshotAsMesh(self, _node):
        return self

    def getVert(self, _mesh, _index):
        raise RuntimeError("vertex read failed")


class _MaterialRuntime:
    undefined = object()

    @staticmethod
    def getHandleByAnim(value):
        return value.handle

    @staticmethod
    def classOf(_value):
        return "VRayMtl"

    @staticmethod
    def getPropNames(_animatable):
        return ["Diffuse"]

    @staticmethod
    def getProperty(_animatable, _name):
        return 123

    @staticmethod
    def getNumSubMtls(_value):
        return 0

    @staticmethod
    def getNumSubTexmaps(_value):
        return 0


class _DispatchNode:
    def __init__(self, name="Bounded"):
        self.name = name
        self.handle = 1


class _DispatchMaterial:
    handle = 7
    name = "Mat"


if __name__ == "__main__":
    unittest.main()
