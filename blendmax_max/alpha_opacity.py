"""Non-destructive alpha/opacity material detection for cleanup protection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class AlphaOpacityFinding:
    geometry_id: str
    geometry_name: str
    material_name: str
    material: Any


@dataclass(frozen=True)
class AlphaOpacityDecision:
    action: str
    protected_geometry_ids: Tuple[str, ...]
    protected_material_ids: Tuple[str, ...]
    findings: Tuple[AlphaOpacityFinding, ...]


_ALPHA_PROPERTY_NAMES = {
    "opacity",
    "opacitymap",
    "opacitymapenable",
    "texmap_opacity",
    "texmap_opacity_on",
}


def _safe_class_name(adapter, value: Any) -> str:
    try:
        return str(adapter._class_name(value))
    except Exception:
        return type(value).__name__


def _safe_anim_id(adapter, value: Any) -> str:
    try:
        return adapter._anim_id(value)
    except Exception:
        return "python-{0}".format(id(value))


def _is_undefined(adapter, value: Any) -> bool:
    try:
        return bool(adapter._is_undefined(value))
    except Exception:
        return value is None


def _get_property(adapter, value: Any, name: str) -> Tuple[bool, Any]:
    try:
        return True, adapter.rt.getProperty(value, name)
    except Exception:
        try:
            return True, getattr(value, name)
        except Exception:
            return False, None


def _property_names(adapter, value: Any) -> Set[str]:
    names: Set[str] = set()
    try:
        for name in adapter.rt.getPropNames(value):
            names.add(str(name).casefold())
    except Exception:
        pass
    return names


def _numeric_opacity_hits(adapter, material: Any, names: Set[str]) -> bool:
    for property_name in ("opacity", "opacityMultiplier"):
        if property_name.casefold() not in names:
            continue
        ok, value = _get_property(adapter, material, property_name)
        if not ok:
            continue
        try:
            return float(value) < 100.0
        except Exception:
            continue
    return False


def _enabled_opacity_map_hit(adapter, material: Any, names: Set[str]) -> bool:
    pairs = (
        ("opacitymap", "opacitymapenable"),
        ("texmap_opacity", "texmap_opacity_on"),
    )
    for map_name, enable_name in pairs:
        if map_name not in names:
            continue
        ok_map, map_value = _get_property(adapter, material, map_name)
        if not ok_map or _is_undefined(adapter, map_value) or map_value is None:
            continue
        ok_enable, enabled = _get_property(adapter, material, enable_name)
        if not ok_enable:
            # A populated explicit opacity slot with no readable enable state is
            # treated conservatively because cleanup must not silently alter it.
            return True
        try:
            if bool(enabled):
                return True
        except Exception:
            return True
    return False


def _texture_slot_hit(adapter, value: Any) -> bool:
    """Detect nested opacity/alpha texture slots without relying on names of materials."""
    try:
        count = int(adapter.rt.getNumSubTexmaps(value))
    except Exception:
        return False
    for index in range(1, count + 1):
        try:
            child = adapter.rt.getSubTexmap(value, index)
        except Exception:
            continue
        try:
            slot = str(adapter.rt.getSubTexmapSlotName(value, index)).casefold()
        except Exception:
            slot = ""
        if child is not None and not _is_undefined(adapter, child) and (
            "opacity" in slot or "alpha" in slot
        ):
            return True
    return False


def material_uses_alpha_opacity(adapter, material: Any, seen: Optional[Set[str]] = None, depth: int = 0) -> bool:
    """Return True when a material graph contains appearance-affecting alpha/opacity state."""
    if _is_undefined(adapter, material) or material is None or depth > 32:
        return False
    seen = set() if seen is None else seen
    anim_id = _safe_anim_id(adapter, material)
    if anim_id in seen:
        return False
    seen.add(anim_id)

    names = _property_names(adapter, material)
    class_name = _safe_class_name(adapter, material).casefold()

    if "vraymtl" in class_name:
        if _enabled_opacity_map_hit(adapter, material, names):
            return True
    else:
        if _enabled_opacity_map_hit(adapter, material, names):
            return True
        if _numeric_opacity_hits(adapter, material, names):
            return True

    if _texture_slot_hit(adapter, material):
        return True

    try:
        sub_count = int(adapter.rt.getNumSubMtls(material))
    except Exception:
        sub_count = 0
    for index in range(1, sub_count + 1):
        try:
            child = adapter.rt.getSubMtl(material, index)
        except Exception:
            continue
        if material_uses_alpha_opacity(adapter, child, seen=seen, depth=depth + 1):
            return True

    try:
        texture_count = int(adapter.rt.getNumSubTexmaps(material))
    except Exception:
        texture_count = 0
    for index in range(1, texture_count + 1):
        try:
            child = adapter.rt.getSubTexmap(material, index)
        except Exception:
            continue
        if material_uses_alpha_opacity(adapter, child, seen=seen, depth=depth + 1):
            return True

    return False


def find_alpha_opacity_geometry(adapter, geometry_ids: Iterable[str]) -> Tuple[AlphaOpacityFinding, ...]:
    findings: List[AlphaOpacityFinding] = []
    seen_geometry: Set[str] = set()
    for geometry_id in geometry_ids:
        if geometry_id in seen_geometry:
            continue
        seen_geometry.add(geometry_id)
        node = adapter._nodes_by_id.get(geometry_id)
        if node is None:
            continue
        material = getattr(node, "material", None)
        if _is_undefined(adapter, material) or material is None:
            continue
        if material_uses_alpha_opacity(adapter, material):
            findings.append(
                AlphaOpacityFinding(
                    geometry_id=geometry_id,
                    geometry_name=str(getattr(node, "name", geometry_id)),
                    material_name=str(getattr(material, "name", "Material")),
                    material=material,
                )
            )
    return tuple(findings)


def confirm_alpha_opacity(adapter, findings: Sequence[AlphaOpacityFinding]) -> AlphaOpacityDecision:
    if not findings:
        return AlphaOpacityDecision("NONE", (), (), ())

    geometry_names = []
    seen_geometry = set()
    material_names = []
    seen_materials = set()
    protected_material_ids = set()
    for finding in findings:
        if finding.geometry_name not in seen_geometry:
            geometry_names.append(finding.geometry_name)
            seen_geometry.add(finding.geometry_name)
        material_id = _safe_anim_id(adapter, finding.material)
        protected_material_ids.add(material_id)
        if finding.material_name not in seen_materials:
            material_names.append(finding.material_name)
            seen_materials.add(finding.material_name)

    message = (
        "BlendMax found materials using alpha/opacity maps or settings.\n\n"
        "These materials can control which parts of a mesh are visible, such as "
        "leaves and other cutout surfaces. Joining or simplifying these objects "
        "may alter their appearance.\n\n"
        "Affected geometry:\n  • {geometry}\n\n"
        "Affected materials:\n  • {materials}\n\n"
        "Choose Skip Materials to keep the entire affected geometry separate."
        .format(
            geometry="\n  • ".join(geometry_names),
            materials="\n  • ".join(material_names),
        )
    )
    try:
        skip = bool(
            adapter.rt.queryBox(
                message,
                title="BlendMax: Alpha / Opacity Materials Detected",
            )
        )
    except Exception:
        return AlphaOpacityDecision("CANCEL", (), (), tuple(findings))

    if skip:
        return AlphaOpacityDecision(
            "SKIP",
            tuple(f.geometry_id for f in findings),
            tuple(sorted(protected_material_ids)),
            tuple(findings),
        )

    merge_message = (
        "Merge the detected alpha/opacity materials anyway?\n\n"
        "Choosing Yes allows these objects to enter the existing cleanup path "
        "and their appearance may change. Choosing No cancels the export."
    )
    try:
        merge = bool(
            adapter.rt.queryBox(
                merge_message,
                title="BlendMax: Merge Alpha / Opacity Materials?",
            )
        )
    except Exception:
        merge = False

    if merge:
        return AlphaOpacityDecision("MERGE", (), (), tuple(findings))
    return AlphaOpacityDecision("CANCEL", (), (), tuple(findings))
