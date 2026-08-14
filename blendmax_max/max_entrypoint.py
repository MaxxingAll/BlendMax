"""Interactive entry point used by the 3ds Max launcher."""

from __future__ import annotations

import traceback

from .errors import BlendMaxError
from .exporter import BlendMaxExporter
from .max_adapter import MaxRuntimeAdapter


def run_interactive() -> None:
    adapter = MaxRuntimeAdapter()
    exporter = BlendMaxExporter(adapter)

    try:
        output_path = adapter.choose_output_path()
        if not output_path:
            return
        summary = exporter.export(output_path)
        message = (
            "BlendMax export complete.\n\n"
            "Asset: {asset_name}\n"
            "Objects: {object_count}\n"
            "Textures copied: {texture_count}\n"
            "Warnings: {warning_count}\n\n"
            "Package:\n{path}"
        ).format(**summary)
        if summary["recommended_blender_scale"] < 1.0:
            message += (
                "\n\nOversized asset detected. Blender should apply scale: "
                "{0:.6f}"
            ).format(summary["recommended_blender_scale"])
        adapter.notify(message, "BlendMax Export Complete")
    except BlendMaxError as exc:
        adapter.notify(str(exc), "BlendMax: {0}".format(exc.code))
    except Exception as exc:
        print(traceback.format_exc())
        adapter.notify(
            "Unexpected exporter error: {0}\n\nSee the Python listener for details.".format(
                exc
            ),
            "BlendMax Export Failed",
        )

