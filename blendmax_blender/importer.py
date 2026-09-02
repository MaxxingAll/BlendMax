"""Public import orchestration kept separate from Blender's UI operator."""

from __future__ import annotations

from .blender_materials import _KNOWN_VRAY_UNMAPPED_PARAMETERS
from .models import ImportSummary
from .package import open_blendmax


def _categorize_import_messages(summary: ImportSummary, package) -> ImportSummary:
    """Move expected limitations into grouped informational notes."""
    notes = list(summary.notes)

    supported_gap_fields = sorted(
        {
            key.casefold()
            for node in package.manifest.graph
            if node.class_name.casefold() == "vraymtl"
            for key in node.parameters
            if key.casefold() in _KNOWN_VRAY_UNMAPPED_PARAMETERS
        }
    )
    if supported_gap_fields:
        notes.append(
            "({0}) is not supported yet, wait for future BlendMax updates".format(
                "/".join(supported_gap_fields)
            )
        )

    glossiness_materials = []
    warnings = []
    glossiness_marker = (
        " has separate reflection and refraction glossiness values; Blender's "
        "Principled shader uses a single roughness for both, so the refraction "
        "roughness is approximated."
    )
    for warning in summary.warnings:
        if warning.endswith(glossiness_marker):
            glossiness_materials.append(warning[: -len(glossiness_marker)])
        else:
            warnings.append(warning)

    if glossiness_materials:
        notes.append(
            "({0}){1}".format(
                "/".join(dict.fromkeys(glossiness_materials)),
                glossiness_marker,
            )
        )

    return ImportSummary(
        asset_name=summary.asset_name,
        object_count=summary.object_count,
        material_count=summary.material_count,
        image_count=summary.image_count,
        warnings=tuple(warnings),
        notes=tuple(dict.fromkeys(notes)),
    )


def import_blendmax(path, context=None, apply_recommended_scale: bool = True):
    import bpy

    from .blender_adapter import BlenderAdapter

    active_context = context or bpy.context
    with open_blendmax(path) as package:
        summary = BlenderAdapter(active_context).import_package(
            package,
            apply_recommended_scale=apply_recommended_scale,
        )
        return _categorize_import_messages(summary, package)
