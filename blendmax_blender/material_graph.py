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


def sorted_sub_materials(node: GraphNode) -> Tuple[GraphLink, ...]:
    return tuple(sorted(node.sub_materials, key=lambda item: (item.index, item.slot)))
