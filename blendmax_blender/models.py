"""Pure-Python data structures used by the Blender importer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class GraphLink:
    index: int
    slot: str
    ref: str


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: str
    class_name: str
    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    sub_materials: Tuple[GraphLink, ...] = ()
    sub_textures: Tuple[GraphLink, ...] = ()


@dataclass(frozen=True)
class ObjectRecord:
    object_id: str
    fbx_name: str
    original_name: str
    node_type: str
    superclass: str
    parent_id: Optional[str] = None
    is_group_head: bool = False
    is_group_member: bool = False


@dataclass(frozen=True)
class TextureRecord:
    graph_node_id: Optional[str]
    status: str
    package_path: Optional[str]
    parameter: Optional[str] = None
    raw_path: str = ""
    source_path: str = ""


@dataclass(frozen=True)
class MaterialAssignment:
    object_id: str
    material_ref: Optional[str]


@dataclass(frozen=True)
class BlendMaxManifest:
    schema_version: str
    asset_name: str
    asset_mode: str
    root_id: str
    geometry_file: str
    objects: Tuple[ObjectRecord, ...]
    graph: Tuple[GraphNode, ...]
    assignments: Tuple[MaterialAssignment, ...]
    textures: Tuple[TextureRecord, ...]
    bounds_minimum_m: Tuple[float, float, float]
    bounds_maximum_m: Tuple[float, float, float]
    recommended_scale: float
    warnings: Tuple[str, ...]
    raw: Mapping[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True)
class PackageContents:
    source_path: Path
    root: Path
    geometry_path: Path
    manifest: BlendMaxManifest
    texture_paths: Mapping[str, Path]


@dataclass(frozen=True)
class ImportSummary:
    asset_name: str
    object_count: int
    material_count: int
    image_count: int
    warnings: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
