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

    def test_hot_reload_button_is_disabled_while_reload_is_pending(self):
        class FakeRow:
            def __init__(self):
                self.enabled = None
                self.operator_call = None

            def operator(self, *args, **kwargs):
                self.operator_call = (args, kwargs)

        class FakeLayout:
            def __init__(self):
                self.row_instance = FakeRow()
                self.operator_calls = []
                self.labels = []

            def row(self):
                return self.row_instance

            def operator(self, *args, **kwargs):
                self.operator_calls.append((args, kwargs))

            def label(self, *args, **kwargs):
                self.labels.append((args, kwargs))

        preferences = self.addon.BLENDMAX_Preferences()

        ready_layout = FakeLayout()
        preferences.layout = ready_layout
        with patch.object(self.addon, "_RELOAD_PENDING", False), patch.object(
            self.addon, "_RESTART_NOTICE_REQUIRED", False
        ):
            preferences.draw(None)

        self.assertIs(ready_layout.row_instance.enabled, True)
        self.assertEqual(
            ready_layout.row_instance.operator_call[1]["text"],
            "Reload BlendMax",
        )
        self.assertEqual(ready_layout.operator_calls, [])
        self.assertEqual(
            ready_layout.labels,
            [((), {"text": "BlendMax is ready to use."})],
        )

        pending_layout = FakeLayout()
        preferences.layout = pending_layout
        with patch.object(self.addon, "_RELOAD_PENDING", True), patch.object(
            self.addon, "_RESTART_NOTICE_REQUIRED", True
        ):
            preferences.draw(None)

        self.assertIs(pending_layout.row_instance.enabled, False)
        self.assertEqual(
            pending_layout.row_instance.operator_call[1]["text"],
            "Reloading BlendMax…",
        )
        self.assertEqual(
            pending_layout.operator_calls,
            [
                (
                    (self.addon.BLENDMAX_OT_restart_blender_notice.bl_idname,),
                    {"text": "⚠ Restart Blender", "icon": "ERROR"},
                )
            ],
        )
        self.assertEqual(pending_layout.labels, [])

    def test_hot_reload_operator_schedules_only_one_reload(self):
        class FakeTimers:
            def __init__(self):
                self.registered = []

            def register(self, callback, first_interval):
                self.registered.append((callback, first_interval))

        timers = FakeTimers()
        reports = []
        operator = self.addon.BLENDMAX_OT_hot_reload()
        operator.report = lambda levels, message: reports.append((levels, message))

        with patch.object(self.addon, "_RELOAD_PENDING", False):
            with patch.object(
                self.addon.bpy,
                "app",
                SimpleNamespace(timers=timers),
                create=True,
            ):
                self.assertEqual(operator.execute(None), {"FINISHED"})
                self.assertEqual(operator.execute(None), {"FINISHED"})

        self.assertEqual(len(timers.registered), 1)
        self.assertEqual(timers.registered[0][1], 0.1)
        self.assertEqual(
            reports,
            [
                ({"INFO"}, "BlendMax reload scheduled."),
                ({"INFO"}, "BlendMax reload is already scheduled."),
            ],
        )


if __name__ == "__main__":
    unittest.main()
