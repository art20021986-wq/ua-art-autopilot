"""Focused regressions for the isolated candidate's fork descriptor lifecycle.

No production source, lock, database, or HTML path is accessed.
"""
import errno
import os
from pathlib import Path
import signal
import tempfile
import threading
import time
import unittest
import warnings
from unittest.mock import patch

import publication_fence as fence


def fork_for_test():
    # The behavior under review is explicitly a fork from a threaded process.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return os.fork()


class ForkRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "publication.lock"

    def tearDown(self):
        self.temp.cleanup()

    def lease(self, timeout=0.1):
        return fence.PublicationFence(
            timeout=timeout, poll_interval=0.005,
            lock_path=self.path, _test_only_path=True,
        )

    def wait_child(self, pid, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            completed, status = os.waitpid(pid, os.WNOHANG)
            if completed:
                self.assertTrue(os.WIFEXITED(status), status)
                self.assertEqual(os.WEXITSTATUS(status), 0)
                return
            time.sleep(0.005)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        self.fail("child blocked beyond its bounded fence timeout")

    def assert_child_fd_closed(self, fd):
        try:
            os.fstat(fd)
        except OSError as error:
            if error.errno == errno.EBADF:
                return
        raise AssertionError("child retained an inherited fence descriptor")

    def test_fork_while_another_thread_holds_condition(self):
        held = threading.Event()
        release = threading.Event()

        def holder():
            with fence._condition:
                held.set()
                release.wait(1.0)

        worker = threading.Thread(target=holder)
        worker.start()
        self.assertTrue(held.wait(0.5))
        timer = threading.Timer(0.05, release.set)
        timer.start()
        pid = fork_for_test()
        if pid == 0:
            try:
                with self.lease(timeout=0.05):
                    fence.require_publication_fence(lock_path=self.path)
            except BaseException:
                os._exit(1)
            os._exit(0)
        try:
            self.wait_child(pid)
        finally:
            release.set()
            timer.join(0.5)
            worker.join(0.5)
        self.assertFalse(worker.is_alive())

    def test_open_descriptor_window_is_serialized_with_fork(self):
        opened = threading.Event()
        permit_return = threading.Event()
        permit_exit = threading.Event()
        descriptors = []
        errors = []
        safe_open = fence._safe_open

        def pause_after_open(path):
            fd = safe_open(path)
            descriptors.append(fd)
            opened.set()
            if not permit_return.wait(1.0):
                raise AssertionError("test did not release open window")
            return fd

        def owner():
            try:
                with self.lease():
                    permit_exit.wait(1.0)
            except BaseException as error:
                errors.append(error)

        with patch.object(fence, "_safe_open", pause_after_open):
            worker = threading.Thread(target=owner)
            worker.start()
            self.assertTrue(opened.wait(0.5))
            timer = threading.Timer(0.05, permit_return.set)
            timer.start()
            pid = fork_for_test()
            if pid == 0:
                try:
                    self.assert_child_fd_closed(descriptors[0])
                    self.assertEqual(fence._states, {})
                except BaseException:
                    os._exit(1)
                os._exit(0)
            try:
                self.wait_child(pid)
            finally:
                permit_return.set()
                permit_exit.set()
                timer.join(0.5)
                worker.join(0.5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_acquired_but_unpublished_descriptor_is_closed_without_unlocking_parent(self):
        acquired = threading.Event()
        publish_owner = threading.Event()
        descriptors = []
        errors = []
        lock_fd = fence._lock_fd

        def pause_after_flock(fd, deadline, interval):
            lock_fd(fd, deadline, interval)
            descriptors.append(fd)
            acquired.set()
            if not publish_owner.wait(1.0):
                raise AssertionError("test did not release acquisition window")

        def owner():
            try:
                with self.lease():
                    pass
            except BaseException as error:
                errors.append(error)

        with patch.object(fence, "_lock_fd", pause_after_flock):
            worker = threading.Thread(target=owner)
            worker.start()
            self.assertTrue(acquired.wait(0.5))
            pid = fork_for_test()
            if pid == 0:
                try:
                    fence._lock_fd = lock_fd
                    self.assert_child_fd_closed(descriptors[0])
                    self.assertEqual(fence._states, {})
                    try:
                        with self.lease(timeout=0.05):
                            raise AssertionError("child revoked parent's flock")
                    except fence.FenceTimeout:
                        pass
                except BaseException:
                    os._exit(1)
                os._exit(0)
            try:
                self.wait_child(pid)
            finally:
                publish_owner.set()
                worker.join(0.5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        with self.lease(timeout=0.05):
            fence.require_publication_fence(lock_path=self.path)

    def test_owned_parent_lease_is_not_retained_by_child_without_helper_calls(self):
        with self.lease():
            owned_fd = fence._states[os.fspath(self.path)].fd
            pid = fork_for_test()
            if pid == 0:
                try:
                    # Check before calling any fence API: cleanup must be eager.
                    self.assert_child_fd_closed(owned_fd)
                    self.assertEqual(fence._states, {})
                except BaseException:
                    os._exit(1)
                os._exit(0)
            self.wait_child(pid)
            fence.require_publication_fence(lock_path=self.path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
