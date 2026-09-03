from __future__ import annotations

import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from blendmax_max.cleanup_entrypoint import run_interactive
from blendmax_max.max_cleanup_adapter import (
    DuplicateMaterialAnalysis,
    MaterialMergeCandidate,
)
from blendmax_max.models import SceneNode


class RefusingShapeAdapter:
    def __init__(self):
        self.main_confirmation_called = False
        self.notifications = []

    @staticmethod
    def snapshot_scene():
        return [
            SceneNode(
                node_id="root",
                name="Root",
                node_type="Dummy",
                superclass="Helper",
                is_group_head=True,
                exportable=False,
            ),
            SceneNode(
                node_id="mesh",
                name="Mesh",
                node_type="Editable_Poly",
                superclass="GeometryClass",
                parent_id="root",
            ),
            SceneNode(
                node_id="shape",
                name="Line",
                node_type="Line",
                superclass="Shape",
                parent_id="root",
                exportable=False,
            ),
        ]

    @staticmethod
    def selected_root_id():
        return "root"

    @staticmethod
    def classify_shape_like_geometry(plan):
        return plan

    @staticmethod
    def confirm_shape_deletion(_plan):
        return False

    def confirm(self, _plan):
        self.main_confirmation_called = True
        return True

    def notify(self, message, title):
        self.notifications.append((message, title))


class CleanupEntrypointTests(unittest.TestCase):
    def test_refusing_shape_deletion_stops_before_main_confirmation(self):
        adapter = RefusingShapeAdapter()
        with patch(
            "blendmax_max.cleanup_entrypoint.MaxCleanupAdapter",
            return_value=adapter,
        ):
            run_interactive()

        self.assertFalse(adapter.main_confirmation_called)
        self.assertEqual(
            adapter.notifications,
            [
                (
                    "Cleanup cannot continue please remove the 1 Shapes first",
                    "BlendMax: CLEANUP_FAILED",
                )
            ],
        )

    def test_approved_identical_material_set_reaches_execute(self):
        candidate = MaterialMergeCandidate(
            display_name="Paint",
            merged_name="Paint_MERGED",
            fingerprint="same",
            materials=(object(), object()),
        )

        class MergeAdapter:
            requires_undo = False

            def __init__(self):
                self._nodes_by_id = {}
                self.confirmed_merges = None
                self.executed_merges = None
                self.notifications = []

            @staticmethod
            def snapshot_scene():
                return [
                    SceneNode(
                        node_id="root",
                        name="Root",
                        node_type="Dummy",
                        superclass="Helper",
                        is_group_head=True,
                        exportable=False,
                    ),
                    SceneNode(
                        node_id="mesh",
                        name="Mesh",
                        node_type="Editable_Poly",
                        superclass="GeometryClass",
                        parent_id="root",
                    ),
                ]

            @staticmethod
            def selected_root_id():
                return "root"

            @staticmethod
            def classify_shape_like_geometry(plan):
                return plan

            @staticmethod
            def analyze_duplicate_materials(_plan):
                return DuplicateMaterialAnalysis((candidate,), ())

            @staticmethod
            def confirm_material_merge(_candidate):
                return True

            def confirm_with_materials(self, _plan, merges, _differing):
                self.confirmed_merges = merges
                return True

            def execute(self, _plan, merges):
                self.executed_merges = merges
                return {
                    "input_mesh_count": 1,
                    "output_mesh_count": 1,
                    "merged_material_set_count": 1,
                    "replaced_material_count": 2,
                    "deleted_shape_count": 0,
                    "removed_group_count": 0,
                    "warnings": [],
                }

            def notify(self, message, title):
                self.notifications.append((message, title))

        adapter = MergeAdapter()
        pymxs = types.SimpleNamespace(
            undo=lambda _enabled: nullcontext(),
            runundo=lambda: None,
        )
        with patch(
            "blendmax_max.cleanup_entrypoint.MaxCleanupAdapter",
            return_value=adapter,
        ), patch.dict(sys.modules, {"pymxs": pymxs}):
            run_interactive()

        self.assertEqual(adapter.confirmed_merges, (candidate,))
        self.assertEqual(adapter.executed_merges, (candidate,))
        self.assertIn(
            "Identical material sets merged: 1",
            adapter.notifications[0][0],
        )

    def test_refused_identical_material_merge_keeps_materials_separate(self):
        candidate = MaterialMergeCandidate(
            display_name="Paint",
            merged_name="Paint_MERGED",
            fingerprint="same",
            materials=(object(), object()),
        )

        class RefusingMergeAdapter:
            requires_undo = False

            def __init__(self):
                self._nodes_by_id = {}
                self.executed_merges = None

            @staticmethod
            def snapshot_scene():
                return [
                    SceneNode(
                        node_id="root",
                        name="Root",
                        node_type="Dummy",
                        superclass="Helper",
                        is_group_head=True,
                        exportable=False,
                    ),
                    SceneNode(
                        node_id="mesh",
                        name="Mesh",
                        node_type="Editable_Poly",
                        superclass="GeometryClass",
                        parent_id="root",
                    ),
                ]

            @staticmethod
            def selected_root_id():
                return "root"

            @staticmethod
            def classify_shape_like_geometry(plan):
                return plan

            @staticmethod
            def analyze_duplicate_materials(_plan):
                return DuplicateMaterialAnalysis((candidate,), ())

            @staticmethod
            def confirm_material_merge(_candidate):
                return False

            @staticmethod
            def confirm_with_materials(_plan, merges, _differing):
                return merges == ()

            def execute(self, _plan, merges):
                self.executed_merges = merges
                return {
                    "input_mesh_count": 1,
                    "output_mesh_count": 1,
                    "merged_material_set_count": 0,
                    "replaced_material_count": 0,
                    "deleted_shape_count": 0,
                    "removed_group_count": 0,
                    "warnings": [],
                }

            @staticmethod
            def notify(_message, _title):
                return None

        adapter = RefusingMergeAdapter()
        pymxs = types.SimpleNamespace(
            undo=lambda _enabled: nullcontext(),
            runundo=lambda: None,
        )
        with patch(
            "blendmax_max.cleanup_entrypoint.MaxCleanupAdapter",
            return_value=adapter,
        ), patch.dict(sys.modules, {"pymxs": pymxs}):
            run_interactive()

        self.assertEqual(adapter.executed_merges, ())

    def test_merge_anyway_reaches_existing_path(self):
        adapter = types.SimpleNamespace()
        adapter.requires_undo = False
        adapter._nodes_by_id = {}
        adapter.notifications = []
        adapter.executed = False
        candidate = MaterialMergeCandidate(
            display_name="Leaves",
            merged_name="Leaves_MERGED",
            fingerprint="same",
            materials=(object(), object()),
        )

        def snapshot_scene():
            return [
                SceneNode("root", "Root", "Dummy", "Helper", is_group_head=True, exportable=False),
                SceneNode("mesh", "Mesh", "Editable_Poly", "GeometryClass", parent_id="root"),
            ]

        adapter.snapshot_scene = snapshot_scene
        adapter.selected_root_id = lambda: "root"
        adapter.classify_shape_like_geometry = lambda plan: plan
        adapter.analyze_duplicate_materials = lambda _plan: DuplicateMaterialAnalysis((candidate,), ())
        adapter.confirm_material_merge = lambda _candidate: True
        adapter.confirm_with_materials = lambda _plan, merges, _differing: merges == (candidate,)

        def execute(_plan, merges):
            adapter.executed = True
            adapter.executed_merges = merges
            return {
                "input_mesh_count": 1,
                "output_mesh_count": 1,
                "merged_material_set_count": 1,
                "replaced_material_count": 2,
                "deleted_shape_count": 0,
                "removed_group_count": 0,
                "warnings": [],
            }

        adapter.execute = execute
        adapter.notify = lambda message, title: adapter.notifications.append((message, title))
        pymxs = types.SimpleNamespace(undo=lambda _enabled: nullcontext(), runundo=lambda: None)
        findings = (object(),)
        decision = types.SimpleNamespace(
            action="MERGE",
            protected_geometry_ids=(),
            protected_material_ids=(),
        )
        with patch("blendmax_max.cleanup_entrypoint.MaxCleanupAdapter", return_value=adapter), \
             patch("blendmax_max.cleanup_entrypoint.find_alpha_opacity_geometry", return_value=findings), \
             patch("blendmax_max.cleanup_entrypoint.confirm_alpha_opacity", return_value=decision), \
             patch.dict(sys.modules, {"pymxs": pymxs}):
            run_interactive()

        self.assertTrue(adapter.executed)
        self.assertEqual(adapter.executed_merges, (candidate,))

    def test_alpha_cancel_never_reaches_execute(self):
        adapter = types.SimpleNamespace()
        adapter.requires_undo = False
        adapter._nodes_by_id = {}
        adapter.executed = False
        adapter.notify = lambda _message, _title: None
        adapter.snapshot_scene = lambda: [
            SceneNode("root", "Root", "Dummy", "Helper", is_group_head=True, exportable=False),
            SceneNode("mesh", "Mesh", "Editable_Poly", "GeometryClass", parent_id="root"),
        ]
        adapter.selected_root_id = lambda: "root"
        adapter.classify_shape_like_geometry = lambda plan: plan
        adapter.execute = lambda _plan, _merges: setattr(adapter, "executed", True)
        decision = types.SimpleNamespace(
            action="CANCEL",
            protected_geometry_ids=(),
            protected_material_ids=(),
        )
        with patch("blendmax_max.cleanup_entrypoint.MaxCleanupAdapter", return_value=adapter), \
             patch("blendmax_max.cleanup_entrypoint.find_alpha_opacity_geometry", return_value=(object(),)), \
             patch("blendmax_max.cleanup_entrypoint.confirm_alpha_opacity", return_value=decision):
            run_interactive()

        self.assertFalse(adapter.executed)

    def test_mixed_scene_still_joins_normal_geometry(self):
        candidate_material = object()
        adapter = types.SimpleNamespace()
        adapter.requires_undo = False
        adapter._nodes_by_id = {}
        adapter.notifications = []
        adapter.joined_plan_ids = None
        adapter.snapshot_scene = lambda: [
            SceneNode("root", "Root", "Dummy", "Helper", is_group_head=True, exportable=False),
            SceneNode("alpha", "Tree_01", "Editable_Poly", "GeometryClass", parent_id="root"),
            SceneNode("normal", "Rock_01", "Editable_Poly", "GeometryClass", parent_id="root"),
        ]
        adapter.selected_root_id = lambda: "root"
        adapter.classify_shape_like_geometry = lambda plan: plan
        adapter.analyze_duplicate_materials = lambda _plan: DuplicateMaterialAnalysis((), ())
        adapter.confirm_with_materials = lambda _plan, _merges, _differing: True

        def execute(plan, _merges):
            adapter.joined_plan_ids = plan.visible_geometry_ids
            return {
                "input_mesh_count": len(plan.visible_geometry_ids),
                "output_mesh_count": 1,
                "merged_material_set_count": 0,
                "replaced_material_count": 0,
                "deleted_shape_count": 0,
                "removed_group_count": 0,
                "warnings": [],
            }

        adapter.execute = execute
        adapter.notify = lambda message, title: adapter.notifications.append((message, title))
        decision = types.SimpleNamespace(
            action="SKIP",
            protected_geometry_ids=("alpha",),
            protected_material_ids=("protected",),
        )
        pymxs = types.SimpleNamespace(undo=lambda _enabled: nullcontext(), runundo=lambda: None)
        with patch("blendmax_max.cleanup_entrypoint.MaxCleanupAdapter", return_value=adapter), \
             patch("blendmax_max.cleanup_entrypoint.find_alpha_opacity_geometry", return_value=(object(),)), \
             patch("blendmax_max.cleanup_entrypoint.confirm_alpha_opacity", return_value=decision), \
             patch("blendmax_max.cleanup_entrypoint.is_protected_material", return_value=False), \
             patch.dict(sys.modules, {"pymxs": pymxs}):
            run_interactive()

        self.assertEqual(adapter.joined_plan_ids, ("normal",))


if __name__ == "__main__":
    unittest.main()
