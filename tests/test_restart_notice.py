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
                self.assertTrue(restart_notice.restart_notice_required(bpy))

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
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                self.assertTrue(restart_notice.restart_notice_required(bpy))

    def test_new_process_consumes_restart_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))

            with patch.object(restart_notice.os, "getpid", return_value=202):
                self.assertFalse(restart_notice.restart_notice_required(bpy))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertFalse(state.exists())

    def test_hot_reload_suppresses_notice_on_first_successful_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_pending(bpy)

                state = Path(directory) / "blendmax_restart_notice.json"
                self.assertEqual(
                    restart_notice._read_state(state),
                    {
                        "pending_pid": 101,
                        "hot_reload_pending_pid": 101,
                    },
                )

                self.assertFalse(restart_notice.restart_notice_required(bpy))
                self.assertFalse(state.exists())
                self.assertTrue(restart_notice.restart_notice_required(bpy))

    def test_failed_hot_reload_restores_pending_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_pending(bpy)
                restart_notice.mark_hot_reload_failed(bpy)
                self.assertTrue(restart_notice.restart_notice_required(bpy))

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(restart_notice._read_state(state), {"pending_pid": 101})

    def test_hot_reload_consumed_matches_current_process_only(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=1234):
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    False,
                )
                restart_notice.mark_hot_reload_consumed(bpy)
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    True,
                )

            with patch.object(restart_notice.os, "getpid", return_value=5678):
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    False,
                )

    def test_mark_hot_reload_consumed_preserves_restart_notice_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_consumed(bpy)

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {
                    "pending_pid": 101,
                    "hot_reload_consumed_pid": 101,
                },
            )

    def test_successful_hot_reload_notice_clear_preserves_consumed_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_consumed(bpy)
                restart_notice.mark_hot_reload_pending(bpy)
                self.assertFalse(restart_notice.restart_notice_required(bpy))
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    True,
                )

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {"hot_reload_consumed_pid": 101},
            )

    def test_failed_hot_reload_preserves_consumed_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_consumed(bpy)
                restart_notice.mark_hot_reload_pending(bpy)
                restart_notice.mark_hot_reload_failed(bpy)
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    True,
                )

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {
                    "pending_pid": 101,
                    "hot_reload_consumed_pid": 101,
                },
            )


if __name__ == "__main__":
    unittest.main()
