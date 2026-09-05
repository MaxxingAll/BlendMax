"""Blender-side integration for Physical Material fidelity helpers."""

from __future__ import annotations

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

    parameters = graph_node.parameters

    # Max's coat can affect the underlying base/SSS color. Principled Coat Tint
    # is not equivalent, so apply the documented power-rule approximation when
    # the imported base color is a constant.
    base_color = bsdf.inputs.get("Base Color")
    if base_color is not None and not base_color.is_linked:
        try:
            base_color.default_value = coat_affected_color(
                base_color.default_value, parameters
            )
        except (TypeError, ValueError):
            pass

    # Max can unlock a separate transmission roughness while Principled uses a
    # shared surface roughness. Preserve the resolved value as metadata; only
    # replace the shared socket when the values agree.
    try:
        reflection_roughness = float(bsdf.inputs["Roughness"].default_value)
        trans_roughness = transparency_roughness(parameters, reflection_roughness)
        if not bool(parameters.get("trans_roughness_lock", True)):
            material["blendmax_transparency_roughness"] = trans_roughness
            if abs(trans_roughness - reflection_roughness) < 1e-6:
                bsdf.inputs["Roughness"].default_value = trans_roughness
    except (KeyError, TypeError, ValueError):
        pass

    # Principled BSDF has no direct transparency-depth socket. Preserve the
    # inverse-depth semantic for a future Beer-Lambert volume construction.
    inverse_depth = transparency_depth_inverse(parameters)
    if inverse_depth > 0.0:
        material["blendmax_transparency_depth_inverse"] = inverse_depth

    # Resolve SSS semantics and feed supported Principled sockets where present.
    sss_color, scatter_color, sss_depth = sss_parameters(parameters)
    if sss_depth > 0.0:
        material["blendmax_sss_depth"] = sss_depth
        material["blendmax_sss_scatter_color"] = scatter_color[:3]
        socket = bsdf.inputs.get("Subsurface Radius")
        if socket is not None and not socket.is_linked:
            socket.default_value = sss_color[:3]
        scale_socket = bsdf.inputs.get("Subsurface Scale")
        if scale_socket is not None and not scale_socket.is_linked:
            scale_socket.default_value = sss_depth

    # Physical Material emission is specified as surface luminance (nits).
    # Blender's emission strength is not a strict nit-equivalent, but this
    # preserves the source physical intent better than the old 1500-nit scale.
    luminance = emission_luminance(parameters)
    if luminance > 0.0:
        emission_strength = bsdf.inputs.get("Emission Strength")
        if emission_strength is not None and not emission_strength.is_linked:
            emission_strength.default_value = luminance
        material["blendmax_emission_luminance_nits"] = luminance

    # Kelvin emission has no universal one-to-one Principled socket across the
    # supported Blender versions. Preserve it rather than silently discarding it.
    emit_kelvin = parameters.get("emit_kelvin")
    if emit_kelvin is not None:
        try:
            material["blendmax_emission_kelvin"] = float(emit_kelvin)
        except (TypeError, ValueError):
            pass

    return output


def install() -> None:
    """Install the Physical Material builder integration once per process."""
    global _PATCHED, _ORIGINAL
    if _PATCHED:
        return

    from . import blender_materials

    _ORIGINAL = blender_materials.MaterialBuilder._build_physical_mtl
    blender_materials.MaterialBuilder._build_physical_mtl = _apply_physical_fidelity
    _PATCHED = True
