"""Read and index BlendMax manifest schema 0.1.x."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .errors import ManifestValidationError
from .models import (
    BlendMaxManifest,
    GraphLink,
    GraphNode,
    MaterialAssignment,
    ObjectRecord,
    TextureRecord,
)


SUPPORTED_SCHEMA_FAMILY = (0, 1)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError("{0} must be a JSON object.".format(label))
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ManifestValidationError("{0} must be a JSON array.".format(label))
    return value


def _text(value: Any, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ManifestValidationError("{0} must be a non-empty string.".format(label))
    return value.strip()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestValidationError("{0} must be numeric.".format(label))
    return float(value)


def _vector3(value: Any, label: str) -> Tuple[float, float, float]:
    values = _sequence(value, label)
    if len(values) != 3:
        raise ManifestValidationError("{0} must contain three numbers.".format(label))
    return tuple(_number(item, label) for item in values)  # type: ignore[return-value]


def _parse_schema(raw: Mapping[str, Any]) -> str:
    schema = _mapping(raw.get("schema"), "schema")
    name = _text(schema.get("name"), "schema.name")
    version = _text(schema.get("version"), "schema.version")
    if name != "BlendMax Manifest":
        raise ManifestValidationError("Unsupported manifest name: {0}.".format(name))
    match = _VERSION_RE.match(version)
    if not match:
        raise ManifestValidationError("Invalid manifest schema version: {0}.".format(version))
    family = (int(match.group(1)), int(match.group(2)))
    if family != SUPPORTED_SCHEMA_FAMILY:
        raise ManifestValidationError(
            "Manifest schema {0} is not compatible with importer schema 0.1.x.".format(
                version
            )
        )
    return version


def _parse_links(value: Any, label: str) -> Tuple[GraphLink, ...]:
    links = []
    for offset, raw_link in enumerate(_sequence(value, label)):
        item = _mapping(raw_link, "{0}[{1}]".format(label, offset))
        index_value = item.get("index")
        if isinstance(index_value, bool) or not isinstance(index_value, int):
            raise ManifestValidationError(
                "{0}[{1}].index must be an integer.".format(label, offset)
            )
        links.append(
            GraphLink(
                index=index_value,
                slot=_text(item.get("slot", ""), "{0}[{1}].slot".format(label, offset), True),
                ref=_text(item.get("ref"), "{0}[{1}].ref".format(label, offset)),
            )
        )
    return tuple(links)


def _parse_graph(materials: Mapping[str, Any]) -> Tuple[GraphNode, ...]:
    graph = []
    seen = set()
    for offset, raw_node in enumerate(_sequence(materials.get("graph", []), "materials.graph")):
        item = _mapping(raw_node, "materials.graph[{0}]".format(offset))
        node_id = _text(item.get("id"), "materials.graph[{0}].id".format(offset))
        if node_id in seen:
            raise ManifestValidationError("Duplicate material graph id: {0}.".format(node_id))
        seen.add(node_id)
        parameters = _mapping(
            item.get("parameters", {}),
            "materials.graph[{0}].parameters".format(offset),
        )
        graph.append(
            GraphNode(
                node_id=node_id,
                kind=_text(item.get("kind", "unknown"), "materials.graph[{0}].kind".format(offset)),
                class_name=_text(item.get("class", "Unknown"), "materials.graph[{0}].class".format(offset)),
                name=_text(item.get("name", node_id), "materials.graph[{0}].name".format(offset), True),
                parameters=dict(parameters),
                sub_materials=_parse_links(
                    item.get("sub_materials", []),
                    "materials.graph[{0}].sub_materials".format(offset),
                ),
                sub_textures=_parse_links(
                    item.get("sub_textures", []),
                    "materials.graph[{0}].sub_textures".format(offset),
                ),
            )
        )
    return tuple(graph)


def _parse_objects(raw: Mapping[str, Any]) -> Tuple[ObjectRecord, ...]:
    objects = []
    ids = set()
    fbx_names = set()
    for offset, raw_object in enumerate(_sequence(raw.get("objects", []), "objects")):
        item = _mapping(raw_object, "objects[{0}]".format(offset))
        object_id = _text(item.get("id"), "objects[{0}].id".format(offset))
        fbx_name = _text(item.get("fbx_name"), "objects[{0}].fbx_name".format(offset))
        if object_id in ids:
            raise ManifestValidationError("Duplicate object id: {0}.".format(object_id))
        if fbx_name.casefold() in fbx_names:
            raise ManifestValidationError("Duplicate FBX object name: {0}.".format(fbx_name))
        ids.add(object_id)
        fbx_names.add(fbx_name.casefold())
        parent = item.get("parent_id")
        objects.append(
            ObjectRecord(
                object_id=object_id,
                fbx_name=fbx_name,
                original_name=_text(
                    item.get("original_name", fbx_name),
                    "objects[{0}].original_name".format(offset),
                    True,
                ),
                node_type=_text(
                    item.get("node_type", "Unknown"),
                    "objects[{0}].node_type".format(offset),
                    True,
                ),
                superclass=_text(
                    item.get("superclass", "Unknown"),
                    "objects[{0}].superclass".format(offset),
                    True,
                ),
                parent_id=str(parent) if parent is not None else None,
                is_group_head=bool(item.get("is_group_head", False)),
                is_group_member=bool(item.get("is_group_member", False)),
            )
        )
    if not objects:
        raise ManifestValidationError("The manifest contains no object records.")
    return tuple(objects)


def _parse_assignments(materials: Mapping[str, Any]) -> Tuple[MaterialAssignment, ...]:
    assignments = []
    for offset, raw_assignment in enumerate(
        _sequence(materials.get("assignments", []), "materials.assignments")
    ):
        item = _mapping(raw_assignment, "materials.assignments[{0}]".format(offset))
        material_ref = item.get("material_ref")
        assignments.append(
            MaterialAssignment(
                object_id=_text(
                    item.get("object_id"),
                    "materials.assignments[{0}].object_id".format(offset),
                ),
                material_ref=(str(material_ref) if material_ref is not None else None),
            )
        )
    return tuple(assignments)


def _parse_textures(raw: Mapping[str, Any]) -> Tuple[TextureRecord, ...]:
    textures = []
    for offset, raw_texture in enumerate(_sequence(raw.get("textures", []), "textures")):
        item = _mapping(raw_texture, "textures[{0}]".format(offset))
        package_path = item.get("package_path")
        parameter = item.get("parameter")
        graph_node_id = item.get("graph_node_id")
        textures.append(
            TextureRecord(
                graph_node_id=(str(graph_node_id) if graph_node_id else None),
                status=_text(item.get("status", "missing"), "textures[{0}].status".format(offset)),
                package_path=(str(package_path) if package_path else None),
                parameter=(str(parameter) if parameter else None),
                raw_path=str(item.get("raw_path") or ""),
                source_path=str(item.get("source_path") or ""),
            )
        )
    return tuple(textures)


def parse_manifest(raw: Mapping[str, Any]) -> BlendMaxManifest:
    raw = _mapping(raw, "manifest")
    schema_version = _parse_schema(raw)
    asset = _mapping(raw.get("asset"), "asset")
    geometry = _mapping(raw.get("geometry"), "geometry")
    materials = _mapping(raw.get("materials", {}), "materials")
    bounds = _mapping(asset.get("bounds_m"), "asset.bounds_m")
    size_policy = _mapping(asset.get("size_policy", {}), "asset.size_policy")
    warnings_value = _sequence(raw.get("warnings", []), "warnings")

    manifest = BlendMaxManifest(
        schema_version=schema_version,
        asset_name=_text(asset.get("name"), "asset.name"),
        asset_mode=_text(asset.get("mode"), "asset.mode"),
        root_id=_text(asset.get("root_id"), "asset.root_id"),
        geometry_file=_text(geometry.get("file"), "geometry.file"),
        objects=_parse_objects(raw),
        graph=_parse_graph(materials),
        assignments=_parse_assignments(materials),
        textures=_parse_textures(raw),
        bounds_minimum_m=_vector3(bounds.get("minimum"), "asset.bounds_m.minimum"),
        bounds_maximum_m=_vector3(bounds.get("maximum"), "asset.bounds_m.maximum"),
        recommended_scale=_number(
            size_policy.get("recommended_blender_scale", 1.0),
            "asset.size_policy.recommended_blender_scale",
        ),
        warnings=tuple(str(item) for item in warnings_value),
        raw=dict(raw),
    )
    if manifest.root_id not in {item.object_id for item in manifest.objects}:
        raise ManifestValidationError("asset.root_id does not reference an object record.")
    if not manifest.geometry_file.casefold().endswith(".fbx"):
        raise ManifestValidationError("geometry.file must reference an FBX file.")
    if manifest.recommended_scale <= 0.0:
        raise ManifestValidationError(
            "asset.size_policy.recommended_blender_scale must be greater than zero."
        )
    return manifest


def load_manifest(path: Path) -> BlendMaxManifest:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestValidationError("Could not read manifest.json: {0}".format(exc)) from exc
    return parse_manifest(raw)


class ManifestIndex:
    """O(1) lookup tables built once per import."""

    def __init__(self, manifest: BlendMaxManifest):
        self.manifest = manifest
        self.nodes_by_id: Dict[str, GraphNode] = {
            node.node_id: node for node in manifest.graph
        }
        self.objects_by_id: Dict[str, ObjectRecord] = {
            item.object_id: item for item in manifest.objects
        }
        self.objects_by_fbx_name: Dict[str, ObjectRecord] = {
            item.fbx_name.casefold(): item for item in manifest.objects
        }
        self.assignments_by_object: Dict[str, MaterialAssignment] = {
            item.object_id: item for item in manifest.assignments
        }
        self.textures_by_graph_node: Dict[str, TextureRecord] = {}
        for item in manifest.textures:
            if (
                item.package_path
                and item.graph_node_id
                and item.graph_node_id not in self.textures_by_graph_node
            ):
                self.textures_by_graph_node[item.graph_node_id] = item
        self._match_legacy_texture_records()

    @staticmethod
    def _path_key(value: Any) -> str:
        return str(value or "").replace("\\", "/").rsplit("/", 1)[-1].casefold()

    def _match_legacy_texture_records(self) -> None:
        """Best-effort mapping for schema 0.1.0 records without graph ids."""
        legacy = [
            item
            for item in self.manifest.textures
            if not item.graph_node_id and item.package_path
        ]
        if not legacy:
            return
        for node in self.manifest.graph:
            if node.kind.casefold() != "texture" or node.node_id in self.textures_by_graph_node:
                continue
            parameter_keys = {
                self._path_key(value)
                for value in node.parameters.values()
                if isinstance(value, str) and value
            }
            if not parameter_keys:
                continue
            match = next(
                (
                    item
                    for item in legacy
                    if self._path_key(item.package_path) in parameter_keys
                    or self._path_key(item.raw_path) in parameter_keys
                    or self._path_key(item.source_path) in parameter_keys
                ),
                None,
            )
            if match is not None:
                self.textures_by_graph_node[node.node_id] = match

    def node(self, ref: str) -> GraphNode | None:
        return self.nodes_by_id.get(ref)


def material_references(nodes: Iterable[GraphNode]) -> Tuple[str, ...]:
    return tuple(node.node_id for node in nodes if node.kind.casefold() == "material")
