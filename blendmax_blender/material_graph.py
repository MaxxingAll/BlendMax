"""Renderer-independent helpers for interpreting the Max material graph."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Tuple

from .models import GraphLink, GraphNode


_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_MAP_CONTROL_NAMES = {
    "diffuse": "diffuse",
    "reflection": "reflection",
    "refraction": "refraction",
    "bump": "bump",
    "reflectionroughness": "reflectionGlossiness",
    "reflectionglossiness": "reflectionGlossiness",
    "opacity": "opacity",
    "selfillumination": "self_illumination",
    "metalness": "metalness",
    "displace": "displacement",
}

_PHYSICAL_MAP_CONTROL_NAMES = {
    "baseweight": "base_weight_map_on",
    "baseweightmap": "base_weight_map_on",
    "basecolor": "base_color_map_on",
    "basecolormap": "base_color_map_on",
    "reflectionweight": "reflectivity_map_on",
    "reflectionweightmap": "reflectivity_map_on",
    "reflectivity": "reflectivity_map_on",
    "reflectivitymap": "reflectivity_map_on",
    "reflectioncolor": "refl_color_map_on",
    "reflectioncolormap": "refl_color_map_on",
    "roughness": "roughness_map_on",
    "roughnessmap": "roughness_map_on",
    "metalness": "metalness_map_on",
    "metalnessmap": "metalness_map_on",
    "transparency": "transparency_map_on",
    "transparencymap": "transparency_map_on",
    "transparencyweight": "transparency_map_on",
    "transparencyweightmap": "transparency_map_on",
    "transparencycolor": "trans_color_map_on",
    "transparencycolormap": "trans_color_map_on",
    "transparencyroughness": "trans_rough_map_on",
    "transparencyroughnessmap": "trans_rough_map_on",
    "ior": "trans_ior_map_on",
    "iormap": "trans_ior_map_on",
    "emission": "emission_map_on",
    "emissionmap": "emission_map_on",
    "emissionweight": "emission_map_on",
    "emissionweightmap": "emission_map_on",
    "emissioncolor": "emit_color_map_on",
    "emissioncolormap": "emit_color_map_on",
    "coatweight": "coat_map_on",
    "coatweightmap": "coat_map_on",
    "coating": "coat_map_on",
    "coatingmap": "coat_map_on",
    "coatingweight": "coat_map_on",
    "coatingweightmap": "coat_map_on",
    "coatcolor": "coat_color_map_on",
    "coatcolormap": "coat_color_map_on",
    "coatingcolor": "coat_color_map_on",
    "coatingcolormap": "coat_color_map_on",
    "coatroughness": "coat_rough_map_on",
    "coatroughnessmap": "coat_rough_map_on",
    "coatingroughness": "coat_rough_map_on",
    "coatingroughnessmap": "coat_rough_map_on",
    "bump": "bump_map_on",
    "bumpmap": "bump_map_on",
    "coatingbump": "coat_bump_map_on",
    "coatingbumpmap": "coat_bump_map_on",
    "cutout": "cutout_map_on",
    "cutoutmap": "cutout_map_on",
    "displacement": "displacement_map_on",
    "displacementmap": "displacement_map_on",
}


def canonical_name(value: str) -> str:
    return _NON_ALNUM.sub("", str(value).casefold())


def find_texture_link(node: GraphNode, *slot_names: str) -> Optional[GraphLink]:
    wanted = {canonical_name(name) for name in slot_names}
    for link in node.sub_textures:
        if canonical_name(link.slot) in wanted:
            return link
    return None


def map_control_key(slot: str) -> Optional[str]:
    return _MAP_CONTROL_NAMES.get(canonical_name(slot))


def map_is_enabled(parameters: Mapping[str, Any], slot: str) -> bool:
    key = map_control_key(slot)
    if key is None:
        return True
    return bool(parameters.get("texmap_{0}_on".format(key), True))


def map_amount(parameters: Mapping[str, Any], slot: str) -> float:
    key = map_control_key(slot)
    if key is None:
        return 1.0
    value = parameters.get("texmap_{0}_multiplier".format(key), 100.0)
    try:
        amount = float(value) / 100.0
    except (TypeError, ValueError):
        amount = 1.0
    return max(0.0, min(1.0, amount))


def physical_map_is_enabled(parameters: Mapping[str, Any], slot: str) -> bool:
    """Return the Physical Material checkbox state for an exported map slot."""

    key = _PHYSICAL_MAP_CONTROL_NAMES.get(canonical_name(slot))
    if key is None:
        return True
    return bool(parameters.get(key, True))


def scalar(parameters: Mapping[str, Any], name: str, default: float) -> float:
    value = parameters.get(name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def rgba(value: Any, default=(0.8, 0.8, 0.8, 1.0)) -> Tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return tuple(float(item) for item in default)  # type: ignore[return-value]
    alpha = value[3] if len(value) > 3 else 1.0
    try:
        return (
            clamp01(float(value[0])),
            clamp01(float(value[1])),
            clamp01(float(value[2])),
            clamp01(float(alpha)),
        )
    except (TypeError, ValueError):
        return tuple(float(item) for item in default)  # type: ignore[return-value]


def luminance(color: Tuple[float, float, float, float]) -> float:
    return clamp01(0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2])


def vray_roughness(parameters: Mapping[str, Any]) -> float:
    value = clamp01(scalar(parameters, "reflection_glossiness", 1.0))
    if bool(parameters.get("brdf_useRoughness", False)):
        return value
    return 1.0 - value


def physical_roughness(
    parameters: Mapping[str, Any],
    value_name: str = "roughness",
    invert_name: Optional[str] = None,
) -> float:
    """Resolve a 3ds Max Physical Material roughness/invert pair."""

    value = clamp01(scalar(parameters, value_name, 0.0))
    invert_key = invert_name or "{0}_inv".format(value_name)
    return 1.0 - value if bool(parameters.get(invert_key, False)) else value


def sorted_sub_materials(node: GraphNode) -> Tuple[GraphLink, ...]:
    return tuple(sorted(node.sub_materials, key=lambda item: (item.index, item.slot)))
