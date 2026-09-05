"""Shared compatibility metadata for imported 3ds Max material classes."""

from __future__ import annotations

from typing import FrozenSet, Mapping


# Parameter names are normalized with ``casefold()`` before comparison.
# Keep this registry intentionally declarative: translators remain responsible
# for producing Blender nodes; this table only defines known compatibility gaps.
KNOWN_UNMAPPED_PARAMETERS: Mapping[str, FrozenSet[str]] = {
    "vraymtl": frozenset({
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
    }),
    # Physical Material has intentionally no "known unmapped" registry yet.
    # Its translator is already implemented and future fidelity work should
    # classify gaps explicitly here as they are verified against Max.
    "physicalmaterial": frozenset(),
}


def known_unmapped_parameters(class_name: str) -> FrozenSet[str]:
    """Return normalized parameter names known to be intentional gaps."""
    return KNOWN_UNMAPPED_PARAMETERS.get(str(class_name).casefold(), frozenset())
