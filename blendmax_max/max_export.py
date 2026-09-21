"""Prepared export isolation and the FBX export call for the Max adapter.

Split out of ``max_adapter``: this module imports neither the adapter facade
nor the scene or material modules.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import ExportError


@contextmanager
def prepared_export(
    adapter,
    export_ids: Iterable[str],
    selection_ids: Optional[Iterable[str]] = None,
):
    ids = list(export_ids)
    nodes = [adapter._nodes_by_id[node_id] for node_id in ids]
    selected_id_list = list(selection_ids) if selection_ids is not None else ids
    selection_nodes = [adapter._nodes_by_id[node_id] for node_id in selected_id_list]
    previous_selection = list(adapter.rt.selection)
    renamed: List[Tuple[Any, str]] = []
    group_states: List[Tuple[Any, bool]] = []
    export_names: Dict[str, str] = {}

    try:
        for node in nodes:
            try:
                if not bool(adapter.rt.isGroupHead(node)):
                    continue
                was_open = bool(adapter.rt.isOpenGroupHead(node))
                group_states.append((node, was_open))
                if not was_open:
                    adapter.rt.setGroupOpen(node, True)
            except Exception as exc:
                raise ExportError(
                    "Could not open asset group {0} for an isolated export: {1}".format(
                        getattr(node, "name", "Unnamed"),
                        exc,
                    )
                )

        for node_id, node in zip(ids, nodes):
            original_name = str(node.name)
            export_name = "BM_{0}".format(uuid.uuid4().hex[:16])
            renamed.append((node, original_name))
            node.name = export_name
            export_names[node_id] = export_name

        adapter.rt.clearSelection()
        try:
            adapter.rt.select(adapter.rt.Array(*selection_nodes))
        except Exception:
            adapter.rt.select(selection_nodes)

        expected_ids = set(selected_id_list)
        selected_nodes = list(adapter.rt.selection)
        selected_ids = {adapter._anim_id(node) for node in selected_nodes}
        unexpected_nodes = [
            str(getattr(node, "name", "Unnamed"))
            for node in selected_nodes
            if adapter._anim_id(node) not in expected_ids
        ]
        missing_ids = sorted(expected_ids - selected_ids)
        if unexpected_nodes or missing_ids:
            details = []
            if unexpected_nodes:
                details.append(
                    "unexpected nodes: {0}".format(", ".join(unexpected_nodes))
                )
            if missing_ids:
                details.append("missing node IDs: {0}".format(", ".join(missing_ids)))
            raise ExportError(
                "3ds Max expanded the BlendMax export selection ({0}).".format(
                    "; ".join(details)
                )
            )
        yield export_names
    finally:
        for node, original_name in renamed:
            try:
                node.name = original_name
            except Exception:
                pass
        group_restore_error = None
        for group_head, was_open in reversed(group_states):
            try:
                current_open = bool(adapter.rt.isOpenGroupHead(group_head))
                if current_open != was_open:
                    adapter.rt.setGroupOpen(group_head, was_open)
            except Exception as exc:
                if group_restore_error is None:
                    group_restore_error = exc
        try:
            adapter.rt.clearSelection()
            if previous_selection:
                try:
                    adapter.rt.select(adapter.rt.Array(*previous_selection))
                except Exception:
                    adapter.rt.select(previous_selection)
        except Exception:
            pass
        if group_restore_error is not None:
            raise ExportError(
                "BlendMax could not restore the original group state: {0}".format(
                    group_restore_error
                )
            )


def export_selected_fbx(adapter, output_path) -> List[str]:
    warnings: List[str] = []
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        adapter.rt.pluginManager.loadClass(adapter.rt.FBXEXPORTER)
    except Exception:
        pass

    settings_pushed = False
    try:
        try:
            result = adapter.rt.FBXExporterSetParam("PushSettings")
            if str(result).casefold() == "unsupplied":
                warnings.append(
                    "The FBX exporter could not preserve the current settings."
                )
            else:
                settings_pushed = True
        except Exception as exc:
            warnings.append(
                "Could not preserve the current FBX settings: {0}".format(exc)
            )

        try:
            adapter.rt.FBXExporterSetParam("ResetExport")
        except Exception:
            warnings.append(
                "The FBX exporter preset could not be reset; explicit "
                "BlendMax settings were still applied."
            )

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
                result = adapter.rt.FBXExporterSetParam(key, value)
                if str(result).casefold() == "unsupplied":
                    warnings.append(
                        "FBX setting was not supported: {0}".format(key)
                    )
            except Exception as exc:
                warnings.append(
                    "Could not set FBX option {0}: {1}".format(key, exc)
                )

        try:
            adapter.rt.exportFile(
                str(output),
                adapter.rt.Name("noPrompt"),
                selectedOnly=True,
                using=adapter.rt.FBXEXP,
            )
        except Exception as exc:
            raise ExportError("3ds Max FBX export failed: {0}".format(exc))
    finally:
        if settings_pushed:
            try:
                adapter.rt.FBXExporterSetParam("PopSettings")
            except Exception as exc:
                warnings.append(
                    "Could not restore the previous FBX settings: {0}".format(exc)
                )

    if not output.is_file() or output.stat().st_size == 0:
        raise ExportError("3ds Max did not create a usable FBX file.")
    return warnings
