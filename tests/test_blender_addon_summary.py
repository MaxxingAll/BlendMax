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

    class FakeRow:
        def __init__(self, layout):
            self.layout = layout
            self.alert = False

        def operator(self, *args, **kwargs):
            self.layout.operator_calls.append((args, kwargs))

        def label(self, *args, **kwargs):
            self.layout.labels.append((args, kwargs))

    class FakeLayout:
        def __init__(self):
            self.operator_calls = []
            self.labels = []

        def box(self):
            return self

        def column(self):
            return self

        def row(self):
            return FakeRow(self)

        def separator(self):
            pass

        def label(self, *args, **kwargs):
            self.labels.append((args, kwargs))

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
    restart_events = []
    fake_restart_notice = ModuleType("blendmax_blender.restart_notice")
    fake_restart_notice.register = lambda: restart_events.append("register")
    fake_restart_notice.unregister = lambda: restart_events.append("unregister")
    fake_restart_notice.draw_notice = lambda _layout: False
    fake_restart_notice.disk_version = lambda: "0.1.11"
    fake_restart_notice.running_version = lambda: "0.1.10"

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
            "blendmax_blender.restart_notice": fake_restart_notice,
        },
    ):
        spec.loader.exec_module(module)
    module._test_registered_classes = registered_classes
    module._test_unregistered_classes = unregistered_classes
    module._test_restart_events = restart_events
    module._test_fake_layout = FakeLayout
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

    def test_restart_module_has_no_pid_state(self):
        package_root = Path(__file__).resolve().parents[1] / "blendmax_blender"
        trees = [
            ast.parse((package_root / filename).read_text(encoding="utf-8"))
            for filename in ("addon.py", "restart_notice.py")
        ]
        identifiers = {
            node.id.lower()
            for tree in trees
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        attributes = {
            node.attr.lower()
            for tree in trees
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertFalse(any("pid" in name for name in identifiers | attributes))

    def test_restart_state_is_confined_to_the_documented_file(self):
        package_root = Path(__file__).resolve().parents[1] / "blendmax_blender"
        notice_tree = ast.parse(
            (package_root / "restart_notice.py").read_text(encoding="utf-8")
        )
        addon_tree = ast.parse(
            (package_root / "addon.py").read_text(encoding="utf-8")
        )
        state_filenames = [
            node.value.value
            for node in ast.walk(notice_tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_STATE_FILENAME"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
        ]
        self.assertEqual(state_filenames, ["blendmax_restart_state.json"])
        imports_json = any(
            (
                isinstance(node, ast.Import)
                and any(alias.name == "json" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "json")
            for node in ast.walk(addon_tree)
        )
        self.assertFalse(imports_json)

    def test_addon_contains_no_in_process_reload_mechanism(self):
        addon_path = (
            Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
        )
        addon_tree = ast.parse(addon_path.read_text(encoding="utf-8"))
        addon_source = addon_path.read_text(encoding="utf-8").casefold()
        self.assertNotIn("hot_reload", addon_source)
        self.assertNotIn("reload_pending", addon_source)
        self.assertNotIn("reload_consumed", addon_source)
        self.assertFalse(
            any(
                isinstance(node, ast.Attribute)
                and node.attr in {"driver_namespace", "timers"}
                for node in ast.walk(addon_tree)
            )
        )
        self.assertFalse(hasattr(self.addon, "BLENDMAX_OT_hot_reload"))
        self.assertTrue(hasattr(self.addon, "BLENDMAX_Preferences"))
        self.assertIn(self.addon.BLENDMAX_Preferences, self.addon._CLASSES)

    def test_restart_notice_is_wired_to_addon_registration_and_preferences(self):
        addon_path = (
            Path(__file__).resolve().parents[1] / "blendmax_blender" / "addon.py"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and any(alias.name == "restart_notice" for alias in node.names)
                for node in ast.walk(
                    ast.parse(addon_path.read_text(encoding="utf-8"))
                )
            )
        )
        self.addon.register()
        self.assertEqual(self.addon._test_restart_events, ["register"])
        layout = self.addon._test_fake_layout()
        preferences = self.addon.BLENDMAX_Preferences()
        preferences.layout = layout
        preferences.draw(None)
        self.assertEqual(
            layout.labels,
            [
                (
                    (),
                    {
                        "text": (
                            "Restart Blender after installing or updating BlendMax "
                            "to load the new code."
                        )
                    },
                )
            ],
        )
        self.addon.unregister()
        self.assertEqual(
            self.addon._test_restart_events,
            ["register", "unregister"],
        )

    def test_restart_popup_operators_are_registered(self):
        popup = self.addon.BLENDMAX_OT_restart_notice_popup
        later = self.addon.BLENDMAX_OT_restart_notice_later
        self.assertIn(popup, self.addon._CLASSES)
        self.assertIn(later, self.addon._CLASSES)
        self.assertEqual(popup.bl_idname, "blendmax.restart_notice_popup")
        self.assertEqual(later.bl_idname, "blendmax.restart_notice_later")

    def test_restart_popup_draws_versions_and_actions(self):
        operator = self.addon.BLENDMAX_OT_restart_notice_popup()
        layout = self.addon._test_fake_layout()
        operator.layout = layout

        operator.draw(None)

        self.assertEqual(
            [kwargs["text"] for _args, kwargs in layout.labels],
            [
                "BlendMax was updated.",
                "Restart Blender to load the new code.",
                "Installed BlendMax version: 0.1.11",
                "Running BlendMax version: 0.1.10",
            ],
        )
        self.assertEqual(
            layout.operator_calls,
            [
                (
                    ("wm.quit_blender",),
                    {"text": "Restart Blender", "icon": "ERROR"},
                ),
                (
                    ("blendmax.restart_notice_later",),
                    {"text": "Later"},
                ),
            ],
        )

    def test_restart_popup_operator_requires_the_props_popup_options(self):
        # WindowManager.invoke_props_popup refuses operators without REGISTER
        # and UNDO ("incorrect invoke function"), so the option set is pinned.
        self.assertEqual(
            self.addon.BLENDMAX_OT_restart_notice_popup.bl_options,
            {"REGISTER", "INTERNAL", "UNDO"},
        )

    def test_restart_popup_invoke_uses_props_popup_with_the_event(self):
        operator = self.addon.BLENDMAX_OT_restart_notice_popup()
        calls = []

        class FakeWindowManager:
            def invoke_props_popup(self, passed_operator, passed_event):
                calls.append((passed_operator, passed_event))
                return {"RUNNING_MODAL"}

        class FakeEvent:
            type = "MOUSEMOVE"
            value = "NOTHING"

        event = FakeEvent()
        result = operator.invoke(
            SimpleNamespace(window_manager=FakeWindowManager()), event
        )

        self.assertEqual(calls, [(operator, event)])
        self.assertEqual(result, {"RUNNING_MODAL"})


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
