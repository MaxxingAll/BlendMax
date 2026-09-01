"""Renderer-independent helpers for interpreting the Max material graph."""

from __future__ import annotations

import re
from collections.abc import Mapping as MappingABC
from typing import Any, Dict, Mapping, Optional, Set, Tuple

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
    """Normalize for slot/class matching: lowercase and strip punctuation.

    Used where MaxScript slot and class names legitimately vary in spacing
    and punctuation (e.g. "Reflection roughness" vs "ReflectionGlossiness").
    Material *parameter* lookups use parameter_key() instead, which preserves
    punctuation so distinct property names cannot silently collapse.
    """
    return _NON_ALNUM.sub("", str(value).casefold())


def parameter_key(value: str) -> str:
    """Normalize a material parameter name for lookup: casefold, keep spelling.

    Unlike canonical_name(), this preserves underscores and punctuation so a
    lookup must match the exact property spelling apart from case. Known
    cross-release spellings belong in _PARAMETER_ALIASES rather than in
    implicit punctuation stripping.
    """
    return str(value).strip().casefold()


_PARAMETER_ALIASES: Dict[str, str] = {}
"""Explicit material-parameter aliases for the Blender importer.

Maps a normalized (casefolded) alias key to the normalized canonical key.
Parameter lookups fall back to this table only after a direct
case-insensitive match fails. Populate it as cross-release V-Ray/Max
property spellings are discovered; nothing is treated as equivalent beyond
its exact casefolded spelling unless it is listed here.
"""


class ParameterView(MappingABC):
    """Case-insensitive, access-recording view over a node's parameters.

    Lookups are keyed on parameter_key() (casefolded, punctuation preserved)
    so a lookup must match the exact property spelling apart from case. Known
    cross-release spellings can be registered in the alias table. The view
    records which keys were read so a converter can report manifest
    parameters that nothing consumed instead of letting them silently fall
    back to defaults.
    """

    def __init__(
        self,
        parameters: Mapping[str, Any],
        aliases: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._by_key: Dict[str, Any] = {}
        self._original_keys: Dict[str, str] = {}
        for key, value in parameters.items():
            normalized = parameter_key(key)
            self._by_key.setdefault(normalized, value)
            self._original_keys.setdefault(normalized, str(key))
        self._aliases = aliases if aliases is not None else _PARAMETER_ALIASES
        self.accessed: Set[str] = set()

    def _resolve(self, key: str) -> Optional[str]:
        normalized = parameter_key(key)
        if normalized in self._by_key:
            return normalized
        target = self._aliases.get(normalized)
        if target is not None and target in self._by_key:
            return target
        return None

    def __getitem__(self, key: str) -> Any:
        resolved = self._resolve(key)
        if resolved is None:
            raise KeyError(key)
        self.accessed.add(resolved)
        return self._by_key[resolved]

    def __iter__(self):
        return iter(self._by_key)

    def __len__(self) -> int:
        return len(self._by_key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._resolve(key) is not None

    def get(self, key: str, default: Any = None) -> Any:
        resolved = self._resolve(key)
        if resolved is None:
            return default
        self.accessed.add(resolved)
        return self._by_key[resolved]

    def original_key(self, key: str) -> str:
        """The first manifest key (original casing) for a normalized name."""
        return self._original_keys.get(parameter_key(key), key)

    def unmapped_keys(self) -> Tuple[str, ...]:
        """Normalized keys present in the manifest but never read."""
        return tuple(sorted(self._by_key.keys() - self.accessed))


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


def vray_anisotropy(parameters: Mapping[str, Any]) -> Tuple[float, float]:
    """Return (magnitude, rotation) for Blender's Principled BSDF.

    V-Ray stores anisotropy as -1..1 where the sign flips the elongation
    axis, and anisotropy_rotation as 0..1 for one full turn. Blender's
    Anisotropic input is a 0..1 magnitude and its Anisotropic Rotation is
    also 0..1 for a full turn, so the magnitude is the absolute value and a
    negative V-Ray value adds a quarter turn (perpendicular).
    """
    value = scalar(parameters, "anisotropy", 0.0)
    magnitude = clamp01(abs(value))
    rotation = clamp01(scalar(parameters, "anisotropy_rotation", 0.0))
    if value < 0.0:
        rotation = (rotation + 0.25) % 1.0
    return magnitude, rotation


def vray_sheen_roughness(parameters: Mapping[str, Any]) -> float:
    """Sheen glossiness (1 = sharpest) inverted to Blender sheen roughness."""
    return clamp01(1.0 - scalar(parameters, "sheen_glossiness", 0.8))


def vray_thin_film(parameters: Mapping[str, Any]) -> Tuple[float, float]:
    """Return (ior, thickness_nm) for Blender's Principled thin film.

    Supported when no thickness-blend map exists. V-Ray's thickness is a
    min/max range, but the maximum is only used when a thickness-blend
    texture is connected; BlendMax does not interpret that map yet, so only
    the minimum reaches Blender (matching V-Ray's own no-blend-map behavior).
    Blender treats thickness 0 as disabled, so a disabled V-Ray thin film
    maps to 0.
    """
    enabled = bool(parameters.get("thinfilm_on", False))
    ior = max(1.0, scalar(parameters, "thinfilm_ior", 1.5))
    minimum = max(0.0, scalar(parameters, "thinfilm_thickness_min", 0.0))
    # thickness_max is intentionally NOT used: it only applies with a
    # thickness-blend map, which is not interpreted yet. Reading it here
    # merely keeps it out of the unmapped-parameter diagnostics; its value
    # remains available in the stored manifest.
    _ = parameters.get("thinfilm_thickness_max")
    return ior, minimum if enabled else 0.0


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
