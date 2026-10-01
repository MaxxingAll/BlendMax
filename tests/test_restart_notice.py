from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class FakeTimers:
    def __init__(self):
        self.callbacks = []
        self.register_calls = 0

    def is_registered(self, callback):
        return any(item is callback for item in self.callbacks)

    def register(self, callback, *, first_interval, persistent):
        self.register_calls += 1
        self.callbacks.append(callback)
        return callback

    def unregister(self, callback):
        self.callbacks = [item for item in self.callbacks if item is not callback]


class RestartNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.manifest = Path(self.tempdir.name) / "blender_manifest.toml"
        self._mtime_ns = 1_700_000_000_000_000_000
        self.write_manifest("0.1.10")

        self.timers = FakeTimers()
        self.handlers = []
        self.ops_calls = []
        self.bpy = ModuleType("bpy")
        self.bpy.app = SimpleNamespace(
            driver_namespace={},
            timers=self.timers,
            background=False,
            handlers=SimpleNamespace(depsgraph_update_post=self.handlers),
        )
        self.bpy.context = SimpleNamespace(
            window_manager=SimpleNamespace(windows=[]),
        )
        self.bpy.utils = SimpleNamespace(user_resource=self.user_resource)
        self.bpy.ops = SimpleNamespace(
            blendmax=SimpleNamespace(restart_notice_popup=self.record_popup_op)
        )
        self.notice = self.load_notice("blendmax_blender._restart_notice_test")
        self.notice._MANIFEST = self.manifest

    def tearDown(self):
        if self.notice is not None:
            self.notice.unregister()
        self.tempdir.cleanup()

    def record_popup_op(self, *args):
        self.ops_calls.append(args)
        return {"RUNNING_MODAL"}

    def user_resource(self, resource_type, path="", create=False):
        self.assertEqual(resource_type, "CONFIG")
        directory = Path(self.tempdir.name) / "config" / path
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return str(directory)

    def state_path(self):
        return (
            Path(self.tempdir.name)
            / "config"
            / "blendmax"
            / "blendmax_restart_state.json"
        )

    def read_state(self):
        with self.state_path().open("r", encoding="utf-8") as state_file:
            return json.load(state_file)

    def load_notice(self, module_name):
        module_path = (
            Path(__file__).resolve().parents[1]
            / "blendmax_blender"
            / "restart_notice.py"
        )
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load restart notice test module.")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": self.bpy}):
            spec.loader.exec_module(module)
        return module

    def write_manifest(self, version=None, *, contents=None):
        if contents is None:
            contents = 'version = "{0}"\n'.format(version)
        self.manifest.write_text(contents, encoding="utf-8")
        self._mtime_ns += 5_000_000_000
        os.utime(self.manifest, ns=(self._mtime_ns, self._mtime_ns))

    def start_and_poll(self):
        self.notice.register()
        self.assertEqual(self.notice._poll(), self.notice._POLL_SECONDS)

    def test_fresh_start_matches_manifest_without_restart_notice(self):
        self.start_and_poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.10")
        self.assertFalse(self.notice.restart_needed())
        self.assertEqual(
            self.read_state(),
            {
                "just_updated": False,
                "running_version": "0.1.10",
                "installed_version": "0.1.10",
                "popup_shown": False,
            },
        )

    def test_new_disk_version_requires_restart(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")

        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())
        self.assertEqual(
            self.read_state(),
            {
                "just_updated": True,
                "running_version": "0.1.10",
                "installed_version": "0.1.11",
                "popup_shown": False,
            },
        )

    def test_invalid_toml_preserves_last_valid_state(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.write_manifest(contents='version = "0.1.12\n')

        self.notice._poll()

        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())

    def test_deleted_manifest_preserves_last_valid_state(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.manifest.unlink()

        self.notice._poll()

        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())

    def test_downgrade_also_requires_restart(self):
        self.write_manifest("0.1.11")
        self.start_and_poll()
        self.write_manifest("0.1.10")

        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.11")
        self.assertEqual(self.notice.disk_version(), "0.1.10")
        self.assertTrue(self.notice.restart_needed())

    def test_matching_disk_version_clears_notice(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.assertTrue(self.notice.restart_needed())

        self.write_manifest("0.1.10")
        self.notice._poll()

        self.assertEqual(self.notice.disk_version(), "0.1.10")
        self.assertFalse(self.notice.restart_needed())
        self.assertFalse(self.read_state()["just_updated"])

    def test_disable_and_reenable_preserves_running_version(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.notice.unregister()

        self.notice.register()
        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())
        self.assertTrue(self.read_state()["just_updated"])

    def test_simulated_blender_restart_consumes_pending_state(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.assertTrue(self.read_state()["just_updated"])
        self.notice.unregister()
        self.bpy.app.driver_namespace.clear()

        restarted = self.load_notice("blendmax_blender._restart_notice_fresh")
        restarted._MANIFEST = self.manifest
        restarted.register()
        restarted._poll()

        self.assertEqual(restarted.running_version(), "0.1.11")
        self.assertEqual(restarted.disk_version(), "0.1.11")
        self.assertFalse(restarted.restart_needed())
        self.assertEqual(
            self.read_state(),
            {
                "just_updated": False,
                "running_version": "0.1.11",
                "installed_version": "0.1.11",
                "popup_shown": False,
            },
        )
        restarted.unregister()

    def test_further_update_while_pending_refreshes_record(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.write_manifest("0.1.12")
        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.12")
        self.assertTrue(self.notice.restart_needed())
        self.assertEqual(self.read_state()["installed_version"], "0.1.12")

    def test_corrupt_state_file_is_replaced_on_next_register(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.notice.unregister()
        self.state_path().write_text("{not valid json", encoding="utf-8")

        self.notice.register()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())
        self.assertEqual(
            self.read_state(),
            {
                "just_updated": True,
                "running_version": "0.1.10",
                "installed_version": "0.1.11",
                "popup_shown": False,
            },
        )

    def test_notice_still_works_without_a_config_directory(self):
        self.bpy.utils = SimpleNamespace()
        self.start_and_poll()
        self.write_manifest("0.1.11")

        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())

    def test_unregister_removes_timers_and_armed_dialog_handler(self):
        self.notice.register()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.assertTrue(self.timers.is_registered(self.notice._poll))
        self.assertIn(self.notice._popup_handler, self.handlers)

        self.notice.unregister()

        self.assertFalse(self.timers.is_registered(self.notice._poll))
        self.assertNotIn(self.notice._popup_handler, self.handlers)

    def test_timer_registration_is_idempotent(self):
        self.notice.register()
        self.notice.register()

        self.assertEqual(self.timers.register_calls, 1)
        self.assertEqual(len(self.timers.callbacks), 1)

    def test_draw_uses_cached_versions_without_reading_files(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()

        class Row:
            def __init__(self):
                self.alert = False
                self.operator_call = None

            def operator(self, *args, **kwargs):
                self.operator_call = (args, kwargs)

        class Layout:
            def __init__(self):
                self.row_item = Row()
                self.labels = []

            def box(self):
                return self

            def column(self):
                return self

            def row(self):
                return self.row_item

            def label(self, *args, **kwargs):
                self.labels.append((args, kwargs))

        layout = Layout()
        with patch.object(
            self.notice,
            "_read_manifest_version",
            side_effect=AssertionError("draw must not read the manifest"),
        ), patch.object(
            self.notice,
            "_read_state",
            side_effect=AssertionError("draw must not read the state file"),
        ):
            self.assertTrue(self.notice.draw_notice(layout))

        self.assertTrue(layout.row_item.alert)
        self.assertEqual(
            layout.row_item.operator_call,
            (("wm.quit_blender",), {"text": "Restart Blender", "icon": "ERROR"}),
        )
        self.assertEqual(
            [kwargs["text"] for _args, kwargs in layout.labels],
            [
                "Installed BlendMax version: 0.1.11",
                "Running BlendMax version: 0.1.10",
            ],
        )

    def test_update_detection_arms_a_one_shot_dialog_handler(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")

        self.notice._poll()

        self.assertTrue(self.notice._popup_pending)
        self.assertEqual(self.handlers.count(self.notice._popup_handler), 1)

        self.notice._request_popup()

        self.assertEqual(self.handlers.count(self.notice._popup_handler), 1)

    def test_dialog_handler_shows_once_and_records_it(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()

        self.notice._popup_handler(None)

        self.assertEqual(self.ops_calls, [("INVOKE_DEFAULT",)])
        self.assertFalse(self.notice._popup_pending)
        self.assertTrue(self.notice._popup_shown)
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.assertTrue(self.read_state()["popup_shown"])

        self.notice._popup_handler(None)

        self.assertEqual(self.ops_calls, [("INVOKE_DEFAULT",)])

    def test_background_mode_does_not_arm_the_dialog_handler(self):
        self.bpy.app.background = True
        self.start_and_poll()
        self.write_manifest("0.1.11")

        self.notice._poll()

        self.assertTrue(self.notice._popup_pending)
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.assertFalse(self.read_state()["popup_shown"])

    def test_dialog_failure_keeps_the_notice_unshown(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()

        def boom(*_args):
            raise RuntimeError("no window")

        self.bpy.ops.blendmax.restart_notice_popup = boom

        self.notice._popup_handler(None)

        self.assertFalse(self.notice._popup_shown)
        self.assertFalse(self.read_state()["popup_shown"])
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.assertTrue(self.notice.restart_needed())

    def test_dismissed_dialog_is_not_reshown_on_reenable(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.notice._popup_handler(None)
        self.notice.unregister()

        self.notice.register()

        self.assertTrue(self.notice.restart_needed())
        self.assertFalse(self.notice._popup_pending)
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.assertTrue(self.read_state()["popup_shown"])

    def test_register_rearms_a_dialog_that_never_showed(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.assertFalse(self.read_state()["popup_shown"])
        self.notice.unregister()

        self.notice.register()

        self.assertTrue(self.notice.restart_needed())
        self.assertTrue(self.notice._popup_pending)
        self.assertIn(self.notice._popup_handler, self.handlers)

    def test_new_update_event_rearms_the_dialog(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.notice._popup_handler(None)

        self.write_manifest("0.1.12")
        self.notice._poll()

        self.assertTrue(self.notice._popup_pending)
        self.assertIn(self.notice._popup_handler, self.handlers)
        self.notice._popup_handler(None)
        self.assertEqual(len(self.ops_calls), 2)
        self.assertEqual(self.read_state()["installed_version"], "0.1.12")
        self.assertTrue(self.read_state()["popup_shown"])

    def test_matching_version_cancels_a_pending_dialog(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.assertTrue(self.notice._popup_pending)

        self.write_manifest("0.1.10")
        self.notice._poll()

        self.assertFalse(self.notice._popup_pending)
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.notice._popup_handler(None)
        self.assertEqual(self.ops_calls, [])
        self.assertFalse(self.read_state()["popup_shown"])

    def test_show_popup_invokes_the_operator_without_a_context_override(self):
        self.notice._show_popup()

        self.assertEqual(self.ops_calls, [("INVOKE_DEFAULT",)])

    def test_show_popup_rejects_an_invalid_call(self):
        self.bpy.ops.blendmax.restart_notice_popup = lambda *args: {"PASS_THROUGH"}

        with self.assertRaises(RuntimeError):
            self.notice._show_popup()

    def test_rejected_dialog_call_keeps_the_notice_unshown(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.bpy.ops.blendmax.restart_notice_popup = lambda *args: {"PASS_THROUGH"}

        self.notice._popup_handler(None)

        self.assertFalse(self.notice._popup_shown)
        self.assertFalse(self.read_state()["popup_shown"])
        self.assertNotIn(self.notice._popup_handler, self.handlers)
        self.assertTrue(self.notice.restart_needed())


if __name__ == "__main__":
    unittest.main()
