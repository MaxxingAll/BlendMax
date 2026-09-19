"""Material graph capture and texture discovery for the Max adapter.

Split out of ``max_adapter``: this module owns the conversion-relevant
property whitelist and map-slot aliases, and imports neither the adapter
facade nor the scene or export modules.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


VRAY_MTL_PROPERTIES = {
    "anisotropy",
    "anisotropy_axis",
    "anisotropy_channel",
    "anisotropy_derivation",
    "anisotropy_rotation",
    "brdf_type",
    "brdf_useroughness",
    "coat_amount",
    "coat_color",
    "coat_darkening",
    "coat_glossiness",
    "coat_ior",
    "diffuse",
    "diffuse_roughness",
    "option_cutoff",
    "option_doublesided",
    "option_glossyfresnel",
    "option_opacitymode",
    "option_openpbrmode",
    "option_tracediffuse",
    "option_tracereflection",
    "option_tracerefraction",
    "reflection",
    "reflection_affectalpha",
    "reflection_dimdistance",
    "reflection_dimdistance_falloff",
    "reflection_dimdistance_on",
    "reflection_fresnel",
    "reflection_glossiness",
    "reflection_ior",
    "reflection_lockior",
    "reflection_maxdepth",
    "reflection_metalness",
    "reflection_weight",
    "refraction",
    "refraction_affectalpha",
    "refraction_affectshadows",
    "refraction_dispersion",
    "refraction_dispersion_on",
    "refraction_fogbias",
    "refraction_fogcolor",
    "refraction_fogdepth",
    "refraction_fogmult",
    "refraction_fogunitsscale_on",
    "refraction_glossiness",
    "refraction_ior",
    "refraction_maxdepth",
    "refraction_thinwalled",
    "selfillumination",
    "selfillumination_gi",
    "selfillumination_multiplier",
    "sheen_color",
    "sheen_glossiness",
    "thinfilm_ior",
    "thinfilm_on",
    "thinfilm_thickness_max",
    "thinfilm_thickness_min",
    "translucency_amount",
    "translucency_color",
    "translucency_fbcoeff",
    "translucency_multiplier",
    "translucency_on",
    "translucency_scattercoeff",
    "translucency_surfacelighting",
    "translucency_thickness",
}


VRAY_MAP_SLOT_ALIASES = {
    # V-Ray 7 can display this slot as Reflection Roughness while retaining
    # the older reflectionGlossiness property stem for its map controls.
    "reflectionroughness": "reflectionglossiness",
}


def _primitive_value(adapter, value) -> Tuple[bool, Any]:
    if value is None:
        return True, None
    if isinstance(value, (bool, int, float, str)):
        return True, value

    class_name = adapter._class_name(value).casefold()
    if class_name in {"name", "string", "filename"}:
        return True, str(value)
    if "color" in class_name:
        components = []
        for component in ("r", "g", "b", "a"):
            if hasattr(value, component):
                components.append(float(getattr(value, component)))
        if len(components) >= 3:
            if max(abs(component) for component in components) > 1.0:
                components = [component / 255.0 for component in components]
            return True, components
    if class_name in {"point2", "point3", "point4"}:
        components = []
        for component in ("x", "y", "z", "w"):
            if hasattr(value, component):
                components.append(float(getattr(value, component)))
        if components:
            return True, components
    return False, None


def _primitive_properties(adapter, animatable) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    try:
        names = list(adapter.rt.getPropNames(animatable))
    except Exception:
        return properties

    for property_name in names:
        key = str(property_name)
        if key.casefold() in {"name"}:
            continue
        try:
            value = adapter.rt.getProperty(animatable, property_name)
            supported, encoded = _primitive_value(adapter, value)
            if supported:
                properties[key] = encoded
        except Exception:
            continue
    return properties


def _filter_material_properties(
    adapter,
    class_name: str,
    properties: Dict[str, Any],
) -> Dict[str, Any]:
    if class_name.casefold() != "vraymtl":
        return properties
    return {
        key: value
        for key, value in properties.items()
        if key.casefold() in VRAY_MTL_PROPERTIES
    }


def _connected_map_controls(
    adapter,
    class_name: str,
    properties: Dict[str, Any],
    slot_names: Iterable[str],
) -> Dict[str, Any]:
    if class_name.casefold() != "vraymtl":
        return {}

    normalized_slots = set()
    for slot in slot_names:
        normalized = re.sub(r"[^a-z0-9]", "", str(slot).casefold())
        normalized_slots.add(VRAY_MAP_SLOT_ALIASES.get(normalized, normalized))
    controls = {}
    for key, value in properties.items():
        lowered = key.casefold()
        if not lowered.startswith("texmap_"):
            continue
        stem = lowered[len("texmap_") :]
        for suffix in ("_multiplier", "_on"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        normalized_stem = re.sub(r"[^a-z0-9]", "", stem)
        normalized_stem = VRAY_MAP_SLOT_ALIASES.get(
            normalized_stem,
            normalized_stem,
        )
        if normalized_stem in normalized_slots:
            controls[key] = value
    return controls


def capture_material_graph(
    adapter,
    payload_ids: Iterable[str],
) -> Dict[str, Any]:
    graph: Dict[str, Dict[str, Any]] = {}

    def visit(animatable, kind: str) -> Optional[str]:
        if animatable is None:
            return None
        try:
            if animatable == adapter.rt.undefined:
                return None
        except Exception:
            pass

        reference = "{0}_{1}".format(kind[:3], adapter._anim_id(animatable))
        if reference in graph:
            return reference

        class_name = adapter._class_name(animatable)
        all_properties = _primitive_properties(adapter, animatable)
        entry: Dict[str, Any] = {
            "id": reference,
            "kind": kind,
            "name": str(getattr(animatable, "name", reference)),
            "class": class_name,
            "parameters": _filter_material_properties(
                adapter,
                class_name,
                all_properties,
            ),
            "sub_materials": [],
            "sub_textures": [],
        }
        graph[reference] = entry

        try:
            sub_material_count = int(adapter.rt.getNumSubMtls(animatable))
        except Exception:
            sub_material_count = 0
        for index in range(1, sub_material_count + 1):
            try:
                child = adapter.rt.getSubMtl(animatable, index)
                child_ref = visit(child, "material")
                try:
                    slot = str(adapter.rt.getSubMtlSlotName(animatable, index))
                except Exception:
                    slot = str(index)
                if child_ref:
                    entry["sub_materials"].append(
                        {"index": index, "slot": slot, "ref": child_ref}
                    )
            except Exception:
                continue

        try:
            sub_texture_count = int(adapter.rt.getNumSubTexmaps(animatable))
        except Exception:
            sub_texture_count = 0
        connected_slot_names = []
        for index in range(1, sub_texture_count + 1):
            try:
                child = adapter.rt.getSubTexmap(animatable, index)
                child_ref = visit(child, "texture")
                try:
                    slot = str(adapter.rt.getSubTexmapSlotName(animatable, index))
                except Exception:
                    slot = str(index)
                if child_ref:
                    connected_slot_names.append(slot)
                    entry["sub_textures"].append(
                        {"index": index, "slot": slot, "ref": child_ref}
                    )
            except Exception:
                continue
        entry["parameters"].update(
            _connected_map_controls(
                adapter,
                class_name,
                all_properties,
                connected_slot_names,
            )
        )
        entry["parameter_count"] = len(entry["parameters"])
        return reference

    assignments = []
    for node_id in payload_ids:
        node = adapter._nodes_by_id[node_id]
        material = getattr(node, "material", None)
        material_ref = visit(material, "material")
        assignments.append(
            {"object_id": node_id, "material_ref": material_ref}
        )

    return {
        "serialization": "conversion_relevant_property_snapshot",
        "color_encoding": "rgba_0_1",
        "assignments": assignments,
        "graph": list(graph.values()),
    }


def discover_texture_references(
    adapter,
    material_data: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Return only graph-reachable bitmap references with stable owners."""

    candidates: List[Dict[str, str]] = []
    likely_path_tokens = ("filename", "file", "path", "mapname", "bitmap")
    for entry in material_data.get("graph", []):
        if entry.get("kind") != "texture":
            continue
        for key, value in entry.get("parameters", {}).items():
            if not isinstance(value, str):
                continue
            if any(token in key.casefold() for token in likely_path_tokens):
                raw_path = value.strip()
                resolved_path = _resolve_texture_path(adapter, raw_path)
                if resolved_path:
                    candidates.append(
                        {
                            "graph_node_id": str(entry.get("id", "")),
                            "parameter": str(key),
                            "raw_path": raw_path,
                            "resolved_path": resolved_path,
                        }
                    )

    unique: List[Dict[str, str]] = []
    seen = set()
    for reference in candidates:
        key = (
            reference["graph_node_id"],
            reference["parameter"].casefold(),
            reference["resolved_path"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(reference)
    return unique


def _resolve_texture_path(adapter, value: str) -> str:
    raw = os.path.expandvars(str(value)).strip()
    if not raw or raw.casefold() in {"none", "undefined"}:
        return ""
    if os.path.isabs(raw) and os.path.isfile(raw):
        return os.path.normpath(raw)

    scene_directory = str(getattr(adapter.rt, "maxFilePath", ""))
    if scene_directory:
        scene_candidate = os.path.join(scene_directory, raw)
        if os.path.isfile(scene_candidate):
            return os.path.normpath(scene_candidate)

    try:
        resolved = str(adapter.rt.pathConfig.resolvePath(raw))
        if resolved and os.path.isfile(resolved):
            return os.path.normpath(resolved)
    except Exception:
        pass
    return os.path.normpath(raw)
