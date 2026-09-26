"""Fail closed on lock-path replacement in an isolated temporary directory.

All cooperating production participants must still never unlink or replace the
lock file.  No sequence of advisory-lock path checks can enforce that rule
against an uncooperative process replacing it after a lease was granted.
"""
import fcntl
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import publication_fence as fence


class InodeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "publication.lock"

    def tearDown(self):
        self.temp.cleanup()

    def lease(self, timeout=0.5):
        return fence.PublicationFence(
            timeout=timeout, poll_interval=0.005,
            lock_path=self.path, _test_only_path=True,
        )

    def test_replacement_during_flock_wait_is_rejected_and_registry_recovers(self):
        opened = threading.Event()
        outcome = []
        lock_fd = fence._lock_fd

        def announce_open(fd, deadline, interval):
            opened.set()
            return lock_fd(fd, deadline, interval)

        def waiter():
            try:
                with self.lease():
                    outcome.append("GRANTED_STALE_INODE")
            except fence.FencePathError:
                outcome.append("PATH_REJECTED")
            except BaseException as error:
                outcome.append(type(error).__name__)

        with open(self.path, "a+") as old_holder:
            fcntl.flock(old_holder.fileno(), fcntl.LOCK_EX)
            with patch.object(fence, "_lock_fd", announce_open):
                worker = threading.Thread(target=waiter)
                worker.start()
                self.assertTrue(opened.wait(0.25))
                old_inode = os.fstat(old_holder.fileno()).st_ino
                self.path.unlink()
                with open(self.path, "a+") as replacement_holder:
                    self.assertNotEqual(os.fstat(replacement_holder.fileno()).st_ino, old_inode)
                    fcntl.flock(replacement_holder.fileno(), fcntl.LOCK_EX)
                    fcntl.flock(old_holder.fileno(), fcntl.LOCK_UN)
                    worker.join(1.0)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(outcome, ["PATH_REJECTED"])
                    state = fence._states[os.fspath(self.path)]
                    self.assertIsNone(state.fd)
                    self.assertIsNone(state.owner_thread)
                    self.assertIsNone(state.acquiring_thread)
                    self.assertEqual(state.depth, 0)
                    fcntl.flock(replacement_holder.fileno(), fcntl.LOCK_UN)
        with self.lease(timeout=0.05):
            fence.require_publication_fence(lock_path=self.path)

    def test_reentrant_grant_rejects_replacement_without_incrementing_depth(self):
        with self.lease():
            self.path.unlink()
            self.path.touch()
            with self.assertRaisesRegex(fence.FencePathError, "PATH_CHANGED"):
                with self.lease():
                    self.fail("nested grant accepted a replaced lock path")
            self.assertEqual(fence._states[os.fspath(self.path)].depth, 1)
        with self.lease(timeout=0.05):
            fence.require_publication_fence(lock_path=self.path)

    def test_require_rejects_replaced_and_missing_lock_path(self):
        with self.lease():
            self.path.unlink()
            with self.assertRaisesRegex(fence.FencePathError, "PATH_CHANGED"):
                fence.require_publication_fence(lock_path=self.path)
            self.path.touch()
            with self.assertRaisesRegex(fence.FencePathError, "PATH_CHANGED"):
                fence.require_publication_fence(lock_path=self.path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
