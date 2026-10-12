"""Tests for tools/blender_headless.py; Blender itself is never launched."""

from __future__ import annotations

import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from tools import blender_headless


class FindBlenderTests(unittest.TestCase):
    def test_explicit_path_wins_over_environment(self):
        self.assertEqual(
            blender_headless.find_blender("C:/b/blender.exe", {"BLENDER": "other"}),
            "C:/b/blender.exe",
        )

    def test_environment_variable_is_used_without_explicit_path(self):
        self.assertEqual(
            blender_headless.find_blender(None, {"BLENDER": "/opt/blender"}),
            "/opt/blender",
        )

    def test_missing_blender_raises(self):
        with mock.patch.object(blender_headless.os, "name", "posix"), mock.patch.object(
            blender_headless.shutil, "which", return_value=None
        ):
            with self.assertRaises(FileNotFoundError):
                blender_headless.find_blender(None, {})


class CommandAndEnvironmentTests(unittest.TestCase):
    def test_background_flag_is_added_once(self):
        self.assertEqual(
            blender_headless.headless_command(
                "blender", ["-b", "--python", "x.py", "--background"]
            ),
            ["blender", "-b", "--python", "x.py"],
        )

    def test_environment_points_user_scripts_at_empty_folder(self):
        environment = blender_headless.headless_environment(
            "/tmp/empty", {"PATH": "/bin", "BLENDER_USER_SCRIPTS": "/real"}
        )
        self.assertEqual(environment["BLENDER_USER_SCRIPTS"], "/tmp/empty")
        self.assertEqual(environment["PATH"], "/bin")

    def test_environment_does_not_touch_config_or_extensions(self):
        environment = blender_headless.headless_environment("/tmp/empty", {})
        self.assertNotIn("BLENDER_USER_CONFIG", environment)
        self.assertNotIn("BLENDER_USER_EXTENSIONS", environment)


class RunTests(unittest.TestCase):
    def test_run_uses_an_existing_empty_scripts_folder(self):
        seen = {}

        def fake_run(command, env, timeout):
            folder = env["BLENDER_USER_SCRIPTS"]
            seen["exists"] = os.path.isdir(folder)
            seen["empty"] = os.path.isdir(folder) and not os.listdir(folder)
            seen["folder"] = folder
            seen["command"] = command
            seen["timeout"] = timeout
            return SimpleNamespace(returncode=0)

        with mock.patch.object(blender_headless.subprocess, "run", side_effect=fake_run):
            code = blender_headless.run(["--python", "x.py"], blender="blender", timeout=30)

        self.assertEqual(code, 0)
        self.assertTrue(seen["exists"])
        self.assertTrue(seen["empty"])
        self.assertFalse(os.path.exists(seen["folder"]))
        self.assertEqual(seen["command"], ["blender", "-b", "--python", "x.py"])
        self.assertEqual(seen["timeout"], 30)

    def test_main_passes_arguments_after_separator(self):
        with mock.patch.object(blender_headless, "run", return_value=7) as run:
            code = blender_headless.main(
                ["--blender", "blender", "--", "--python-expr", "print(1)"]
            )
        self.assertEqual(code, 7)
        run.assert_called_once_with(
            ["--python-expr", "print(1)"], blender="blender", timeout=None
        )

    def test_main_reports_timeout(self):
        error = subprocess.TimeoutExpired(cmd="blender", timeout=5)
        with mock.patch.object(blender_headless, "run", side_effect=error):
            with mock.patch("sys.stderr"):
                code = blender_headless.main(["--timeout", "5", "--", "-b"])
        self.assertEqual(code, 124)

    def test_main_reports_missing_blender(self):
        with mock.patch.object(
            blender_headless, "run", side_effect=FileNotFoundError("missing")
        ):
            with mock.patch("sys.stderr"):
                self.assertEqual(blender_headless.main([]), 2)


if __name__ == "__main__":
    unittest.main()
