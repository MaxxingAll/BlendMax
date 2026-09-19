"""Scene snapshot, version metadata and geometry bounds for the Max adapter.

Split out of ``max_adapter``: this module imports neither the adapter facade
nor the material or export modules.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import (
    SUPPORTED_VRAY_MAX_RELEASE,
    SUPPORTED_VRAY_MIN_RELEASE,
    SUPPORTED_VRAY_RANGE,
    TARGET_MAX_VERSION,
)
from .errors import ExportError
from .models import SceneNode


def snapshot_scene(adapter) -> List[SceneNode]:
    max_nodes = list(adapter.rt.objects)
    adapter._nodes_by_id = {
        adapter._anim_id(node): node
        for node in max_nodes
    }
    snapshots: List[SceneNode] = []
    for node_id, node in adapter._nodes_by_id.items():
        parent = getattr(node, "parent", None)
        parent_id = None
        if parent is not None:
            try:
                if parent != adapter.rt.undefined:
                    parent_id = adapter._anim_id(parent)
            except Exception:
                parent_id = adapter._anim_id(parent)

        try:
            is_group_head = bool(adapter.rt.isGroupHead(node))
        except Exception:
            is_group_head = False
        try:
            is_group_member = bool(adapter.rt.isGroupMember(node))
        except Exception:
            is_group_member = False

        superclass = adapter._superclass_name(node)
        hidden_or_frozen = adapter._is_hidden_or_frozen(node)
        snapshots.append(
            SceneNode(
                node_id=node_id,
                name=str(getattr(node, "name", "Unnamed")),
                node_type=adapter._class_name(node),
                superclass=superclass,
                parent_id=parent_id,
                is_group_head=is_group_head,
                is_group_member=is_group_member,
                exportable=(
                    adapter._is_exportable_superclass(superclass)
                    and not hidden_or_frozen
                ),
                hidden_or_frozen=hidden_or_frozen,
            )
        )
    return snapshots


def source_metadata(adapter) -> Dict[str, Any]:
    try:
        version = [str(value) for value in list(adapter.rt.maxVersion())]
    except Exception:
        version = []
    try:
        display_units = str(adapter.rt.units.DisplayType)
    except Exception:
        display_units = "Unknown"
    try:
        units_per_meter = float(adapter.rt.units.decodeValue("1m"))
    except Exception:
        units_per_meter = 1.0

    scene_name = str(getattr(adapter.rt, "maxFileName", "")) or "Untitled.max"
    detected_max_version = _parse_max_version(adapter, version)
    renderer_class = None
    try:
        renderer_class = adapter._class_name(adapter.rt.renderers.current)
    except Exception:
        pass

    try:
        getattr(adapter.rt, "VRayMtl")
        vray_installed = True
    except Exception:
        vray_installed = False

    detected_vray_version = None
    try:
        value = adapter.rt.vrayVersion()
        if value is not None:
            detected_vray_version = str(value)
    except Exception:
        pass

    max_matches_target = detected_max_version == TARGET_MAX_VERSION
    parsed_vray_version = _parse_vray_version(adapter, detected_vray_version)
    vray_release = (
        parsed_vray_version[:2]
        if parsed_vray_version is not None
        else None
    )
    vray_matches_target = bool(
        vray_release
        and SUPPORTED_VRAY_MIN_RELEASE
        <= vray_release
        <= SUPPORTED_VRAY_MAX_RELEASE
    )
    compatibility_warnings = []
    if not max_matches_target:
        compatibility_warnings.append(
            "Untested 3ds Max version detected: {0}; target is {1}.".format(
                detected_max_version or "Unknown", TARGET_MAX_VERSION
            )
        )
    if not vray_installed:
        compatibility_warnings.append(
            "V-Ray was not detected; supported range is {0}.".format(
                SUPPORTED_VRAY_RANGE
            )
        )
    elif detected_vray_version and not vray_matches_target:
        compatibility_warnings.append(
            "Untested V-Ray version detected: {0}; supported range is {1}.".format(
                detected_vray_version, SUPPORTED_VRAY_RANGE
            )
        )

    return {
        "application": "Autodesk 3ds Max",
        "max_version_raw": version,
        "max_version": detected_max_version,
        "scene_file": Path(scene_name).name,
        "display_units": display_units,
        "system_units_per_meter": units_per_meter,
        "renderer": {
            "current_class": renderer_class,
        },
        "vray": {
            "installed": vray_installed,
            "version": detected_vray_version,
            "parsed_version": (
                ".".join(
                    [
                        str(parsed_vray_version[0]),
                        "{0:02d}".format(parsed_vray_version[1]),
                        "{0:02d}".format(parsed_vray_version[2]),
                    ]
                )
                if parsed_vray_version is not None
                else None
            ),
        },
        "compatibility": {
            "target_3ds_max": TARGET_MAX_VERSION,
            "supported_vray_range": SUPPORTED_VRAY_RANGE,
            "max_matches_target": max_matches_target,
            "vray_matches_target": vray_matches_target,
            "warnings": compatibility_warnings,
        },
    }


def _parse_vray_version(
    adapter,
    raw_version: Optional[str],
) -> Optional[Tuple[int, int, int]]:
    if not raw_version:
        return None
    match = re.search(
        r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)",
        str(raw_version),
    )
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _parse_max_version(adapter, raw_version: Iterable[str]) -> Optional[str]:
    values = [str(value) for value in raw_version]
    for index, value in enumerate(values):
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if not 2000 <= year <= 2100:
            continue
        update = ""
        if index + 1 < len(values):
            candidate = values[index + 1].strip()
            # The host may return the update component with harmless trailing
            # TEXT (".3 Update" rather than ".3"), so the numeric token is
            # matched at the start of the value and trailing text ignored.
            #
            # Trailing version NUMBERS are NOT ignored: a dotted suffix like
            # ".3.1" is a real version component, not decoration. Matching it
            # as ".3" would report a newer-than-target build as the target
            # and suppress the compatibility warning that should fire. The
            # lookahead makes such values fall back to year-only instead.
            #
            # A leading-junk value such as "x.3" does not match either.
            match = re.match(r"\.\d+(?![\d.])", candidate)
            if match:
                update = match.group(0)
        return "{0}{1}".format(year, update)
    return None


def bounds_in_meters(
    adapter,
    payload_ids: Iterable[str],
) -> Dict[str, List[float]]:
    minimum = [float("inf"), float("inf"), float("inf")]
    maximum = [float("-inf"), float("-inf"), float("-inf")]
    found = False

    for node_id in payload_ids:
        node = adapter._nodes_by_id[node_id]
        try:
            values_min, values_max = _evaluated_mesh_bounds(adapter, node)
        except Exception as evaluated_exc:
            try:
                values_min, values_max = _node_bounds(node)
            except Exception as node_exc:
                raise ExportError(
                    "Could not calculate the bounding box for {0}: "
                    "evaluated mesh failed ({1}); node bounds failed ({2})".format(
                        getattr(node, "name", node_id),
                        evaluated_exc,
                        node_exc,
                    )
                )
        for index in range(3):
            minimum[index] = min(minimum[index], values_min[index])
            maximum[index] = max(maximum[index], values_max[index])
        found = True

    if not found:
        raise ExportError("No geometry was available for bounds calculation.")

    try:
        units_per_meter = float(adapter.rt.units.decodeValue("1m"))
        if units_per_meter <= 0.0:
            units_per_meter = 1.0
    except Exception:
        units_per_meter = 1.0

    minimum_m = [value / units_per_meter for value in minimum]
    maximum_m = [value / units_per_meter for value in maximum]
    dimensions_m = [
        maximum_m[index] - minimum_m[index]
        for index in range(3)
    ]
    return {
        "minimum": minimum_m,
        "maximum": maximum_m,
        "dimensions": dimensions_m,
    }


def _node_bounds(node) -> Tuple[List[float], List[float]]:
    node_min = node.min
    node_max = node.max
    return (
        [float(node_min.x), float(node_min.y), float(node_min.z)],
        [float(node_max.x), float(node_max.y), float(node_max.z)],
    )


def _evaluated_mesh_bounds(
    adapter,
    node,
) -> Tuple[List[float], List[float]]:
    mesh = None
    try:
        # snapshotAsMesh evaluates the modifier stack and returns world-space
        # vertices, avoiding the conservative node.min/node.max box produced
        # by rotated geometry.
        mesh = adapter.rt.snapshotAsMesh(node)
        vertex_count = int(mesh.numverts)
        if vertex_count <= 0:
            raise ValueError("evaluated mesh has no vertices")

        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        for vertex_index in range(1, vertex_count + 1):
            vertex = adapter.rt.getVert(mesh, vertex_index)
            values = [float(vertex.x), float(vertex.y), float(vertex.z)]
            for axis in range(3):
                minimum[axis] = min(minimum[axis], values[axis])
                maximum[axis] = max(maximum[axis], values[axis])
        return minimum, maximum
    finally:
        if mesh is not None:
            try:
                adapter.rt.delete(mesh)
            except Exception:
                pass
