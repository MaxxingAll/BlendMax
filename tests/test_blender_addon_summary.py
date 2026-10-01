from __future__ import annotations

import importlib.util
import ast
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from blendmax_blender.models import ImportSummary


def load_addon(module_name="blendmax_blender._addon_summary_test"):
    class FakeOperator:
        pass

    class FakePreferences:
        pass

    class FakeImportHelper:
        pass

    class FakeMenu:
        pass

    class FakeMenuCollection(list):
        def append(self, item):
            if item not in self:
                super().append(item)

        def remove(self, item):
            if item in self:
                super().remove(item)

    fake_bpy = ModuleType("bpy")
    # Blender draws ``TOPBAR_MT_editor_menus`` beside File/Edit/Render/Window/Help.
    fake_bpy.types = SimpleNamespace(
        Operator=FakeOperator,
        AddonPreferences=FakePreferences,
        Menu=FakeMenu,
        TOPBAR_MT_editor_menus=FakeMenuCollection(),
        TOPBAR_MT_file_import=FakeMenuCollection(),
        VIEW3D_MT_editor_menus=FakeMenuCollection(),
    )
    fake_bpy.props = SimpleNamespace(
        BoolProperty=lambda **_kwargs: None,
        FloatProperty=lambda **_kwargs: None,
        IntProperty=lambda **_kwargs: None,
        StringProperty=lambda **_kwargs: None,
    )
    fake_bpy.app = SimpleNamespace(driver_namespace={})
    registered_classes = []
    unregistered_classes = []
    fake_bpy.utils = SimpleNamespace(
        register_class=registered_classes.append,
        unregister_class=unregistered_classes.append,
    )
    fake_extras = ModuleType("bpy_extras")
    fake_io_utils = ModuleType("bpy_extras.io_utils")
    fake_io_utils.ImportHelper = FakeImportHelper
    fake_extras.io_utils = fake_io_utils

    addon_path = (
        Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, addon_path)
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
    module._test_registered_classes = registered_classes
    module._test_unregistered_classes = unregistered_classes
    return module


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


class BlenderAddonSummaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addon = load_addon()

    def setUp(self):
        self.addon.bpy.app.driver_namespace.clear()
        self.addon._HOT_RELOAD_CONSUMED = None
        self.addon._RELOAD_PENDING = False

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

    def test_measurement_cage_operator_reports_value_error_and_cancels(self):
        from types import ModuleType

        presentation = ModuleType("blendmax_blender.blender_presentation")

        def fail_create(*_args, **_kwargs):
            raise ValueError("Select an asset with valid mesh geometry.")

        presentation.create_measurement_cage = fail_create
        reports = []
        operator = self.addon.BLENDMAX_OT_create_measurement_cage()
        operator.report = lambda levels, message: reports.append((levels, message))
        operator.envelope_increment = 1.0
        operator.divisions_x = 1
        operator.divisions_y = 1
        operator.divisions_z = 1
        operator.in_front = True

        with patch.dict(
            sys.modules,
            {"blendmax_blender.blender_presentation": presentation},
        ):
            result = operator.execute(None)

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(
            reports,
            [({"ERROR"}, "Select an asset with valid mesh geometry.")],
        )

    def test_icon_falls_back_when_stdout_cannot_encode_glyphs(self):
        with patch.object(self.addon, "_stdout_encoding", return_value="ascii"):
            self.assertEqual(self.addon._icon("objects"), "[O]")
            self.assertEqual(self.addon._icon("warnings"), "[!]")

    def _draw_preferences(
        self,
        *,
        reload_pending,
        reload_consumed,
    ):
        preferences = self.addon.BLENDMAX_Preferences()
        layout = FakeLayout()
        preferences.layout = layout
        with patch.object(self.addon, "_RELOAD_PENDING", reload_pending), patch.object(
            self.addon, "_HOT_RELOAD_CONSUMED", reload_consumed
        ):
            preferences.draw(None)
        return layout

    def test_hot_reload_button_initial_state(self):
        layout = self._draw_preferences(
            reload_pending=False,
            reload_consumed=False,
        )

        self.assertIs(layout.row_instance.enabled, True)
        self.assertEqual(
            layout.row_instance.operator_call[1]["text"],
            "Reload BlendMax",
        )
        self.assertEqual(
            layout.labels,
            [((), {"text": "BlendMax is ready to use."})],
        )

    def test_hot_reload_button_pending_state(self):
        layout = self._draw_preferences(
            reload_pending=True,
            reload_consumed=True,
        )

        self.assertIs(layout.row_instance.enabled, False)
        self.assertEqual(
            layout.row_instance.operator_call[1]["text"],
            "Reloading BlendMax…",
        )

    def test_hot_reload_guard_survives_package_module_reload(self):
        self.addon._set_hot_reload_consumed(True)
        self.addon._HOT_RELOAD_CONSUMED = None

        self.assertTrue(self.addon._hot_reload_is_consumed())
        self.assertEqual(
            self.addon.bpy.app.driver_namespace,
            {self.addon._HOT_RELOAD_STATE_KEY: True},
        )

    def test_fresh_blender_session_starts_with_hot_reload_available(self):
        self.addon.bpy.app.driver_namespace.clear()
        self.addon._HOT_RELOAD_CONSUMED = None

        self.assertFalse(self.addon._hot_reload_is_consumed())

    def test_hot_reload_operator_cannot_execute_twice(self):
        class FakeTimers:
            def __init__(self):
                self.registered = []

            def register(self, callback, first_interval):
                self.registered.append((callback, first_interval))

        timers = FakeTimers()
        reports = []
        operator = self.addon.BLENDMAX_OT_hot_reload()
        operator.report = lambda levels, message: reports.append((levels, message))

        app = SimpleNamespace(
            timers=timers,
            driver_namespace=self.addon.bpy.app.driver_namespace,
        )
        with patch.object(self.addon, "_RELOAD_PENDING", False), patch.object(
            self.addon.bpy, "app", app
        ):
            self.assertEqual(operator.execute(None), {"FINISHED"})
            self.assertTrue(self.addon._hot_reload_is_consumed())
            self.assertEqual(operator.execute(None), {"CANCELLED"})

        self.assertEqual(len(timers.registered), 1)
        self.assertEqual(timers.registered[0][1], 0.1)
        self.assertEqual(reports, [({"INFO"}, "BlendMax reload scheduled.")])

    def test_hot_reload_timer_registration_failure_rolls_back(self):
        class FakeTimers:
            def register(self, callback, first_interval):
                raise RuntimeError("timer registration failed")

        reports = []
        operator = self.addon.BLENDMAX_OT_hot_reload()
        operator.report = lambda levels, message: reports.append((levels, message))

        app = SimpleNamespace(
            timers=FakeTimers(),
            driver_namespace=self.addon.bpy.app.driver_namespace,
        )
        with patch.object(self.addon.bpy, "app", app):
            self.assertEqual(operator.execute(None), {"CANCELLED"})
            self.assertIs(self.addon._HOT_RELOAD_CONSUMED, False)
            self.assertIs(self.addon._RELOAD_PENDING, False)
            self.assertFalse(self.addon._hot_reload_is_consumed())
        self.assertEqual(reports, [])

    def test_preferences_draw_does_not_reread_state_every_time(self):
        calls = {"count": 0}

        class CountingNamespace(dict):
            def get(self, key, default=None):
                calls["count"] += 1
                return super().get(key, default)

        preferences = self.addon.BLENDMAX_Preferences()
        preferences.layout = FakeLayout()
        namespace = CountingNamespace()
        with patch.object(
            self.addon.bpy.app, "driver_namespace", namespace
        ), patch.object(self.addon, "_RELOAD_PENDING", False), patch.object(
            self.addon, "_HOT_RELOAD_CONSUMED", None
        ):
            self.addon._HOT_RELOAD_CONSUMED = None
            preferences.draw(None)
            preferences.layout = FakeLayout()
            preferences.draw(None)

        self.assertEqual(calls["count"], 1)

    def test_restart_state_and_process_probing_are_absent(self):
        addon_path = (
            Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
        )
        addon_tree = ast.parse(addon_path.read_text(encoding="utf-8"))
        package_root = Path(__file__).resolve().parents[1] / "blendmax_blender"
        self.assertFalse((package_root / ("restart_" + "notice.py")).exists())
        identifiers = {
            node.id.lower()
            for node in ast.walk(addon_tree)
            if isinstance(node, ast.Name)
        }
        attributes = {
            node.attr.lower()
            for node in ast.walk(addon_tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertFalse(any("pid" in name for name in identifiers | attributes))
        imports_json = any(
            (
                isinstance(node, ast.Import)
                and any(alias.name == "json" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "json")
            for node in ast.walk(addon_tree)
        )
        self.assertFalse(imports_json)

    def test_preferences_do_not_draw_a_restart_required_notice(self):
        layout = self._draw_preferences(
            reload_pending=False,
            reload_consumed=False,
        )
        self.assertEqual(layout.operator_calls, [])
        self.assertEqual(
            layout.labels,
            [((), {"text": "BlendMax is ready to use."})],
        )

    def test_preferences_explain_hot_reload_limit_without_restart_prompt(self):
        layout = self._draw_preferences(
            reload_pending=False,
            reload_consumed=True,
        )
        self.assertEqual(layout.operator_calls, [])
        self.assertEqual(
            layout.labels,
            [((), {"text": "Hot Reload is limited to once per Blender session."})],
        )

    def test_addon_registers_without_restart_module_file(self):
        addon_path = (
            Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
        )
        import_modules = {
            node.module
            for node in ast.walk(
                ast.parse(addon_path.read_text(encoding="utf-8"))
            )
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("restart" + "_notice", import_modules)
        self.addon.register()
        self.addon.unregister()


class BlendMaxMenuRegistrationTests(unittest.TestCase):
    """The BlendMax menu belongs in Blender's global top application menu row."""

    def setUp(self):
        self.addon = load_addon()
        self.addon.register()

    def tearDown(self):
        self.addon.unregister()

    def test_blendmax_menu_registers_in_the_top_application_menu_row(self):
        types = self.addon.bpy.types
        self.assertIn(self.addon._menu_blendmax, types.TOPBAR_MT_editor_menus)
        self.assertNotIn(self.addon._menu_blendmax, types.VIEW3D_MT_editor_menus)
        self.assertIn(self.addon._menu_import, types.TOPBAR_MT_file_import)

    def test_unregister_removes_the_top_application_menu(self):
        self.addon.unregister()
        types = self.addon.bpy.types
        self.assertNotIn(self.addon._menu_blendmax, types.TOPBAR_MT_editor_menus)
        self.assertNotIn(self.addon._menu_blendmax, types.VIEW3D_MT_editor_menus)
        self.assertNotIn(self.addon._menu_import, types.TOPBAR_MT_file_import)

    def test_remove_measurement_cage_operator_is_registered(self):
        self.assertIn(
            self.addon.BLENDMAX_OT_remove_measurement_cage,
            self.addon._CLASSES,
        )
        self.assertEqual(
            self.addon.BLENDMAX_OT_remove_measurement_cage.bl_idname,
            "blendmax.remove_measurement_cage",
        )
        self.assertEqual(
            self.addon._test_registered_classes,
            list(self.addon._CLASSES),
        )
        self.assertEqual(self.addon._test_unregistered_classes, [])


if __name__ == "__main__":
    unittest.main()
