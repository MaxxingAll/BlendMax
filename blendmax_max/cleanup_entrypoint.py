"""Interactive 3ds Max entry point for Join Mesh by Material."""

from __future__ import annotations

import traceback

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
        material_analysis = adapter.analyze_duplicate_materials(plan)
        approved_material_merges = tuple(
            candidate
            for candidate in material_analysis.candidates
            if adapter.confirm_material_merge(candidate)
        )
        if not adapter.confirm_with_materials(
            plan,
            approved_material_merges,
            material_analysis.differing_name_groups,
        ):
            return

        import pymxs  # type: ignore

        try:
            with pymxs.undo(True):
                summary = adapter.execute(plan, approved_material_merges)
        except Exception:
            if adapter.requires_undo:
                try:
                    pymxs.runundo()
                except Exception:
                    pass
            raise

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
