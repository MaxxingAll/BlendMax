from __future__ import annotations

import copy
import unittest

from blendmax_max.cleanup import CleanupPlan
from blendmax_max.errors import CleanupError
from blendmax_max.max_cleanup_adapter import (
    MaterialMergeCandidate,
    MaxCleanupAdapter,
)


class Node:
    def __init__(
        self,
        handle,
        name,
        parent=None,
        group_head=False,
        open_group=False,
        face_count=1,
        material=None,
    ):
        self.handle = handle
        self.name = name
        self.parent = parent
        self.group_head = group_head
        self.open_group = open_group
        self.face_count = face_count
        self.material = material


class SelectionRuntime:
    undefined = object()

    def __init__(self, selection, query_response=True):
        self.selection = selection
        self.query_response = query_response
        self.query_calls = []

    @staticmethod
    def getHandleByAnim(node):
        return node.handle

    @staticmethod
    def isGroupHead(node):
        return node.group_head

    @staticmethod
    def isOpenGroupHead(node):
        return node.group_head and node.open_group

    def queryBox(self, message, title=None):
        self.query_calls.append((message, title))
        return self.query_response


class MaxCleanupSelectionTests(unittest.TestCase):
    def test_accepts_one_selected_group_head(self):
        root = Node(1, "Root", group_head=True, open_group=True)
        adapter = MaxCleanupAdapter(runtime=SelectionRuntime([root]))

        self.assertEqual(adapter.selected_root_id(), "1")

    def test_rejects_closed_group_selection_expansion_with_pink_box_guidance(self):
        root = Node(1, "Root", group_head=True)
        nested = Node(2, "Nested", parent=root, group_head=True)
        mesh_a = Node(3, "MeshA", parent=root)
        mesh_b = Node(4, "MeshB", parent=nested)
        adapter = MaxCleanupAdapter(
            runtime=SelectionRuntime([root, nested, mesh_a, mesh_b])
        )

        with self.assertRaisesRegex(CleanupError, "select the Pink Box"):
            adapter.selected_root_id()

    def test_rejects_expanded_members_without_open_group_head(self):
        root = Node(1, "Root", group_head=True)
        mesh_a = Node(2, "MeshA", parent=root)
        mesh_b = Node(3, "MeshB", parent=root)
        adapter = MaxCleanupAdapter(runtime=SelectionRuntime([mesh_a, mesh_b]))

        with self.assertRaisesRegex(CleanupError, "select the Pink Box"):
            adapter.selected_root_id()

    def test_rejects_selected_closed_group_head(self):
        root = Node(1, "Root", group_head=True, open_group=False)
        adapter = MaxCleanupAdapter(runtime=SelectionRuntime([root]))

        with self.assertRaisesRegex(CleanupError, "select the Pink Box"):
            adapter.selected_root_id()

    def test_rejects_selection_across_two_root_groups(self):
        root_a = Node(1, "RootA", group_head=True)
        root_b = Node(2, "RootB", group_head=True)
        mesh_a = Node(3, "MeshA", parent=root_a)
        mesh_b = Node(4, "MeshB", parent=root_b)
        adapter = MaxCleanupAdapter(runtime=SelectionRuntime([mesh_a, mesh_b]))

        with self.assertRaisesRegex(CleanupError, "Root Group not Detected"):
            adapter.selected_root_id()

    def test_rejects_ungrouped_selection(self):
        mesh = Node(1, "Mesh")
        adapter = MaxCleanupAdapter(runtime=SelectionRuntime([mesh]))

        with self.assertRaisesRegex(CleanupError, "Root Group not Detected"):
            adapter.selected_root_id()

    def test_shape_deletion_confirmation_reports_detected_count(self):
        root = Node(1, "Root", group_head=True)
        runtime = SelectionRuntime([root])
        adapter = MaxCleanupAdapter(runtime=runtime)
        plan = CleanupPlan(
            root_id="1",
            visible_geometry_ids=("2",),
            shape_ids=("3", "4", "5"),
            removable_group_ids=(),
        )

        self.assertTrue(adapter.confirm_shape_deletion(plan))
        self.assertIn("contains 3 Spline/Segment as Shapes", runtime.query_calls[0][0])
        self.assertEqual(
            runtime.query_calls[0][1],
            "BlendMax: Shape Objects Detected",
        )

    def test_zero_face_geometry_is_added_to_shape_deletion_plan(self):
        class Mesh:
            def __init__(self, face_count):
                self.numfaces = face_count

        class GeometryRuntime(SelectionRuntime):
            def __init__(self):
                super().__init__([])
                self.deleted = []

            @staticmethod
            def snapshotAsMesh(node):
                return Mesh(node.face_count)

            def delete(self, value):
                self.deleted.append(value)

        root = Node(1, "Root", group_head=True, open_group=True)
        polygon_mesh = Node(2, "Polygon", parent=root, face_count=20)
        line_geometry = Node(3, "LineGeometry", parent=root, face_count=0)
        runtime = GeometryRuntime()
        adapter = MaxCleanupAdapter(runtime=runtime)
        adapter._nodes_by_id = {
            "1": root,
            "2": polygon_mesh,
            "3": line_geometry,
        }
        plan = CleanupPlan(
            root_id="1",
            visible_geometry_ids=("2", "3"),
            shape_ids=("4",),
            removable_group_ids=(),
        )

        classified = adapter.classify_shape_like_geometry(plan)

        self.assertEqual(classified.visible_geometry_ids, ("2",))
        self.assertEqual(classified.shape_ids, ("4", "3"))
        self.assertEqual(len(runtime.deleted), 2)


class GraphAnimatable:
    def __init__(
        self,
        handle,
        name,
        class_name,
        superclass,
        properties=None,
        sub_materials=None,
        sub_textures=None,
    ):
        self.handle = handle
        self.name = name
        self.class_name = class_name
        self.superclass = superclass
        self.properties = dict(properties or {})
        self.sub_materials = list(sub_materials or [])
        self.sub_textures = list(sub_textures or [])


class MaterialGraphRuntime(SelectionRuntime):
    def __init__(self):
        super().__init__([])
        self.next_handle = 1000

    @staticmethod
    def classOf(value):
        return value.class_name

    @staticmethod
    def superClassOf(value):
        return value.superclass

    @staticmethod
    def getPropNames(value):
        return list(value.properties)

    @staticmethod
    def getProperty(value, property_name):
        return value.properties[str(property_name)]

    @staticmethod
    def getNumSubMtls(value):
        return len(value.sub_materials)

    @staticmethod
    def getSubMtl(value, index):
        return value.sub_materials[index - 1][1]

    @staticmethod
    def getSubMtlSlotName(value, index):
        return value.sub_materials[index - 1][0]

    @staticmethod
    def getNumSubTexmaps(value):
        return len(value.sub_textures)

    @staticmethod
    def getSubTexmap(value, index):
        return value.sub_textures[index - 1][1]

    @staticmethod
    def getSubTexmapSlotName(value, index):
        return value.sub_textures[index - 1][0]

    def copy(self, value):
        cloned = copy.deepcopy(value)
        cloned.handle = self.next_handle
        self.next_handle += 1
        return cloned


class MaterialFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.runtime = MaterialGraphRuntime()
        self.adapter = MaxCleanupAdapter(runtime=self.runtime)

    @staticmethod
    def bitmap(handle, name="Bitmap", filename="maps/albedo.png"):
        return GraphAnimatable(
            handle,
            name,
            "Bitmaptexture",
            "Texmap",
            properties={
                "filename": filename,
                "filtering": 1,
                "coordsChannel": 1,
            },
        )

    @classmethod
    def physical(
        cls,
        handle,
        name="Paint",
        roughness=0.35,
        filename="maps/albedo.png",
    ):
        return GraphAnimatable(
            handle,
            name,
            "PhysicalMaterial",
            "Material",
            properties={
                "base_weight": 1.0,
                "roughness": roughness,
                "metalness": 0.0,
                "coat": 0.2,
            },
            sub_textures=[
                ("Base Color Map", cls.bitmap(handle + 100, filename=filename)),
            ],
        )

    def test_identical_physical_material_graphs_share_fingerprint(self):
        first = self.physical(1, name="Paint")
        second = self.physical(2, name="PAINT")
        second.sub_textures[0][1].name = "A differently arranged Slate node"

        self.assertEqual(
            self.adapter.material_fingerprint(first),
            self.adapter.material_fingerprint(second),
        )

    def test_physical_material_property_or_nested_map_difference_is_detected(self):
        baseline = self.physical(1)
        rougher = self.physical(2, roughness=0.6)
        different_bitmap = self.physical(3, filename="maps/other.png")

        baseline_fingerprint = self.adapter.material_fingerprint(baseline)
        self.assertNotEqual(
            baseline_fingerprint,
            self.adapter.material_fingerprint(rougher),
        )
        self.assertNotEqual(
            baseline_fingerprint,
            self.adapter.material_fingerprint(different_bitmap),
        )

    def test_material_class_is_part_of_fingerprint(self):
        physical = self.physical(1)
        vray = GraphAnimatable(
            2,
            "Paint",
            "VRayMtl",
            "Material",
            properties={"diffuse": "red", "reflection_glossiness": 0.65},
            sub_textures=[("Diffuse", self.bitmap(102))],
        )

        self.assertNotEqual(
            self.adapter.material_fingerprint(physical),
            self.adapter.material_fingerprint(vray),
        )

    def test_duplicate_analysis_merges_only_matching_setup_cluster(self):
        first = self.physical(1, name="0134_DimGray")
        second = self.physical(2, name="0134_DimGray")
        different = self.physical(3, name="0134_DimGray", roughness=0.8)
        root = Node(10, "Root", group_head=True, open_group=True)
        meshes = [
            Node(11, "A", root, material=first),
            Node(12, "B", root, material=second),
            Node(13, "C", root, material=different),
        ]
        self.adapter._nodes_by_id = {
            "10": root,
            "11": meshes[0],
            "12": meshes[1],
            "13": meshes[2],
        }
        plan = CleanupPlan(
            root_id="10",
            visible_geometry_ids=("11", "12", "13"),
            shape_ids=(),
            removable_group_ids=(),
        )

        analysis = self.adapter.analyze_duplicate_materials(plan)

        self.assertEqual(len(analysis.candidates), 1)
        candidate = analysis.candidates[0]
        self.assertEqual(candidate.display_name, "0134_DimGray")
        self.assertEqual(candidate.merged_name, "0134_DimGray_MERGED")
        self.assertEqual(candidate.materials, (first, second))
        self.assertEqual(
            analysis.differing_name_groups,
            (("0134_DimGray", 3, 2),),
        )

    def test_multiple_identical_variants_receive_distinct_merged_names(self):
        materials = [
            self.physical(1, name="Paint", roughness=0.2),
            self.physical(2, name="Paint", roughness=0.2),
            self.physical(3, name="Paint", roughness=0.8),
            self.physical(4, name="Paint", roughness=0.8),
        ]
        root = Node(10, "Root", group_head=True, open_group=True)
        self.adapter._nodes_by_id = {"10": root}
        mesh_ids = []
        for index, material in enumerate(materials, start=11):
            node = Node(index, "Mesh", root, material=material)
            self.adapter._nodes_by_id[str(index)] = node
            mesh_ids.append(str(index))
        plan = CleanupPlan("10", tuple(mesh_ids), (), ())

        analysis = self.adapter.analyze_duplicate_materials(plan)

        self.assertEqual(
            {candidate.merged_name for candidate in analysis.candidates},
            {"Paint_MERGED_01", "Paint_MERGED_02"},
        )

    def test_approved_merge_copies_master_and_maps_every_original(self):
        first = self.physical(1, name="Paint")
        second = self.physical(2, name="Paint")
        candidate = MaterialMergeCandidate(
            display_name="Paint",
            merged_name="Paint_MERGED",
            fingerprint=self.adapter.material_fingerprint(first),
            materials=(first, second),
        )

        replacements = self.adapter._material_replacements((candidate,))

        self.assertIs(replacements["1"], replacements["2"])
        self.assertIsNot(replacements["1"], first)
        self.assertEqual(replacements["1"].name, "Paint_MERGED")

    def test_merge_confirmation_reports_name_and_count(self):
        first = self.physical(1, name="Paint")
        second = self.physical(2, name="Paint")
        candidate = MaterialMergeCandidate(
            display_name="Paint",
            merged_name="Paint_MERGED",
            fingerprint="fingerprint",
            materials=(first, second),
        )

        self.assertTrue(self.adapter.confirm_material_merge(candidate))
        message, title = self.runtime.query_calls[0]
        self.assertIn('2 separate materials named "Paint"', message)
        self.assertIn('Merge them into "Paint_MERGED"', message)
        self.assertEqual(title, "BlendMax: Identical Materials Detected")


if __name__ == "__main__":
    unittest.main()
