from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blendmax_blender import restart_notice


class FakeUtils:
    def __init__(self, directory):
        self.directory = str(directory)

    def user_resource(self, resource_type, *, path="", create=False):
        self.last_call = (resource_type, path, create)
        return self.directory


class FakeBpy:
    def __init__(self, directory):
        self.utils = FakeUtils(directory)


class RestartNoticeTests(unittest.TestCase):
    def test_first_registration_requires_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertTrue(state.exists())
            self.assertEqual(
                restart_notice._read_state(state),
                {"pending_pid": 101},
            )

    def test_same_process_keeps_restart_notice_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))

    def test_new_process_consumes_restart_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))

            with patch.object(restart_notice.os, "getpid", return_value=202):
                self.assertFalse(restart_notice.restart_notice_required(bpy, "0.1.8"))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertFalse(state.exists())

    def test_hot_reload_suppresses_notice_for_current_process_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))
                restart_notice.mark_hot_reload_complete(bpy, "0.1.8")
                self.assertFalse(restart_notice.restart_notice_required(bpy, "0.1.8"))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {
                    "pending_pid": 101,
                    "hot_reload_pid": 101,
                    "hot_reload_version": "0.1.8",
                },
            )

            with patch.object(restart_notice.os, "getpid", return_value=202):
                self.assertFalse(restart_notice.restart_notice_required(bpy, "0.1.8"))

            self.assertFalse(state.exists())

    def test_new_version_does_not_inherit_hot_reload_suppression(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))
                restart_notice.mark_hot_reload_complete(bpy, "0.1.8")
                self.assertFalse(restart_notice.restart_notice_required(bpy, "0.1.8"))
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.9"))

    def test_failed_hot_reload_restores_pending_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))
                restart_notice.mark_hot_reload_complete(bpy, "0.1.8")
                self.assertFalse(restart_notice.restart_notice_required(bpy, "0.1.8"))
                restart_notice.mark_hot_reload_failed(bpy)
                self.assertTrue(restart_notice.restart_notice_required(bpy, "0.1.8"))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(restart_notice._read_state(state), {"pending_pid": 101})


if __name__ == "__main__":
    unittest.main()
