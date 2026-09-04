from __future__ import annotations

import unittest

from blendmax_blender.diagnostics import build_import_summary_view
from blendmax_blender.models import ImportSummary


class BlenderDiagnosticsViewTests(unittest.TestCase):
    def test_empty_summary_has_empty_diagnostic_sections(self):
        summary = ImportSummary("Basketball", 1, 2, 2)
        view = build_import_summary_view(summary)

        self.assertEqual(view["warnings"], ())
        self.assertEqual(view["notes"], ())


if __name__ == "__main__":
    unittest.main()
