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


if __name__ == "__main__":
    unittest.main()
