from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blendmax_max.errors import ExportError
from blendmax_max.max_adapter import MaxRuntimeAdapter


class FakeColor:
    r = 255.0
    g = 127.5
    b = 0.0
    a = 255.0


class FakeUnits:
    DisplayType = "Generic"

    @staticmethod
    def decodeValue(value):
        return 1000.0


class FakeRenderers:
    current = object()


class FakeRuntime:
    undefined = object()
    units = FakeUnits()
    renderers = FakeRenderers()
    VRayMtl = object()
    maxFileName = "Example.max"

    @staticmethod
    def maxVersion():
        return [27000, 66, 0, 27, 3, 0, 30874, 2025, ".3"]

    @staticmethod
    def vrayVersion():
        return '#("7.00.02", "00000", "6c03966c")'

    @staticmethod
    def classOf(value):
        if isinstance(value, FakeColor):
            return "Color"
        return "V_Ray_7__update_4"


class MaxAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MaxRuntimeAdapter(runtime=FakeRuntime())

    def test_normalizes_max_color_to_zero_one(self):
        supported, value = self.adapter._primitive_value(FakeColor())
        self.assertTrue(supported)
        self.assertEqual(value, [1.0, 0.5, 0.0, 1.0])

    def test_detects_target_environment(self):
        metadata = self.adapter.source_metadata()
        self.assertEqual(metadata["max_version"], "2025.3")
        self.assertEqual(
            metadata["vray"]["version"],
            '#("7.00.02", "00000", "6c03966c")',
        )
        self.assertEqual(metadata["vray"]["parsed_version"], "7.00.02")
        self.assertEqual(
            metadata["compatibility"]["supported_vray_range"],
            "7.00.x to 7.40.x",
        )
        self.assertTrue(metadata["compatibility"]["max_matches_target"])
        self.assertTrue(metadata["compatibility"]["vray_matches_target"])
        self.assertEqual(metadata["compatibility"]["warnings"], [])

    def test_accepts_upper_supported_vray_release_family(self):
        class UpperRangeRuntime(FakeRuntime):
            @staticmethod
            def vrayVersion():
                return "V-Ray 7.40.02 for x64"

        metadata = MaxRuntimeAdapter(runtime=UpperRangeRuntime()).source_metadata()
        self.assertEqual(metadata["vray"]["parsed_version"], "7.40.02")
        self.assertTrue(metadata["compatibility"]["vray_matches_target"])
        self.assertEqual(metadata["compatibility"]["warnings"], [])

    def test_warns_for_vray_release_above_supported_range(self):
        class NewerRuntime(FakeRuntime):
            @staticmethod
            def vrayVersion():
                return '#("7.50.00", "00000", "future")'

        metadata = MaxRuntimeAdapter(runtime=NewerRuntime()).source_metadata()
        self.assertFalse(metadata["compatibility"]["vray_matches_target"])
        self.assertEqual(len(metadata["compatibility"]["warnings"]), 1)
        self.assertIn("7.00.x to 7.40.x", metadata["compatibility"]["warnings"][0])

    def test_warns_for_vray_release_below_supported_range(self):
        class OlderRuntime(FakeRuntime):
            @staticmethod
            def vrayVersion():
                return '#("6.20.00", "00000", "older")'

        metadata = MaxRuntimeAdapter(runtime=OlderRuntime()).source_metadata()
        self.assertFalse(metadata["compatibility"]["vray_matches_target"])
        self.assertEqual(len(metadata["compatibility"]["warnings"]), 1)

    def test_prunes_unneeded_vray_defaults(self):
        filtered = self.adapter._filter_material_properties(
            "VRayMtl",
            {
                "Diffuse": [1.0, 0.0, 0.0, 1.0],
                "reflection_glossiness": 0.7,
                "reflection_lockIOR": False,
                "reflection_subdivs": 8,
                "unrelated_internal_value": 123,
            },
        )
        self.assertIn("Diffuse", filtered)
        self.assertIn("reflection_glossiness", filtered)
        self.assertIs(filtered["reflection_lockIOR"], False)
        self.assertNotIn("reflection_subdivs", filtered)
        self.assertNotIn("unrelated_internal_value", filtered)

    def test_keeps_controls_only_for_connected_map_slot(self):
        controls = self.adapter._connected_map_controls(
            "VRayMtl",
            {
                "texmap_diffuse_on": True,
                "texmap_diffuse_multiplier": 100.0,
                "texmap_bump_on": True,
                "texmap_bump_multiplier": 30.0,
            },
            ["Diffuse"],
        )
        self.assertEqual(
            controls,
            {
                "texmap_diffuse_on": True,
                "texmap_diffuse_multiplier": 100.0,
            },
        )

    def test_matches_reflection_roughness_to_glossiness_controls(self):
        controls = self.adapter._connected_map_controls(
            "VRayMtl",
            {
                "texmap_reflectionGlossiness_on": False,
                "texmap_reflectionGlossiness_multiplier": 37.0,
                "texmap_reflection_on": True,
            },
            ["Reflection roughness"],
        )
        self.assertEqual(
            controls,
            {
                "texmap_reflectionGlossiness_on": False,
                "texmap_reflectionGlossiness_multiplier": 37.0,
            },
        )

    def test_v01_exports_geometry_but_not_shapes(self):
        self.assertTrue(self.adapter._is_exportable_superclass("GeometryClass"))
        self.assertFalse(self.adapter._is_exportable_superclass("Shape"))

    def test_texture_references_keep_graph_owner_and_resolve_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            texture = root / "maps" / "wood.png"
            texture.parent.mkdir()
            texture.write_bytes(b"texture")

            class RelativeRuntime(FakeRuntime):
                maxFilePath = str(root)

            references = MaxRuntimeAdapter(
                runtime=RelativeRuntime()
            ).discover_texture_references(
                {
                    "graph": [
                        {
                            "id": "tex_42",
                            "kind": "texture",
                            "parameters": {"filename": "maps/wood.png"},
                        },
                        {
                            "id": "mat_7",
                            "kind": "material",
                            "parameters": {"filename": "stale.png"},
                        },
                    ]
                }
            )

            self.assertEqual(len(references), 1)
            self.assertEqual(references[0]["graph_node_id"], "tex_42")
            self.assertEqual(references[0]["parameter"], "filename")
            self.assertEqual(references[0]["raw_path"], "maps/wood.png")
            self.assertEqual(references[0]["resolved_path"], str(texture))

    def test_fbx_settings_are_restored_after_success(self):
        class PluginManager:
            @staticmethod
            def loadClass(_value):
                return True

        class FBXRuntime:
            FBXEXPORTER = object()
            FBXEXP = object()
            pluginManager = PluginManager()

            def __init__(self):
                self.calls = []

            def FBXExporterSetParam(self, *args):
                self.calls.append(args)
                return True

            @staticmethod
            def Name(value):
                return value

            @staticmethod
            def exportFile(path, *_args, **_kwargs):
                Path(path).write_bytes(b"fbx")

        runtime = FBXRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            warnings = MaxRuntimeAdapter(runtime=runtime).export_selected_fbx(
                Path(temporary) / "geometry.fbx"
            )

        self.assertEqual(warnings, [])
        self.assertEqual(runtime.calls[0], ("PushSettings",))
        self.assertEqual(runtime.calls[1], ("ResetExport",))
        self.assertEqual(runtime.calls[-1], ("PopSettings",))

    def test_fbx_settings_are_restored_after_export_failure(self):
        class PluginManager:
            @staticmethod
            def loadClass(_value):
                return True

        class FailingFBXRuntime:
            FBXEXPORTER = object()
            FBXEXP = object()
            pluginManager = PluginManager()

            def __init__(self):
                self.calls = []

            def FBXExporterSetParam(self, *args):
                self.calls.append(args)
                return True

            @staticmethod
            def Name(value):
                return value

            @staticmethod
            def exportFile(*_args, **_kwargs):
                raise RuntimeError("simulated failure")

        runtime = FailingFBXRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ExportError):
                MaxRuntimeAdapter(runtime=runtime).export_selected_fbx(
                    Path(temporary) / "geometry.fbx"
                )

        self.assertEqual(runtime.calls[0], ("PushSettings",))
        self.assertEqual(runtime.calls[-1], ("PopSettings",))

    def _group_export_adapter(self, always_expand=False):
        class Node:
            def __init__(self, handle, name, group_head=False):
                self.handle = handle
                self.name = name
                self.group_head = group_head

        group = Node(101, "AssetGroup", group_head=True)
        mesh = Node(102, "Mesh")
        ignored = Node(103, "IgnoredLight")
        previous = Node(104, "PreviouslySelected")

        class GroupRuntime:
            undefined = object()

            def __init__(self):
                self.selection = [previous]
                self.group_is_open = False
                self.group_calls = []

            @staticmethod
            def getHandleByAnim(node):
                return node.handle

            @staticmethod
            def isGroupHead(node):
                return node.group_head

            def isOpenGroupHead(self, _node):
                return self.group_is_open

            def setGroupOpen(self, _node, is_open):
                self.group_is_open = bool(is_open)
                self.group_calls.append(bool(is_open))

            @staticmethod
            def Array(*nodes):
                return list(nodes)

            def clearSelection(self):
                self.selection = []

            def select(self, nodes):
                selected = list(nodes)
                if mesh in selected and (always_expand or not self.group_is_open):
                    selected.append(ignored)
                self.selection = selected

        runtime = GroupRuntime()
        adapter = MaxRuntimeAdapter(runtime=runtime)
        adapter._nodes_by_id = {
            "101": group,
            "102": mesh,
        }
        return adapter, runtime, group, mesh, ignored, previous

    def test_prepared_export_opens_group_and_restores_scene_state(self):
        adapter, runtime, group, mesh, ignored, previous = self._group_export_adapter()

        with adapter.prepared_export(
            ("101", "102"),
            selection_ids=("102",),
        ) as export_names:
            self.assertTrue(runtime.group_is_open)
            self.assertEqual(runtime.selection, [mesh])
            self.assertNotIn(ignored, runtime.selection)
            self.assertEqual(set(export_names), {"101", "102"})
            self.assertTrue(group.name.startswith("BM_"))
            self.assertTrue(mesh.name.startswith("BM_"))

        self.assertFalse(runtime.group_is_open)
        self.assertEqual(runtime.group_calls, [True, False])
        self.assertEqual(runtime.selection, [previous])
        self.assertEqual(group.name, "AssetGroup")
        self.assertEqual(mesh.name, "Mesh")

    def test_prepared_export_restores_group_after_body_failure(self):
        adapter, runtime, group, mesh, _ignored, previous = self._group_export_adapter()

        with self.assertRaisesRegex(RuntimeError, "simulated body failure"):
            with adapter.prepared_export(
                ("101", "102"),
                selection_ids=("102",),
            ):
                raise RuntimeError("simulated body failure")

        self.assertFalse(runtime.group_is_open)
        self.assertEqual(runtime.group_calls, [True, False])
        self.assertEqual(runtime.selection, [previous])
        self.assertEqual(group.name, "AssetGroup")
        self.assertEqual(mesh.name, "Mesh")

    def test_prepared_export_rejects_unexpected_group_selection_expansion(self):
        adapter, runtime, group, mesh, ignored, previous = self._group_export_adapter(
            always_expand=True
        )

        with self.assertRaisesRegex(ExportError, "expanded the BlendMax export selection"):
            with adapter.prepared_export(
                ("101", "102"),
                selection_ids=("102",),
            ):
                self.fail("An expanded selection must not reach the FBX exporter.")

        self.assertFalse(runtime.group_is_open)
        self.assertEqual(runtime.selection, [previous])
        self.assertEqual(group.name, "AssetGroup")
        self.assertEqual(mesh.name, "Mesh")
        self.assertEqual(ignored.name, "IgnoredLight")


if __name__ == "__main__":
    unittest.main()
