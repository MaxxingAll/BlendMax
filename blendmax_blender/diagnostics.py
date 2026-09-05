"""Pure-Python diagnostics for BlendMax importer results."""

from __future__ import annotations

from .material_compatibility import known_unmapped_parameters
from .models import ImportSummary


# Backwards-compatible public name for callers/tests that used the V-Ray
# registry directly. New code should use the shared material-compatibility
# registry instead.
KNOWN_VRAY_UNMAPPED_PARAMETERS = known_unmapped_parameters("vraymtl")

_GLOSSINESS_MARKER = (
    " has separate reflection and refraction glossiness values; Blender's "
    "Principled shader uses a single roughness for both, so the refraction "
    "roughness is approximated."
)


def categorize_import_messages(summary: ImportSummary, package) -> ImportSummary:
    """Move known material limitations into grouped informational notes."""
    notes = list(summary.notes)
    known_by_class = {}
    for node in package.manifest.graph:
        known = known_unmapped_parameters(node.class_name)
        if not known:
            continue
        keys = tuple(key for key in node.parameters if key.casefold() in known)
        if keys:
            known_by_class.setdefault(node.class_name.casefold(), set()).update(
                key.casefold() for key in keys
            )

    for class_name in sorted(known_by_class):
        fields = sorted(known_by_class[class_name])
        notes.append(
            "({0}) is not supported yet, wait for future BlendMax updates".format(
                "/".join(fields)
            )
        )

    glossiness_materials = []
    warnings = []
    for warning in summary.warnings:
        if warning.endswith(_GLOSSINESS_MARKER):
            glossiness_materials.append(warning[: -len(_GLOSSINESS_MARKER)])
        else:
            warnings.append(warning)
    if glossiness_materials:
        notes.append(
            "({0}){1}".format(
                "/".join(dict.fromkeys(glossiness_materials)), _GLOSSINESS_MARKER
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
