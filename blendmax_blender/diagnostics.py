"""Pure-Python diagnostics for BlendMax importer results."""

from __future__ import annotations

from .models import ImportSummary

KNOWN_VRAY_UNMAPPED_PARAMETERS = frozenset({
    "anisotropy_axis", "anisotropy_channel", "anisotropy_derivation", "brdf_type",
    "coat_darkening", "option_cutoff", "option_doublesided", "option_glossyfresnel",
    "option_opacitymode", "option_openpbrmode", "option_tracediffuse", "option_tracereflection",
    "option_tracerefraction", "reflection_affectalpha", "reflection_dimdistance",
    "reflection_dimdistance_falloff", "reflection_dimdistance_on", "reflection_fresnel",
    "reflection_maxdepth", "refraction_affectalpha", "refraction_affectshadows",
    "refraction_dispersion", "refraction_dispersion_on", "refraction_fogbias", "refraction_fogcolor",
    "refraction_fogdepth", "refraction_fogmult", "refraction_fogunitsscale_on",
    "refraction_maxdepth", "selfillumination_gi", "translucency_amount", "translucency_color",
    "translucency_fbcoeff", "translucency_multiplier", "translucency_on", "translucency_scattercoeff",
    "translucency_surfacelighting", "translucency_thickness",
})

_GLOSSINESS_MARKER = (
    " has separate reflection and refraction glossiness values; Blender's "
    "Principled shader uses a single roughness for both, so the refraction "
    "roughness is approximated."
)


def categorize_import_messages(summary: ImportSummary, package) -> ImportSummary:
    """Move expected V-Ray limitations into grouped informational notes."""
    notes = list(summary.notes)
    supported_gap_fields = sorted({
        key.casefold()
        for node in package.manifest.graph
        if node.class_name.casefold() == "vraymtl"
        for key in node.parameters
        if key.casefold() in KNOWN_VRAY_UNMAPPED_PARAMETERS
    })
    if supported_gap_fields:
        notes.append(
            "({0}) is not supported yet, wait for future BlendMax updates".format(
                "/".join(supported_gap_fields)
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


def build_import_summary_view(summary: ImportSummary) -> dict:
    """Return a stable, UI-neutral payload for the Blender import summary."""
    return {
        "asset_name": summary.asset_name,
        "object_count": int(summary.object_count),
        "material_count": int(summary.material_count),
        "image_count": int(summary.image_count),
        "warnings": tuple(summary.warnings),
        "notes": tuple(summary.notes),
    }
