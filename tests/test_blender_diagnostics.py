from __future__ import annotations

import unittest

from blendmax_blender.diagnostics import build_import_summary_view
from blendmax_blender.models import ImportSummary


class BlenderDiagnosticsTests(unittest.TestCase):
    def test_summary_view_preserves_counts_and_messages(self):
        summary = ImportSummary(
            asset_name="Ring-Light",
            object_count=26,
            material_count=26,
            image_count=8,
            warnings=("Missing packaged image: tex_2140",),
            notes=("(brdf_type) is not supported yet, wait for future BlendMax updates",),
        )

        self.assertEqual(
            build_import_summary_view(summary),
            {
                "asset_name": "Ring-Light",
                "object_count": 26,
                "material_count": 26,
                "image_count": 8,
                "warnings": ("Missing packaged image: tex_2140",),
                "notes": ("(brdf_type) is not supported yet, wait for future BlendMax updates",),
            },
        )

    def test_empty_diagnostics_are_explicitly_empty(self):
        summary = ImportSummary(
            asset_name="Basketball",
            object_count=1,
            material_count=2,
            image_count=2,
        )

        view = build_import_summary_view(summary)

        self.assertEqual(view["warnings"], ())
        self.assertEqual(view["notes"], ())
        self.assertEqual(view["object_count"], 1)
        self.assertEqual(view["material_count"], 2)
        self.assertEqual(view["image_count"], 2)


if __name__ == "__main__":
    unittest.main()
