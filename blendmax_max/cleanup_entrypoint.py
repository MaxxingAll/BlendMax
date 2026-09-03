"""Interactive 3ds Max entry point for Join Mesh by Material."""

from __future__ import annotations

import traceback
from dataclasses import replace

from .alpha_opacity import confirm_alpha_opacity, find_alpha_opacity_geometry
from .cleanup import build_cleanup_plan
from .errors import BlendMaxError, CleanupError
from .max_cleanup_adapter import MaxCleanupAdapter


def run_interactive() -> None:
    adapter = MaxCleanupAdapter()
    try:
        snapshots = adapter.snapshot_scene()
        root_id = adapter.selected_root_id()
        plan = build_cleanup_plan(snapshots, root_id)
        plan = adapter.classify_shape_like_geometry(plan)
        if plan.shape_ids and not adapter.confirm_shape_deletion(plan):
            raise CleanupError(
                "Cleanup cannot continue please remove the {0} Shapes first".format(
                    len(plan.shape_ids)
                )
            )

        alpha_findings = find_alpha_opacity_geometry(
            adapter,
            plan.visible_geometry_ids,
        )
        alpha_decision = confirm_alpha_opacity(adapter, alpha_findings)
        if alpha_decision.action == "CANCEL":
            return

        protected_geometry_ids = frozenset(alpha_decision.protected_geometry_ids)
        protected_material_ids = frozenset(alpha_decision.protected_material_ids)
        joinable_geometry_ids = tuple(
            node_id
            for node_id in plan.visible_geometry_ids
            if node_id not in protected_geometry_ids
        )
        joinable_plan = replace(
            plan,
            visible_geometry_ids=joinable_geometry_ids,
        )

        if not joinable_geometry_ids:
            adapter.notify(
                (
                    "No geometry was joined.\n\n"
                    "Alpha/Opacity protection kept all {0} detected geometry node(s) "
                    "separate. No destructive cleanup was performed."
                ).format(len(protected_geometry_ids)),
                "BlendMax Cleanup Skipped",
            )
            return

        material_analysis = adapter.analyze_duplicate_materials(joinable_plan)
        approved_material_merges = tuple(
            candidate
            for candidate in material_analysis.candidates
            if adapter.confirm_material_merge(candidate)
        )
        if not adapter.confirm_with_materials(
            joinable_plan,
            approved_material_merges,
            material_analysis.differing_name_groups,
        ):
            return

        import pymxs  # type: ignore

        try:
            with pymxs.undo(True):
                summary = adapter.execute(joinable_plan, approved_material_merges)
        except Exception:
            if adapter.requires_undo:
                try:
                    pymxs.runundo()
                except Exception:
                    pass
            raise

        summary["protected_geometry_count"] = len(protected_geometry_ids)
        summary["protected_material_count"] = len(protected_material_ids)

        warning_text = ""
        if summary["warnings"]:
            warning_text = "\n\nWarnings:\n- " + "\n- ".join(summary["warnings"])
        adapter.notify(
            (
                "Join Mesh by Material complete.\n\n"
                "Input meshes joined: {input_mesh_count}\n"
                "Output material meshes: {output_mesh_count}\n"
                "Identical material sets merged: {merged_material_set_count}\n"
                "Original materials replaced: {replaced_material_count}\n"
                "Shape objects deleted: {deleted_shape_count}\n"
                "Alpha/Opacity materials protected: {protected_material_count}\n"
                "Geometry kept separate: {protected_geometry_count}\n"
                "Nested groups removed: {removed_group_count}"
                "{warning_text}"
            ).format(warning_text=warning_text, **summary),
            "BlendMax Cleanup Complete",
        )
    except BlendMaxError as exc:
        adapter.notify(str(exc), "BlendMax: {0}".format(exc.code))
    except Exception as exc:
        print(traceback.format_exc())
        adapter.notify(
            "Unexpected cleanup error: {0}\n\nSee the Python listener for details.".format(
                exc
            ),
            "BlendMax Cleanup Failed",
        )
