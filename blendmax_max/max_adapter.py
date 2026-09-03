"""All pymxs-dependent behavior lives in this module."""

from __future__ import annotations

import os
import re
import uuid
from contextlib import contextmanager
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


class MaxRuntimeAdapter:
    def __init__(self, runtime=None) -> None:
        if runtime is None:
            from pymxs import runtime as runtime  # type: ignore

        self.rt = runtime
        self._nodes_by_id: Dict[str, Any] = {}

    def _anim_id(self, value) -> str:
        try:
            handle = int(self.rt.getHandleByAnim(value))
            if handle:
                return str(handle)
        except Exception:
            pass
        return "python-{0}".format(id(value))

    def _class_name(self, value) -> str:
        try:
            return str(self.rt.classOf(value))
        except Exception:
            return type(value).__name__

    def _superclass_name(self, value) -> str:
        try:
            return str(self.rt.superClassOf(value))
        except Exception:
            return "Unknown"

    def get_node_by_id(self, node_id: str) -> Any:
        """Return a snapshot node by stable animation id."""
        return self._nodes_by_id.get(node_id)

    def get_anim_id(self, value: Any) -> str:
        """Public identity accessor for cleanup helpers."""
        return self._anim_id(value)

    def get_class_name(self, value: Any) -> str:
        """Public material/object class-name accessor for cleanup helpers."""
        return self._class_name(value)

    def is_undefined(self, value: Any) -> bool:
        """Public Max undefined-value check for cleanup helpers."""
        try:
            return value is None or value == self.rt.undefined
        except Exception:
            return value is None

    def _is_exportable_superclass(self, superclass: str) -> bool:
        lowered = superclass.casefold()
        return "geometryclass" in lowered

    def _is_hidden_or_frozen(self, node) -> bool:
        for property_name in ("isHiddenInVpt", "isFrozen"):
            try:
                if bool(getattr(node, property_name)):
                    return True
            except Exception:
                continue
        return False

    def snapshot_scene(self) -> List[SceneNode]:
        max_nodes = list(self.rt.objects)
        self._nodes_by_id = {
            self._anim_id(node): node
            for node in max_nodes
        }
        snapshots: List[SceneNode] = []
        for node_id, node in self._nodes_by_id.items():
            parent = getattr(node, "parent", None)
            parent_id = None
            if parent is not None:
                try:
                    if parent != self.rt.undefined:
                        parent_id = self._anim_id(parent)
                except Exception:
                    parent_id = self._anim_id(parent)

            try:
                is_group_head = bool(self.rt.isGroupHead(node))
            except Exception:
                is_group_head = False
            try:
                is_group_member = bool(self.rt.isGroupMember(node))
            except Exception:
                is_group_member = False

            superclass = self._superclass_name(node)
            hidden_or_frozen = self._is_hidden_or_frozen(node)
            snapshots.append(
                SceneNode(
                    node_id=node_id,
                    name=str(getattr(node, "name", "Unnamed")),
                    node_type=self._class_name(node),
                    superclass=superclass,
                    parent_id=parent_id,
                    is_group_head=is_group_head,
                    is_group_member=is_group_member,
                    exportable=(
                        self._is_exportable_superclass(superclass)
                        and not hidden_or_frozen
                    ),
                    hidden_or_frozen=hidden_or_frozen,
                )
            )
        return snapshots

    def source_metadata(self) -> Dict[str, Any]:
        try:
            version = [str(value) for value in list(self.rt.maxVersion())]
        except Exception:
            version = []
        try:
            display_units = str(self.rt.units.DisplayType)
        except Exception:
            display_units = "Unknown"
        try:
            units_per_meter = float(self.rt.units.decodeValue("1m"))
        except Exception:
            units_per_meter = 1.0

        scene_name = str(getattr(self.rt, "maxFileName", "")) or "Untitled.max"
        detected_max_version = self._parse_max_version(version)
        renderer_class = None
        try:
            renderer_class = self._class_name(self.rt.renderers.current)
        except Exception:
            pass

        try:
            getattr(self.rt, "VRayMtl")
            vray_installed = True
        except Exception:
            vray_installed = False

        detected_vray_version = None
        try:
            value = self.rt.vrayVersion()
            if value is not None:
                detected_vray_version = str(value)
        except Exception:
            pass

        max_matches_target = detected_max_version == TARGET_MAX_VERSION
        parsed_vray_version = self._parse_vray_version(detected_vray_version)
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
        if vray_installed and not vray_matches_target:
            compatibility_warnings.append(
                "Untested V-Ray version detected: {0}; target range is {1}.".format(
                    detected_vray_version or "Unknown", SUPPORTED_VRAY_RANGE
                )
            )
        return {
            "scene_name": scene_name,
            "max_version": detected_max_version,
            "display_units": display_units,
            "units_per_meter": units_per_meter,
            "renderer_class": renderer_class,
            "vray_installed": vray_installed,
            "vray_version": detected_vray_version,
            "max_matches_target": max_matches_target,
            "vray_matches_target": vray_matches_target,
            "compatibility_warnings": compatibility_warnings,
        }
