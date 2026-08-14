"""All pymxs-dependent behavior lives in this module."""

from __future__ import annotations

import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import TARGET_MAX_VERSION, TARGET_VRAY_VERSION
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

    def _is_exportable_superclass(self, superclass: str) -> bool:
        lowered = superclass.casefold()
        return "geometryclass" in lowered or "shape" in lowered

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
            snapshots.append(
                SceneNode(
                    node_id=node_id,
                    name=str(getattr(node, "name", "Unnamed")),
                    node_type=self._class_name(node),
                    superclass=superclass,
                    parent_id=parent_id,
                    is_group_head=is_group_head,
                    is_group_member=is_group_member,
                    exportable=self._is_exportable_superclass(superclass),
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
        vray_matches_target = bool(
            detected_vray_version
            and TARGET_VRAY_VERSION in detected_vray_version
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
                "V-Ray was not detected; target is V-Ray {0}.".format(
                    TARGET_VRAY_VERSION
                )
            )
        elif detected_vray_version and not vray_matches_target:
            compatibility_warnings.append(
                "Untested V-Ray version detected: {0}; target is {1}.".format(
                    detected_vray_version, TARGET_VRAY_VERSION
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
            },
            "compatibility": {
                "target_3ds_max": TARGET_MAX_VERSION,
                "target_vray": TARGET_VRAY_VERSION,
                "max_matches_target": max_matches_target,
                "vray_matches_target": vray_matches_target,
                "warnings": compatibility_warnings,
            },
        }

    def _parse_max_version(self, raw_version: Iterable[str]) -> Optional[str]:
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
                if re.fullmatch(r"\.\d+", candidate):
                    update = candidate
            return "{0}{1}".format(year, update)
        return None

    def bounds_in_meters(
        self,
        payload_ids: Iterable[str],
    ) -> Dict[str, List[float]]:
        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        found = False

        for node_id in payload_ids:
            node = self._nodes_by_id[node_id]
            try:
                node_min = node.min
                node_max = node.max
                values_min = [float(node_min.x), float(node_min.y), float(node_min.z)]
                values_max = [float(node_max.x), float(node_max.y), float(node_max.z)]
            except Exception as exc:
                raise ExportError(
                    "Could not calculate the bounding box for {0}: {1}".format(
                        getattr(node, "name", node_id), exc
                    )
                )
            for index in range(3):
                minimum[index] = min(minimum[index], values_min[index])
                maximum[index] = max(maximum[index], values_max[index])
            found = True

        if not found:
            raise ExportError("No geometry was available for bounds calculation.")

        try:
            units_per_meter = float(self.rt.units.decodeValue("1m"))
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

    def _primitive_value(self, value) -> Tuple[bool, Any]:
        if value is None:
            return True, None
        if isinstance(value, (bool, int, float, str)):
            return True, value

        class_name = self._class_name(value).casefold()
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

    def _primitive_properties(self, animatable) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}
        try:
            names = list(self.rt.getPropNames(animatable))
        except Exception:
            return properties

        for property_name in names:
            key = str(property_name)
            if key.casefold() in {"name"}:
                continue
            try:
                value = self.rt.getProperty(animatable, property_name)
                supported, encoded = self._primitive_value(value)
                if supported:
                    properties[key] = encoded
            except Exception:
                continue
        return properties

    def _filter_material_properties(
        self,
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
        self,
        class_name: str,
        properties: Dict[str, Any],
        slot_names: Iterable[str],
    ) -> Dict[str, Any]:
        if class_name.casefold() != "vraymtl":
            return {}

        normalized_slots = {
            re.sub(r"[^a-z0-9]", "", str(slot).casefold())
            for slot in slot_names
        }
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
            if normalized_stem in normalized_slots:
                controls[key] = value
        return controls

    def capture_material_graph(
        self,
        payload_ids: Iterable[str],
    ) -> Dict[str, Any]:
        graph: Dict[str, Dict[str, Any]] = {}

        def visit(animatable, kind: str) -> Optional[str]:
            if animatable is None:
                return None
            try:
                if animatable == self.rt.undefined:
                    return None
            except Exception:
                pass

            reference = "{0}_{1}".format(kind[:3], self._anim_id(animatable))
            if reference in graph:
                return reference

            class_name = self._class_name(animatable)
            all_properties = self._primitive_properties(animatable)
            entry: Dict[str, Any] = {
                "id": reference,
                "kind": kind,
                "name": str(getattr(animatable, "name", reference)),
                "class": class_name,
                "parameters": self._filter_material_properties(
                    class_name,
                    all_properties,
                ),
                "sub_materials": [],
                "sub_textures": [],
            }
            graph[reference] = entry

            try:
                sub_material_count = int(self.rt.getNumSubMtls(animatable))
            except Exception:
                sub_material_count = 0
            for index in range(1, sub_material_count + 1):
                try:
                    child = self.rt.getSubMtl(animatable, index)
                    child_ref = visit(child, "material")
                    try:
                        slot = str(self.rt.getSubMtlSlotName(animatable, index))
                    except Exception:
                        slot = str(index)
                    if child_ref:
                        entry["sub_materials"].append(
                            {"index": index, "slot": slot, "ref": child_ref}
                        )
                except Exception:
                    continue

            try:
                sub_texture_count = int(self.rt.getNumSubTexmaps(animatable))
            except Exception:
                sub_texture_count = 0
            connected_slot_names = []
            for index in range(1, sub_texture_count + 1):
                try:
                    child = self.rt.getSubTexmap(animatable, index)
                    child_ref = visit(child, "texture")
                    try:
                        slot = str(self.rt.getSubTexmapSlotName(animatable, index))
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
                self._connected_map_controls(
                    class_name,
                    all_properties,
                    connected_slot_names,
                )
            )
            entry["parameter_count"] = len(entry["parameters"])
            return reference

        assignments = []
        for node_id in payload_ids:
            node = self._nodes_by_id[node_id]
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

    def discover_texture_paths(self, material_data: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        likely_path_tokens = ("filename", "file", "path", "mapname", "bitmap")
        for entry in material_data.get("graph", []):
            if entry.get("kind") != "texture":
                continue
            for key, value in entry.get("parameters", {}).items():
                if not isinstance(value, str):
                    continue
                if any(token in key.casefold() for token in likely_path_tokens):
                    candidates.append(self._resolve_texture_path(value))

        for class_name in ("Bitmaptexture", "VRayBitmap"):
            try:
                texture_class = getattr(self.rt, class_name)
                instances = list(self.rt.getClassInstances(texture_class))
            except Exception:
                continue
            for texture in instances:
                for property_name in ("filename", "file", "HDRIMapName"):
                    try:
                        raw_value = getattr(texture, property_name)
                    except Exception:
                        continue
                    if raw_value is None:
                        continue
                    try:
                        if raw_value == self.rt.undefined:
                            continue
                    except Exception:
                        pass
                    value = str(raw_value).strip()
                    if value and value.casefold() not in {"none", "undefined"}:
                        candidates.append(self._resolve_texture_path(value))

        return list(dict.fromkeys(path for path in candidates if path))

    def _resolve_texture_path(self, value: str) -> str:
        raw = os.path.expandvars(str(value)).strip()
        if not raw or raw.casefold() in {"none", "undefined"}:
            return ""
        if os.path.isabs(raw) and os.path.isfile(raw):
            return os.path.normpath(raw)

        scene_directory = str(getattr(self.rt, "maxFilePath", ""))
        if scene_directory:
            scene_candidate = os.path.join(scene_directory, raw)
            if os.path.isfile(scene_candidate):
                return os.path.normpath(scene_candidate)

        try:
            resolved = str(self.rt.pathConfig.resolvePath(raw))
            if resolved and os.path.isfile(resolved):
                return os.path.normpath(resolved)
        except Exception:
            pass
        return os.path.normpath(raw)

    @contextmanager
    def prepared_export(self, export_ids: Iterable[str]):
        ids = list(export_ids)
        nodes = [self._nodes_by_id[node_id] for node_id in ids]
        previous_selection = list(self.rt.selection)
        renamed: List[Tuple[Any, str]] = []
        export_names: Dict[str, str] = {}

        try:
            for node_id, node in zip(ids, nodes):
                original_name = str(node.name)
                export_name = "BM_{0}".format(uuid.uuid4().hex[:16])
                renamed.append((node, original_name))
                node.name = export_name
                export_names[node_id] = export_name

            self.rt.clearSelection()
            try:
                self.rt.select(self.rt.Array(*nodes))
            except Exception:
                self.rt.select(nodes)
            yield export_names
        finally:
            for node, original_name in renamed:
                try:
                    node.name = original_name
                except Exception:
                    pass
            try:
                self.rt.clearSelection()
                if previous_selection:
                    try:
                        self.rt.select(self.rt.Array(*previous_selection))
                    except Exception:
                        self.rt.select(previous_selection)
            except Exception:
                pass

    def export_selected_fbx(self, output_path) -> List[str]:
        warnings: List[str] = []
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.rt.pluginManager.loadClass(self.rt.FBXEXPORTER)
        except Exception:
            pass

        try:
            self.rt.FBXExporterSetParam("ResetExport")
        except Exception:
            warnings.append("The FBX exporter preset could not be reset; explicit BlendMax settings were still applied.")

        settings = {
            "Animation": False,
            "ASCII": False,
            "Cameras": False,
            "Lights": False,
            "EmbedTextures": False,
            "ConvertUnit": "m",
            "Preserveinstances": True,
            "Shape": False,
            "Skin": False,
            "ShowWarnings": False,
            "SmoothingGroups": True,
            "TangentSpaceExport": True,
            "Triangulate": False,
            "UpAxis": "Z",
        }
        for key, value in settings.items():
            try:
                result = self.rt.FBXExporterSetParam(key, value)
                if str(result).casefold() == "unsupplied":
                    warnings.append("FBX setting was not supported: {0}".format(key))
            except Exception as exc:
                warnings.append("Could not set FBX option {0}: {1}".format(key, exc))

        try:
            self.rt.exportFile(
                str(output),
                self.rt.Name("noPrompt"),
                selectedOnly=True,
                using=self.rt.FBXEXP,
            )
        except Exception as exc:
            raise ExportError("3ds Max FBX export failed: {0}".format(exc))

        if not output.is_file() or output.stat().st_size == 0:
            raise ExportError("3ds Max did not create a usable FBX file.")
        return warnings

    def choose_output_path(self) -> Optional[str]:
        scene_name = str(getattr(self.rt, "maxFileName", ""))
        stem = Path(scene_name).stem if scene_name else "BlendMax_Asset"
        directory = str(getattr(self.rt, "maxFilePath", ""))
        initial = os.path.join(directory, stem + ".blendmax") if directory else stem + ".blendmax"
        try:
            result = self.rt.getSaveFileName(
                caption="Export BlendMax Package",
                filename=initial,
                types="BlendMax Package (*.blendmax)|*.blendmax|",
            )
        except Exception as exc:
            raise ExportError("Could not open the save dialog: {0}".format(exc))
        if not result:
            return None
        return str(result)

    def notify(self, message: str, title: str = "BlendMax") -> None:
        try:
            self.rt.messageBox(str(message), title=title)
        except Exception:
            print("{0}: {1}".format(title, message))
