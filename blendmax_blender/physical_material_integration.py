"""Blender-side integration for Physical Material fidelity helpers."""

from __future__ import annotations

from .material_graph import ParameterView
from .physical_material_fidelity import (
    coat_affected_color,
    emission_luminance,
    sss_parameters,
    transparency_depth_inverse,
    transparency_roughness,
)


_PATCHED = False
_ORIGINAL = None


def _apply_physical_fidelity(self, tree, graph_node, material, stack, x, y):
    output = _ORIGINAL(self, tree, graph_node, material, stack, x, y)
    bsdf = getattr(output, "node", None)
    if bsdf is None:
        return output
    parameters = ParameterView(graph_node.parameters)
    base_color = bsdf.inputs.get("Base Color")
    if base_color is not None and not base_color.is_linked:
        try:
            # Coat Tint is not a strict physical equivalent to this power-rule approximation.
            base_color.default_value = coat_affected_color(base_color.default_value, parameters)
        except (TypeError, ValueError):
            pass
    try:
        reflection_roughness = float(bsdf.inputs["Roughness"].default_value)
        trans_roughness = transparency_roughness(parameters, reflection_roughness)
        if not bool(parameters.get("trans_roughness_lock", True)):
            material["blendmax_transparency_roughness"] = trans_roughness
            # Only replace shared Roughness when both values agree within a small tolerance.
            if abs(trans_roughness - reflection_roughness) < 1e-6:
                bsdf.inputs["Roughness"].default_value = trans_roughness
    except (KeyError, TypeError, ValueError):
        pass
    inverse_depth = transparency_depth_inverse(parameters)
    if inverse_depth > 0.0:
        # Preserve inverse depth as metadata for a future Beer-Lambert implementation.
        material["blendmax_transparency_depth_inverse"] = inverse_depth
    # Do not materialize SSS defaults on materials whose scattering weight is 0.
    # This contract intentionally follows the numeric Subsurface Weight resolved by the builder;
    # texture-driven weight cannot be inferred here.
    try:
        sss_weight = max(0.0, min(1.0, float(parameters.get("scattering", 0.0))))
    except (TypeError, ValueError):
        sss_weight = 0.0
    if sss_weight > 0.0:
        sss_color, scatter_color, sss_depth = sss_parameters(parameters)
        if sss_depth > 0.0:
            # blendmax_sss_* describes active SSS fidelity metadata, not merely configured geometry.
            material["blendmax_sss_depth"] = sss_depth
            material["blendmax_sss_scatter_color"] = scatter_color[:3]
            socket = bsdf.inputs.get("Subsurface Radius")
            if socket is not None and not socket.is_linked:
                socket.default_value = sss_color[:3]
            scale_socket = bsdf.inputs.get("Subsurface Scale")
            if scale_socket is not None and not scale_socket.is_linked:
                scale_socket.default_value = sss_depth
    luminance = emission_luminance(parameters)
    if luminance > 0.0:
        emission_strength = bsdf.inputs.get("Emission Strength")
        if emission_strength is not None and not emission_strength.is_linked:
            emission_strength.default_value = luminance
        # Physical Material emission is specified in nits; Blender's emission strength is only an approximation.
        material["blendmax_emission_luminance_nits"] = luminance
    emit_kelvin = parameters.get("emit_kelvin")
    if emit_kelvin is not None:
        try:
            # Kelvin metadata is retained because cross-version renderer color-temperature handling differs.
            material["blendmax_emission_kelvin"] = float(emit_kelvin)
        except (TypeError, ValueError):
            pass
    return output


def install() -> None:
    """Install the Physical Material builder integration once per class state.

    A live Blender session upgraded from a pre-hardening release cannot recover the
    previous wrapper because that wrapper has no ownership marker. Disable/re-enable
    the add-on or restart Blender when upgrading across that boundary.
    """
    global _PATCHED, _ORIGINAL
    from . import blender_materials
    current = blender_materials.MaterialBuilder._build_physical_mtl
    if _PATCHED and current is _apply_physical_fidelity:
        return
    original = getattr(current, "_blendmax_original", None)
    if original is not None:
        _ORIGINAL = original
    else:
        _ORIGINAL = current
    _apply_physical_fidelity._blendmax_original = _ORIGINAL
    blender_materials.MaterialBuilder._build_physical_mtl = _apply_physical_fidelity
    _PATCHED = True
