"""Renderer-independent fidelity helpers for 3ds Max Physical Material.

These helpers resolve source parameters into the semantic values needed by a
Blender shader builder. They intentionally do not create Blender nodes, which
keeps the source-model behavior testable without a Blender runtime.
"""

from __future__ import annotations

from typing import Mapping, Tuple

from .material_graph import clamp01, physical_roughness, rgba, scalar


def transparency_roughness(parameters: Mapping[str, object],
                            reflection_roughness: float) -> float:
    """Resolve Physical Material transparency roughness."""
    if bool(parameters.get("trans_roughness_lock", True)):
        return clamp01(reflection_roughness)
    return physical_roughness(parameters, "trans_roughness")


def transparency_depth_inverse(parameters: Mapping[str, object]) -> float:
    """Return inverse transparency depth for a Beer-Lambert approximation."""
    depth = max(0.0, scalar(parameters, "trans_depth", 0.0))
    return 0.0 if depth == 0.0 else 1.0 / depth


def sss_parameters(parameters: Mapping[str, object]) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float], float]:
    """Resolve SSS colors and effective depth."""
    color = rgba(parameters.get("sss_color"), (1.0, 1.0, 1.0, 1.0))
    scatter_color = rgba(parameters.get("sss_scatter_color"), color)
    depth = max(0.0, scalar(parameters, "sss_depth", 10.0))
    scale = max(0.0, scalar(parameters, "sss_scale", 1.0))
    return color, scatter_color, depth * scale


def emission_luminance(parameters: Mapping[str, object]) -> float:
    """Return resolved Physical Material surface luminance in nits."""
    amount = clamp01(scalar(parameters, "emission", 0.0))
    luminance = max(0.0, scalar(parameters, "emit_luminance", 1500.0))
    return amount * luminance


def coating_affect_factors(parameters: Mapping[str, object]) -> Tuple[float, float]:
    """Return coat underlying-color and roughness effect strengths."""
    weight = clamp01(scalar(parameters, "coating", 0.0))
    affect_color = clamp01(scalar(parameters, "coat_affect_color", 0.5))
    affect_roughness = clamp01(scalar(parameters, "coat_affect_roughness", 0.5))
    return weight * affect_color, weight * affect_roughness


def coat_affected_color(color, parameters: Mapping[str, object]):
    """Apply Max's documented coating darkening/saturation power rule."""
    color_factor, _ = coating_affect_factors(parameters)
    exponent = 1.0 + color_factor
    return tuple(max(0.0, min(1.0, float(channel))) ** exponent for channel in color[:3]) + (color[3],)
