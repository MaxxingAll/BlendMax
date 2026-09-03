"""Non-destructive alpha/opacity material detection for cleanup protection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class AlphaOpacityFinding:
    geometry_id: str
    geometry_name: str
    material_name: str
    material: Any
    material_graph_ids: Tuple[str, ...]


@dataclass(frozen=True)
class AlphaOpacityDecision:
    action: str
    protected_geometry_ids: Tuple[str, ...]
    protected_material_ids: Tuple[str, ...]
    findings: Tuple[AlphaOpacityFinding, ...]


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


def _get_property(adapter, value: Any, name: str, property_names=None) -> Tuple[bool, Any]:
    """Resolve a Max property without losing the runtime property's original casing."""
    candidates = [name]
    if property_names:
        folded = name.casefold()
        candidates.extend(
            actual_name
            for actual_name in property_names
            if str(actual_name).casefold() == folded and str(actual_name) not in candidates
        )

    for candidate in candidates:
        try:
            return True, adapter.rt.getProperty(value, candidate)
        except Exception:
            pass
        try:
            return True, getattr(value, candidate)
        except Exception:
            pass
    return False, None


def _property_names(adapter, value: Any) -> Tuple[str, ...]:
    names: List[str] = []
    try:
        for name in adapter.rt.getPropNames(value):
            names.append(str(name))
    except Exception:
        pass
    return tuple(names)


def _numeric_opacity_hits(adapter, material: Any, names: Tuple[str, ...]) -> bool:
    folded_names = {name.casefold() for name in names}
    if "opacity" not in folded_names:
        return False
    ok, value = _get_property(adapter, material, "opacity", names)
    if not ok:
        return False
    try:
        return float(value) < 100.0
    except Exception:
        return False


def _enabled_opacity_map_hit(adapter, material: Any, names: Tuple[str, ...]) -> bool:
    folded_names = {name.casefold() for name in names}
    pairs = (
        ("opacitymap", "opacitymapenable"),
        ("texmap_opacity", "texmap_opacity_on"),
    )
    for map_name, enable_name in pairs:
        if map_name.casefold() not in folded_names:
            continue
        ok_map, map_value = _get_property(adapter, material, map_name, names)
        if not ok_map or _is_undefined(adapter, map_value) or map_value is None:
            continue
        ok_enable, enabled = _get_property(adapter, material, enable_name, names)
        if not ok_enable:
            # A populated opacity slot with an unreadable enable state is
            # treated conservatively to avoid silently changing appearance.
            return True
        try:
            if bool(enabled):
                return True
        except Exception:
            return True
    return False


def _walk_material_graph(adapter, material: Any, seen: Optional[Set[str]] = None, depth: int = 0):
    if _is_undefined(adapter, material) or material is None or depth > 32:
        return
    seen = set() if seen is None else seen
    anim_id = _safe_anim_id(adapter, material)
    if anim_id in seen:
        return
    seen.add(anim_id)
    yield material

    try:
        sub_count = int(adapter.rt.getNumSubMtls(material))
    except Exception:
        sub_count = 0
    for index in range(1, sub_count + 1):
        try:
            child = adapter.rt.getSubMtl(material, index)
        except Exception:
            continue
        yield from _walk_material_graph(adapter, child, seen=seen, depth=depth + 1)

    try:
        texture_count = int(adapter.rt.getNumSubTexmaps(material))
    except Exception:
        texture_count = 0
    for index in range(1, texture_count + 1):
        try:
            child = adapter.rt.getSubTexmap(material, index)
        except Exception:
            continue
        yield from _walk_material_graph(adapter, child, seen=seen, depth=depth + 1)


def material_uses_alpha_opacity(adapter, material: Any) -> bool:
    """Return True when a material graph contains appearance-affecting alpha/opacity state."""
    for graph_node in _walk_material_graph(adapter, material):
        names = _property_names(adapter, graph_node)
        if _enabled_opacity_map_hit(adapter, graph_node, names):
            return True
        if "vraymtl" not in _safe_class_name(adapter, graph_node).casefold():
            if _numeric_opacity_hits(adapter, graph_node, names):
                return True
    return False


def is_protected_material(adapter, material: Any, protected_material_ids: Set[str]) -> bool:
    """Return True when a candidate material belongs to a protected graph."""
    if not protected_material_ids:
        return False
    for graph_node in _walk_material_graph(adapter, material):
        if _safe_anim_id(adapter, graph_node) in protected_material_ids:
            return True
    return False


def find_alpha_opacity_geometry(adapter, geometry_ids: Iterable[str]) -> Tuple[AlphaOpacityFinding, ...]:
    findings: List[AlphaOpacityFinding] = []
    seen_geometry: Set[str] = set()
    nodes_by_id = getattr(adapter, "_nodes_by_id", {})
    for geometry_id in geometry_ids:
        if geometry_id in seen_geometry:
            continue
        seen_geometry.add(geometry_id)
        node = nodes_by_id.get(geometry_id)
        if node is None:
            continue
        material = getattr(node, "material", None)
        if _is_undefined(adapter, material) or material is None:
            continue
        if material_uses_alpha_opacity(adapter, material):
            graph_ids = tuple(
                _safe_anim_id(adapter, graph_node)
                for graph_node in _walk_material_graph(adapter, material)
            )
            findings.append(
                AlphaOpacityFinding(
                    geometry_id=geometry_id,
                    geometry_name=str(getattr(node, "name", geometry_id)),
                    material_name=str(getattr(material, "name", "Material")),
                    material=material,
                    material_graph_ids=graph_ids,
                )
            )
    return tuple(findings)


def confirm_alpha_opacity(adapter, findings: Tuple[AlphaOpacityFinding, ...]) -> AlphaOpacityDecision:
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
        protected_material_ids.update(finding.material_graph_ids)
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
        "Choose Yes to skip these materials and keep the affected geometry separate. "
        "Choose No to continue to a second prompt where you can explicitly merge "
        "anyway or cancel the export."
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
    except Exception as exc:
        try:
            adapter.notify(
                "The Alpha/Opacity protection prompt could not be displayed.\n\n"
                "Cleanup was canceled to avoid changing appearance.\n\n"
                "Reason: {0}".format(exc),
                "BlendMax: Cleanup Canceled",
            )
        except Exception:
            pass
        return AlphaOpacityDecision("CANCEL", (), (), findings)

    if skip:
        return AlphaOpacityDecision(
            "SKIP",
            tuple(f.geometry_id for f in findings),
            tuple(sorted(protected_material_ids)),
            findings,
        )

    merge_message = (
        "Merge the detected alpha/opacity materials anyway?\n\n"
        "Yes = Merge Anyway and allow the existing cleanup path.\n"
        "No = Cancel Export before destructive cleanup begins."
    )
    try:
        merge = bool(
            adapter.rt.queryBox(
                merge_message,
                title="BlendMax: Merge Alpha / Opacity Materials?",
            )
        )
    except Exception as exc:
        try:
            adapter.notify(
                "The Alpha/Opacity merge prompt could not be displayed.\n\n"
                "Cleanup was canceled to avoid changing appearance.\n\n"
                "Reason: {0}".format(exc),
                "BlendMax: Cleanup Canceled",
            )
        except Exception:
            pass
        return AlphaOpacityDecision("CANCEL", (), (), findings)

    if merge:
        return AlphaOpacityDecision("MERGE", (), (), findings)
    return AlphaOpacityDecision("CANCEL", (), (), findings)
