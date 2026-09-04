from __future__ import annotations

import json
import sys
import types
import unittest

from blendmax_blender.diagnostics import build_import_summary_view
from blendmax_blender.models import ImportSummary


class BlenderAddonSummaryContractTests(unittest.TestCase):
    def test_summary_payload_is_json_safe_for_operator_property(self):
        summary = ImportSummary(
            asset_name="Tree",
            object_count=12,
            material_count=8,
            image_count=13,
            warnings=("Missing packaged image: leaf.png",),
            notes=("Known V-Ray parameter is not supported yet",),
        )

        payload = json.dumps(build_import_summary_view(summary), ensure_ascii=False)
        decoded = json.loads(payload)

        self.assertEqual(decoded["asset_name"], "Tree")
        self.assertEqual(decoded["object_count"], 12)
        self.assertEqual(decoded["material_count"], 8)
        self.assertEqual(decoded["image_count"], 13)
        self.assertEqual(decoded["warnings"], ["Missing packaged image: leaf.png"])
        self.assertEqual(decoded["notes"], ["Known V-Ray parameter is not supported yet"])

    def test_summary_payload_does_not_require_blender_runtime(self):
        self.assertNotIn("bpy", sys.modules)
        self.assertNotIn("bpy_extras", sys.modules)


if __name__ == "__main__":
    unittest.main()
