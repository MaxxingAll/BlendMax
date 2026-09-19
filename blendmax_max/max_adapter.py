"""The 3ds Max runtime facade.

All pymxs-dependent behavior is reached through this module: the methods below
either implement it directly (shared host primitives) or delegate to one of
the focused sibling modules:

``max_scene``
    Scene snapshot, version metadata and geometry bounds.
``max_materials``
    Material graph capture and texture discovery.
``max_export``
    Prepared export isolation and the FBX export call.

The moved methods keep thin delegations on :class:`MaxRuntimeAdapter` because
``MaxCleanupAdapter`` inherits this class: every moved method must stay
resolvable here or the inheritance boundary (and its subclasses) break.
Nothing in the sibling modules imports this one.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import max_export, max_materials, max_scene
from .errors import ExportError
# Re-exported for the compatibility surface: ``max_cleanup_adapter`` and the
# tests import these constants from this module.
from .max_materials import VRAY_MAP_SLOT_ALIASES, VRAY_MTL_PROPERTIES
from .models import SceneNode


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
        return max_scene.snapshot_scene(self)

    def source_metadata(self) -> Dict[str, Any]:
        return max_scene.source_metadata(self)

    def _parse_vray_version(
        self,
        raw_version: Optional[str],
    ) -> Optional[Tuple[int, int, int]]:
        return max_scene._parse_vray_version(self, raw_version)

    def _parse_max_version(self, raw_version: Iterable[str]) -> Optional[str]:
        return max_scene._parse_max_version(self, raw_version)

    def bounds_in_meters(
        self,
        payload_ids: Iterable[str],
    ) -> Dict[str, List[float]]:
        return max_scene.bounds_in_meters(self, payload_ids)

    @staticmethod
    def _node_bounds(node) -> Tuple[List[float], List[float]]:
        return max_scene._node_bounds(node)

    def _evaluated_mesh_bounds(
        self,
        node,
    ) -> Tuple[List[float], List[float]]:
        return max_scene._evaluated_mesh_bounds(self, node)

    def _primitive_value(self, value) -> Tuple[bool, Any]:
        return max_materials._primitive_value(self, value)

    def _primitive_properties(self, animatable) -> Dict[str, Any]:
        return max_materials._primitive_properties(self, animatable)

    def _filter_material_properties(
        self,
        class_name: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        return max_materials._filter_material_properties(self, class_name, properties)

    def _connected_map_controls(
        self,
        class_name: str,
        properties: Dict[str, Any],
        slot_names: Iterable[str],
    ) -> Dict[str, Any]:
        return max_materials._connected_map_controls(self, class_name, properties, slot_names)

    def capture_material_graph(
        self,
        payload_ids: Iterable[str],
    ) -> Dict[str, Any]:
        return max_materials.capture_material_graph(self, payload_ids)

    def discover_texture_references(
        self,
        material_data: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        return max_materials.discover_texture_references(self, material_data)

    def _resolve_texture_path(self, value: str) -> str:
        return max_materials._resolve_texture_path(self, value)

    @contextmanager
    def prepared_export(
        self,
        export_ids: Iterable[str],
        selection_ids: Optional[Iterable[str]] = None,
    ):
        with max_export.prepared_export(self, export_ids, selection_ids) as result:
            yield result

    def export_selected_fbx(self, output_path) -> List[str]:
        return max_export.export_selected_fbx(self, output_path)

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

