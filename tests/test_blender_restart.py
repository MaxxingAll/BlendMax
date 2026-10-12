from __future__ import annotations

import os
import subprocess
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from tests.fakes import load_blender_module
from tests.test_blender_addon_summary import load_addon


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.reports = []
        self.save_result = {"FINISHED"}
        self.bpy = ModuleType("bpy")
        self.bpy.app = SimpleNamespace(binary_path="/opt/blender/blender")
        self.bpy.data = SimpleNamespace(filepath="", is_dirty=False)
        self.bpy.ops = SimpleNamespace(
            wm=SimpleNamespace(
                quit_blender=self.quit_blender,
                save_mainfile=self.save_mainfile,
            )
        )
        self.restart = load_blender_module(
            "restart.py", vector=object, bpy=self.bpy
        )
        self.windows = False
        patcher = patch.object(
            self.restart, "_is_windows", side_effect=lambda: self.windows
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.popen_error = None
        popen = patch.object(subprocess, "Popen", side_effect=self.popen)
        self.popen_mock = popen.start()
        self.addCleanup(popen.stop)

    def popen(self, command, **kwargs):
        if self.popen_error is not None:
            raise self.popen_error
        self.events.append("spawn")
        return SimpleNamespace()

    def quit_blender(self, *args):
        self.events.append("quit")
        return {"FINISHED"}

    def save_mainfile(self):
        self.events.append("save")
        if isinstance(self.save_result, Exception):
            raise self.save_result
        return self.save_result

    def report(self, levels, message):
        self.reports.append((levels, message))

    def run_restart(self, action=None):
        if action is None:
            return self.restart.restart_blender(self.report)
        return self.restart.restart_blender(self.report, action)

    def test_command_is_binary_path_for_untitled_file(self):
        self.assertEqual(self.restart.build_command(), ["/opt/blender/blender"])

    def test_command_reopens_saved_file(self):
        self.bpy.data.filepath = "/work/scene.blend"
        self.assertEqual(
            self.restart.build_command(),
            ["/opt/blender/blender", "/work/scene.blend"],
        )

    def test_command_never_forwards_sys_argv(self):
        with patch("sys.argv", ["blender", "-b", "--python", "x.py"]):
            self.assertEqual(
                self.restart.build_command(), ["/opt/blender/blender"]
            )

    def test_windows_prefers_blender_launcher_when_present(self):
        self.windows = True
        self.bpy.app.binary_path = os.path.join("C:", "Blender", "blender.exe")
        launcher = os.path.join("C:", "Blender", "blender-launcher.exe")
        with patch("os.path.isfile", side_effect=lambda path: path == launcher):
            self.assertEqual(self.restart.build_command(), [launcher])
        with patch("os.path.isfile", return_value=False):
            self.assertEqual(
                self.restart.build_command(), [self.bpy.app.binary_path]
            )

    def test_launcher_is_ignored_off_windows(self):
        with patch("os.path.isfile", return_value=True):
            self.assertEqual(
                self.restart.build_command(), ["/opt/blender/blender"]
            )

    def test_popen_flags_on_posix(self):
        self.run_restart()
        args, kwargs = self.popen_mock.call_args
        self.assertEqual(args[0], ["/opt/blender/blender"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertNotIn("creationflags", kwargs)
        self.assertTrue(kwargs["close_fds"])
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(kwargs[stream], subprocess.DEVNULL)
        self.assertEqual(kwargs["cwd"], os.path.dirname("/opt/blender/blender"))

    def test_popen_flags_on_windows(self):
        self.windows = True
        self.bpy.app.binary_path = os.path.join("C:", "Blender", "blender.exe")
        with patch("os.path.isfile", return_value=False):
            self.run_restart()
        _args, kwargs = self.popen_mock.call_args
        self.assertEqual(kwargs["creationflags"], 0x00000008 | 0x00000200)
        self.assertNotIn("start_new_session", kwargs)
        self.assertEqual(kwargs["cwd"], os.path.join("C:", "Blender"))

    def test_spawn_happens_before_quit(self):
        self.assertEqual(self.run_restart(), {"FINISHED"})
        self.assertEqual(self.events, ["spawn", "quit"])
        self.assertEqual(self.reports, [])

    def test_popen_failure_does_not_quit(self):
        self.popen_error = OSError("boom")
        self.assertEqual(self.run_restart(), {"CANCELLED"})
        self.assertEqual(self.events, [])
        self.assertEqual(self.reports[0][0], {"ERROR"})
        self.assertIn("Could not start a new Blender: boom", self.reports[0][1])
        self.assertIn("quit and reopen Blender manually", self.reports[0][1])

    def test_empty_binary_path_does_not_spawn_or_quit(self):
        self.bpy.app.binary_path = ""
        self.assertEqual(self.run_restart(), {"CANCELLED"})
        self.assertEqual(self.events, [])
        self.popen_mock.assert_not_called()
        self.assertEqual(self.reports[0][0], {"ERROR"})

    def test_dirty_save_untitled_cancels_without_spawn_or_quit(self):
        self.bpy.data.is_dirty = True
        self.assertEqual(self.run_restart("SAVE"), {"CANCELLED"})
        self.assertEqual(self.events, [])
        self.assertEqual(
            self.reports,
            [({"ERROR"}, "Save the file first (File > Save As), then restart.")],
        )

    def test_dirty_save_saved_file_saves_then_spawns_then_quits(self):
        self.bpy.data.is_dirty = True
        self.bpy.data.filepath = "/work/scene.blend"
        self.assertEqual(self.run_restart("SAVE"), {"FINISHED"})
        self.assertEqual(self.events, ["save", "spawn", "quit"])

    def test_failed_save_does_not_spawn_or_quit(self):
        self.bpy.data.is_dirty = True
        self.bpy.data.filepath = "/work/scene.blend"
        self.save_result = {"CANCELLED"}
        self.assertEqual(self.run_restart("SAVE"), {"CANCELLED"})
        self.assertEqual(self.events, ["save"])
        self.assertEqual(self.reports[0][0], {"ERROR"})

    def test_save_error_does_not_spawn_or_quit(self):
        # Blender raises RuntimeError when the save operator reports an
        # error, for example on a read-only file.
        self.bpy.data.is_dirty = True
        self.bpy.data.filepath = "/work/scene.blend"
        self.save_result = RuntimeError("Error: Cannot open file for writing")
        self.assertEqual(self.run_restart("SAVE"), {"CANCELLED"})
        self.assertEqual(self.events, ["save"])
        self.assertEqual(self.reports[0][0], {"ERROR"})

    def test_dirty_discard_spawns_and_quits_without_saving(self):
        self.bpy.data.is_dirty = True
        self.bpy.data.filepath = "/work/scene.blend"
        self.assertEqual(self.run_restart("DISCARD"), {"FINISHED"})
        self.assertEqual(self.events, ["spawn", "quit"])

    def test_clean_file_never_saves(self):
        self.bpy.data.filepath = "/work/scene.blend"
        self.run_restart("SAVE")
        self.assertEqual(self.events, ["spawn", "quit"])


class RestartOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addon = load_addon("blendmax_blender._addon_restart_test")

    def make_operator(self, dirty):
        operator = self.addon.BLENDMAX_OT_restart_blender()
        operator.unsaved_action = "SAVE"
        operator.report = lambda *_args: None
        calls = []
        fake_restart = SimpleNamespace(
            SAVE="SAVE",
            DISCARD="DISCARD",
            is_dirty=lambda: dirty,
            restart_blender=lambda report, action: (
                calls.append(action) or {"FINISHED"}
            ),
        )
        patcher = patch.object(self.addon, "restart", fake_restart)
        patcher.start()
        self.addCleanup(patcher.stop)
        return operator, calls

    def test_identity_and_registration(self):
        operator_class = self.addon.BLENDMAX_OT_restart_blender
        self.assertEqual(operator_class.bl_idname, "blendmax.restart_blender")
        self.assertEqual(operator_class.bl_label, "Restart Blender")
        self.assertIn(operator_class, self.addon._CLASSES)

    def test_poll_is_false_in_background(self):
        operator_class = self.addon.BLENDMAX_OT_restart_blender
        with patch.object(
            self.addon.bpy, "app", SimpleNamespace(background=True), create=True
        ):
            self.assertFalse(operator_class.poll(None))
        with patch.object(
            self.addon.bpy, "app", SimpleNamespace(background=False), create=True
        ):
            self.assertTrue(operator_class.poll(None))

    def test_invoke_asks_when_dirty(self):
        operator, calls = self.make_operator(dirty=True)
        shown = []
        context = SimpleNamespace(
            window_manager=SimpleNamespace(
                invoke_props_dialog=lambda op, **kwargs: shown.append((op, kwargs))
                or {"RUNNING_MODAL"}
            )
        )
        self.assertEqual(operator.invoke(context, None), {"RUNNING_MODAL"})
        self.assertEqual(shown, [(operator, {"confirm_text": "Restart Blender"})])
        self.assertEqual(calls, [])

    def test_invoke_executes_directly_when_clean(self):
        operator, calls = self.make_operator(dirty=False)
        self.assertEqual(operator.invoke(SimpleNamespace(), None), {"FINISHED"})
        self.assertEqual(calls, ["SAVE"])


if __name__ == "__main__":
    unittest.main()
