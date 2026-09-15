from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
                    "hot_reload_consumed_pids": [101],
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
                {"hot_reload_consumed_pids": [101]},
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
                    "hot_reload_consumed_pids": [101],
                },
            )

    def test_new_process_restart_notice_preserves_other_consumed_pids(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertTrue(restart_notice.restart_notice_required(bpy))
                restart_notice.mark_hot_reload_consumed(bpy)

            with patch.object(restart_notice, "_pid_is_alive", return_value=True):
                with patch.object(restart_notice.os, "getpid", return_value=202):
                    self.assertFalse(restart_notice.restart_notice_required(bpy))
                    self.assertIs(
                        restart_notice.hot_reload_consumed_for_current_process(bpy),
                        False,
                    )

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {"hot_reload_consumed_pids": [101]},
            )

    def test_concurrent_blender_processes_keep_independent_consumed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice, "_pid_is_alive", return_value=True):
                with patch.object(restart_notice.os, "getpid", return_value=101):
                    restart_notice.mark_hot_reload_consumed(bpy)
                with patch.object(restart_notice.os, "getpid", return_value=202):
                    restart_notice.mark_hot_reload_consumed(bpy)
                    self.assertIs(
                        restart_notice.hot_reload_consumed_for_current_process(bpy),
                        True,
                    )
                with patch.object(restart_notice.os, "getpid", return_value=101):
                    self.assertIs(
                        restart_notice.hot_reload_consumed_for_current_process(bpy),
                        True,
                    )

            state = Path(directory) / "blendmax_restart_notice.json"
            self.assertEqual(
                restart_notice._read_state(state),
                {"hot_reload_consumed_pids": [101, 202]},
            )

    def test_legacy_scalar_consumed_pid_is_honored(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            state = Path(directory) / "blendmax_restart_notice.json"
            restart_notice._write_state(state, {"hot_reload_consumed_pid": 101})
            with patch.object(restart_notice.os, "getpid", return_value=101):
                self.assertIs(
                    restart_notice.hot_reload_consumed_for_current_process(bpy),
                    True,
                )
                restart_notice.mark_hot_reload_consumed(bpy)
            self.assertEqual(
                restart_notice._read_state(state),
                {"hot_reload_consumed_pids": [101]},
            )

    def test_unmark_hot_reload_consumed_removes_only_current_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy = FakeBpy(directory)
            with patch.object(restart_notice, "_pid_is_alive", return_value=True):
                with patch.object(restart_notice.os, "getpid", return_value=101):
                    restart_notice.mark_hot_reload_consumed(bpy)
                with patch.object(restart_notice.os, "getpid", return_value=202):
                    restart_notice.mark_hot_reload_consumed(bpy)
                    restart_notice.unmark_hot_reload_consumed(bpy)
                    self.assertIs(
                        restart_notice.hot_reload_consumed_for_current_process(bpy),
                        False,
                    )
                with patch.object(restart_notice.os, "getpid", return_value=101):
                    self.assertIs(
                        restart_notice.hot_reload_consumed_for_current_process(bpy),
                        True,
                    )


class FakeKernel32:
    """Stand-in for kernel32 with the three calls the probe makes.

    Attributes are ``MagicMock``s so the ctypes ``argtypes``/``restype``
    assignments the probe performs are accepted. Models the Win32 contract the
    real API guarantees: OpenProcess returns a handle or NULL (with
    GetLastError set); WaitForSingleObject returns WAIT_OBJECT_0 once the
    process object is signaled (process terminated) and WAIT_TIMEOUT while it
    is still running.
    """

    def __init__(self, handle, *, wait_result=0x00000102, last_error=0):
        self._handle = handle
        self._wait_result = wait_result
        self.last_error = last_error
        self.opened_with = []
        self.closed = []
        self.waited = []

        self.OpenProcess = MagicMock(side_effect=self._open_process)
        self.CloseHandle = MagicMock(side_effect=self._close_handle)
        self.WaitForSingleObject = MagicMock(side_effect=self._wait)

    def _open_process(self, access, inherit, pid):
        self.opened_with.append((access, inherit, pid))
        return self._handle

    def _close_handle(self, handle):
        self.closed.append(handle)
        return 1

    def _wait(self, handle, timeout):
        self.waited.append((handle, timeout))
        return self._wait_result


class WindowsPidLivenessTests(unittest.TestCase):
    """The Windows path must never reach a process-terminating API."""

    def _probe(self, kernel32, pid=4242):
        with patch.object(restart_notice, "_IS_WINDOWS", True):
            with patch("ctypes.WinDLL", return_value=kernel32, create=True):
                with patch(
                    "ctypes.get_last_error",
                    return_value=kernel32.last_error,
                    create=True,
                ):
                    return restart_notice._windows_pid_is_alive(pid)

    def test_live_process_is_alive(self):
        """WAIT_TIMEOUT means the process object is not signaled: still running."""
        kernel32 = FakeKernel32(handle=123, wait_result=restart_notice._WAIT_TIMEOUT)
        self.assertIs(self._probe(kernel32), True)
        self.assertEqual(kernel32.waited, [(123, 0)])
        self.assertEqual(kernel32.closed, [123])

    def test_exited_process_is_dead(self):
        kernel32 = FakeKernel32(handle=123, wait_result=restart_notice._WAIT_OBJECT_0)
        self.assertIs(self._probe(kernel32), False)

    def test_terminated_process_that_exited_with_259_is_dead(self):
        """Regression: exit code 259 must not be mistaken for STILL_ACTIVE.

        GetExitCodeProcess returns 259 both for a running process and for one
        that exited with status 259, so liveness is read from the wait state.
        A process that exited with 259 is signaled, hence WAIT_OBJECT_0.
        """
        kernel32 = FakeKernel32(handle=123, wait_result=restart_notice._WAIT_OBJECT_0)
        self.assertIs(self._probe(kernel32), False)

    def test_unexpected_wait_result_is_dead(self):
        """Anything that is neither signaled nor timed out stays conservative."""
        kernel32 = FakeKernel32(handle=123, wait_result=0xFFFFFFFF)  # WAIT_FAILED
        self.assertIs(self._probe(kernel32), False)
        self.assertEqual(kernel32.closed, [123])

    def test_nonexistent_process_is_dead(self):
        kernel32 = FakeKernel32(
            handle=0, last_error=restart_notice._ERROR_INVALID_PARAMETER
        )
        self.assertIs(self._probe(kernel32), False)
        self.assertEqual(kernel32.closed, [])

    def test_access_denied_process_still_counts_as_alive(self):
        kernel32 = FakeKernel32(handle=0, last_error=restart_notice._ERROR_ACCESS_DENIED)
        self.assertIs(self._probe(kernel32), True)

    def test_probe_requests_query_and_wait_access_only(self):
        """Regression: PROCESS_TERMINATE must never be requested."""
        kernel32 = FakeKernel32(handle=123)
        self._probe(kernel32)
        access = kernel32.opened_with[0][0]
        self.assertTrue(access & restart_notice._PROCESS_QUERY_LIMITED_INFORMATION)
        self.assertTrue(access & restart_notice._SYNCHRONIZE)
        self.assertFalse(access & 0x0001, "PROCESS_TERMINATE bit must be clear")

    def test_windows_path_does_not_call_os_kill(self):
        """Regression: the Windows branch never touches os.kill."""
        kernel32 = FakeKernel32(handle=123, wait_result=restart_notice._WAIT_TIMEOUT)
        with patch.object(restart_notice, "_IS_WINDOWS", True):
            with patch("ctypes.WinDLL", return_value=kernel32, create=True):
                with patch.object(
                    restart_notice.os, "kill", side_effect=AssertionError("os.kill called")
                ) as kill:
                    self.assertIs(restart_notice._pid_is_alive(4242), True)
                    kill.assert_not_called()

    def test_invalid_pid_short_circuits_before_any_os_call(self):
        with patch.object(restart_notice, "_IS_WINDOWS", True):
            with patch.object(
                restart_notice, "_windows_pid_is_alive", side_effect=AssertionError("probe ran")
            ) as probe:
                self.assertIs(restart_notice._pid_is_alive(0), False)
                self.assertIs(restart_notice._pid_is_alive(-1), False)
                self.assertIs(restart_notice._pid_is_alive("4242"), False)
                probe.assert_not_called()


class PosixPidLivenessTests(unittest.TestCase):
    """The POSIX branch keeps its original os.kill semantics."""

    def _posix_probe(self, pid, kill_side_effect):
        with patch.object(restart_notice, "_IS_WINDOWS", False):
            with patch.object(restart_notice.os, "kill", side_effect=kill_side_effect) as k:
                return restart_notice._pid_is_alive(pid), k

    def test_live_process_is_alive(self):
        result, kill = self._posix_probe(4242, None)
        self.assertIs(result, True)
        kill.assert_called_once_with(4242, 0)

    def test_missing_process_is_dead(self):
        result, _ = self._posix_probe(4242, ProcessLookupError())
        self.assertIs(result, False)

    def test_permission_error_counts_as_alive(self):
        result, _ = self._posix_probe(4242, PermissionError())
        self.assertIs(result, True)

    def test_unexpected_os_error_is_dead(self):
        result, _ = self._posix_probe(4242, OSError("boom"))
        self.assertIs(result, False)

    def test_posix_branch_does_not_use_the_windows_probe(self):
        with patch.object(restart_notice, "_IS_WINDOWS", False):
            with patch.object(
                restart_notice, "_windows_pid_is_alive", side_effect=AssertionError("windows probe ran")
            ) as probe:
                with patch.object(restart_notice.os, "kill", return_value=None):
                    self.assertIs(restart_notice._pid_is_alive(4242), True)
                probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
