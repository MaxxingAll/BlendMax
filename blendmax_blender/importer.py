"""Public import orchestration kept separate from Blender's UI operator."""

from __future__ import annotations

from .diagnostics import categorize_import_messages
from .models import ImportSummary
from .package import open_blendmax

# Backwards-compatible private name for existing internal callers.
_categorize_import_messages = categorize_import_messages


def import_blendmax(path, context=None, apply_recommended_scale: bool = True):
    import bpy

    from .blender_adapter import BlenderAdapter

    active_context = context or bpy.context
    with open_blendmax(path) as package:
        summary = BlenderAdapter(active_context).import_package(
            package,
            apply_recommended_scale=apply_recommended_scale,
        )
        return categorize_import_messages(summary, package)
