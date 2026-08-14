"""High-level Max-to-.blendmax export orchestration."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import __version__
from .errors import ExportError
from .package import (
    copy_texture_files,
    create_archive,
    ensure_blendmax_suffix,
    write_manifest,
)
from .validation import evaluate_size_policy, validate_scene


class BlendMaxExporter:
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    def export(self, output_path) -> Dict[str, Any]:
        snapshots = self.adapter.snapshot_scene()
        validation = validate_scene(snapshots)
        snapshot_by_id = {node.node_id: node for node in snapshots}

        bounds = self.adapter.bounds_in_meters(validation.payload_ids)
        size_policy = evaluate_size_policy(bounds["dimensions"])
        material_data = self.adapter.capture_material_graph(validation.payload_ids)
        texture_paths = self.adapter.discover_texture_paths(material_data)

        output = ensure_blendmax_suffix(output_path)
        all_warnings: List[str] = list(validation.warnings)
        source_metadata = self.adapter.source_metadata()
        all_warnings.extend(
            source_metadata.get("compatibility", {}).get("warnings", [])
        )

        with tempfile.TemporaryDirectory(prefix="blendmax_export_") as temporary:
            stage = Path(temporary)
            fbx_path = stage / "geometry.fbx"

            with self.adapter.prepared_export(validation.export_ids) as export_names:
                all_warnings.extend(self.adapter.export_selected_fbx(fbx_path))

            texture_records = copy_texture_files(
                texture_paths,
                stage / "textures",
            )
            missing_count = sum(
                1 for record in texture_records if record["status"] == "missing"
            )
            if missing_count:
                all_warnings.append(
                    "{0} referenced texture file(s) could not be copied.".format(
                        missing_count
                    )
                )

            root = snapshot_by_id[validation.root_id]
            object_records = []
            for node_id in validation.export_ids:
                node = snapshot_by_id[node_id]
                object_records.append(
                    {
                        "id": node.node_id,
                        "original_name": node.name,
                        "fbx_name": export_names[node.node_id],
                        "node_type": node.node_type,
                        "superclass": node.superclass,
                        "parent_id": node.parent_id,
                        "is_group_head": node.is_group_head,
                        "is_group_member": node.is_group_member,
                    }
                )

            manifest = {
                "schema": {
                    "name": "BlendMax Manifest",
                    "version": "0.1.0",
                },
                "generator": {
                    "name": "BlendMax Max Exporter",
                    "version": __version__,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                },
                "source": source_metadata,
                "asset": {
                    "name": root.name,
                    "mode": validation.mode,
                    "root_id": validation.root_id,
                    "object_count": validation.object_count,
                    "bounds_m": bounds,
                    "size_policy": {
                        "maximum_footprint_m": 50.0,
                        "oversized": size_policy.oversized,
                        "recommended_blender_scale": size_policy.recommended_scale,
                    },
                },
                "geometry": {
                    "file": "geometry.fbx",
                    "format": "FBX binary",
                    "unit": "meter",
                    "up_axis": "Z",
                    "animation": False,
                },
                "objects": object_records,
                "materials": material_data,
                "textures": texture_records,
                "warnings": all_warnings,
            }
            write_manifest(stage / "manifest.json", manifest)
            created_path = create_archive(stage, output)

        if not created_path.is_file():
            raise ExportError("BlendMax package creation failed.")
        return {
            "path": str(created_path),
            "asset_name": root.name,
            "object_count": validation.object_count,
            "texture_count": sum(
                1 for record in texture_records if record["status"] == "copied"
            ),
            "warning_count": len(all_warnings),
            "recommended_blender_scale": size_policy.recommended_scale,
        }
