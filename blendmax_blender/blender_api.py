"""Blender operator compatibility and FBX import for the BlendMax importer.

Split out of ``blender_adapter`` so that the adapter stays an orchestration
layer. Nothing here reaches back into the adapter or into scene/material code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set

import bpy

from .errors import BlendMaxImportError


def _operator_properties(operator) -> Optional[Set[str]]:
    try:
        return {
            item.identifier
            for item in operator.get_rna_type().properties
            if item.identifier != "rna_type"
        }
    except (AttributeError, RuntimeError):
        return None


def _call_supported(
    operator,
    candidates: Dict[str, object],
    supported: Optional[Set[str]] = None,
):
    supported = supported if supported is not None else _operator_properties(operator)
    if supported is None:
        raise BlendMaxImportError("The requested Blender import operator is unavailable.")
    return operator(**{key: value for key, value in candidates.items() if key in supported})


def _import_fbx(path: Path):
    new_operator = getattr(getattr(bpy.ops, "wm", None), "fbx_import", None)
    new_properties = _operator_properties(new_operator) if new_operator is not None else None
    if new_operator is not None and new_properties is not None:
        return _call_supported(
            new_operator,
            {
                "filepath": str(path),
                "import_meshes": True,
                "import_materials": True,
                "import_cameras": False,
                "import_lights": False,
                "import_animation": False,
                "use_anim": False,
            },
            supported=new_properties,
        )

    legacy_operator = getattr(getattr(bpy.ops, "import_scene", None), "fbx", None)
    if legacy_operator is None:
        raise BlendMaxImportError(
            "No Blender FBX importer is available. Enable Blender's FBX import support."
        )
    return _call_supported(
        legacy_operator,
        {
            "filepath": str(path),
            "use_custom_normals": True,
            "use_image_search": False,
            "use_anim": False,
        },
    )
