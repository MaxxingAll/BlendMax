from __future__ import annotations

import importlib.util
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
        self.bpy = ModuleType("bpy")
        self.bpy.app = SimpleNamespace(
            driver_namespace={},
            timers=self.timers,
        )
        self.bpy.context = SimpleNamespace(
            window_manager=SimpleNamespace(windows=[]),
        )
        self.notice = self.load_notice("blendmax_blender._restart_notice_test")
        self.notice._MANIFEST = self.manifest

    def tearDown(self):
        if self.notice is not None:
            self.notice.unregister()
        self.tempdir.cleanup()

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

    def test_new_disk_version_requires_restart(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")

        self.notice._poll()

        self.assertEqual(self.notice.running_version(), "0.1.10")
        self.assertEqual(self.notice.disk_version(), "0.1.11")
        self.assertTrue(self.notice.restart_needed())

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

    def test_simulated_blender_restart_captures_current_disk_version(self):
        self.start_and_poll()
        self.write_manifest("0.1.11")
        self.notice._poll()
        self.notice.unregister()
        self.bpy.app.driver_namespace.clear()

        restarted = self.load_notice("blendmax_blender._restart_notice_fresh")
        restarted._MANIFEST = self.manifest
        restarted.register()
        restarted._poll()

        self.assertEqual(restarted.running_version(), "0.1.11")
        self.assertEqual(restarted.disk_version(), "0.1.11")
        self.assertFalse(restarted.restart_needed())
        restarted.unregister()

    def test_unregister_removes_timer(self):
        self.notice.register()
        self.assertTrue(self.timers.is_registered(self.notice._poll))

        self.notice.unregister()

        self.assertFalse(self.timers.is_registered(self.notice._poll))

    def test_timer_registration_is_idempotent(self):
        self.notice.register()
        self.notice.register()

        self.assertEqual(self.timers.register_calls, 1)
        self.assertEqual(len(self.timers.callbacks), 1)

    def test_draw_uses_cached_versions_without_reading_manifest(self):
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


if __name__ == "__main__":
    unittest.main()
