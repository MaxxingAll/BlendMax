"""Public import orchestration kept separate from Blender's UI operator."""

from __future__ import annotations

from .package import open_blendmax


def import_blendmax(path, context=None, apply_recommended_scale: bool = True):
    import bpy

    from .blender_adapter import BlenderAdapter

    active_context = context or bpy.context
    with open_blendmax(path) as package:
        return BlenderAdapter(active_context).import_package(
            package,
            apply_recommended_scale=apply_recommended_scale,
        )
