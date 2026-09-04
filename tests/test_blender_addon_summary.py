from __future__ import annotations

import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from blendmax_blender.models import ImportSummary


def load_addon():
    class FakeOperator:
        pass

    class FakePreferences:
        pass

    class FakeImportHelper:
        pass

    fake_bpy = ModuleType("bpy")
    fake_bpy.types = SimpleNamespace(
        Operator=FakeOperator,
        AddonPreferences=FakePreferences,
    )
    fake_bpy.props = SimpleNamespace(
        BoolProperty=lambda **_kwargs: None,
        StringProperty=lambda **_kwargs: None,
    )
    fake_bpy.utils = SimpleNamespace()
    fake_extras = ModuleType("bpy_extras")
    fake_io_utils = ModuleType("bpy_extras.io_utils")
    fake_io_utils.ImportHelper = FakeImportHelper
    fake_extras.io_utils = fake_io_utils

    addon_path = (
        Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
    )
    spec = importlib.util.spec_from_file_location(
        "blendmax_blender._addon_summary_test",
        addon_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load BlendMax addon test module.")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "bpy": fake_bpy,
            "bpy.props": fake_bpy.props,
            "bpy_extras": fake_extras,
            "bpy_extras.io_utils": fake_io_utils,
        },
    ):
        spec.loader.exec_module(module)
    return module


class BlenderAddonSummaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addon = load_addon()

    def _print_summary(self, summary: ImportSummary, elapsed_seconds: float = 1.25) -> str:
        buffer = io.StringIO()
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            with redirect_stdout(buffer):
                self.addon._print_import_summary(summary, elapsed_seconds)
        return buffer.getvalue()

    def test_console_summary_includes_counts_and_diagnostics(self):
        summary = ImportSummary(
            asset_name="Tree",
            object_count=12,
            material_count=8,
            image_count=13,
            warnings=("Missing packaged image: leaf.png",),
            notes=("Known V-Ray parameter is not supported yet",),
        )

        output = self._print_summary(summary)

        self.assertIn("Asset       : Tree", output)
        self.assertIn("Objects   : 12", output)
        self.assertIn("Materials : 8", output)
        self.assertIn("Textures  : 13", output)
        self.assertIn("Warnings  : 1", output)
        self.assertIn("Notes     : 1", output)
        self.assertIn("Time      : 1.25 s", output)
        self.assertIn("Missing packaged image: leaf.png", output)
        self.assertIn("Known V-Ray parameter is not supported yet", output)
        self.assertIn("Import completed with 1 warning(s).", output)
        self.assertNotIn("Import completed successfully.", output)

    def test_clean_summary_reports_success_without_diagnostic_sections(self):
        summary = ImportSummary(
            asset_name="Basketball",
            object_count=1,
            material_count=2,
            image_count=2,
        )

        output = self._print_summary(summary)

        self.assertIn("Warnings  : 0", output)
        self.assertIn("Notes     : 0", output)
        self.assertNotIn("[!] Warnings", output)
        self.assertNotIn("[i] Compatibility Notes", output)
        self.assertIn("[OK] Import completed successfully.", output)

    def test_icon_falls_back_when_stdout_cannot_encode_glyphs(self):
        with patch.object(self.addon, "_stdout_encoding", return_value="ascii"):
            self.assertEqual(self.addon._icon("objects"), "[O]")
            self.assertEqual(self.addon._icon("warnings"), "[!]")


if __name__ == "__main__":
    unittest.main()
