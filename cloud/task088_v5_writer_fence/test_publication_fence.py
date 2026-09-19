import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from publication_fence import (
    FenceError,
    FencePathError,
    FenceTimeout,
    PublicationFence,
    require_publication_fence,
)


def _child_try_lock(path, queue):
    try:
        with PublicationFence(timeout=0.15, poll_interval=0.01, lock_path=path, _test_only_path=True):
            queue.put("ACQUIRED")
    except FenceTimeout:
        queue.put("TIMEOUT")


class PublicationFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "publication.lock"

    def tearDown(self):
        self.temp.cleanup()

    def fence(self, **kwargs):
        return PublicationFence(lock_path=self.path, _test_only_path=True, **kwargs)

    def test_noncanonical_path_rejected_outside_tests(self):
        with self.assertRaisesRegex(FencePathError, "EXACT_PRODUCTION"):
            PublicationFence(lock_path=self.path)

    def test_same_thread_nesting_is_reentrant_and_requirement_is_scoped(self):
        with self.assertRaisesRegex(FenceError, "REQUIRED"):
            require_publication_fence(lock_path=self.path)
        with self.fence():
            require_publication_fence(lock_path=self.path)
            with self.fence():
                require_publication_fence(lock_path=self.path)
            require_publication_fence(lock_path=self.path)
        with self.assertRaisesRegex(FenceError, "REQUIRED"):
            require_publication_fence(lock_path=self.path)

    def test_exception_releases_fence(self):
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with self.fence():
                raise RuntimeError("injected")
        with self.fence(timeout=0.1):
            require_publication_fence(lock_path=self.path)

    def test_same_instance_cannot_be_entered_twice(self):
        fence = self.fence()
        with fence:
            with self.assertRaisesRegex(FenceError, "ALREADY_ENTERED"):
                fence.__enter__()

    def test_cross_thread_waits_until_outermost_release(self):
        entered = threading.Event()
        acquired = threading.Event()

        def worker():
            entered.set()
            with self.fence(timeout=1.0, poll_interval=0.01):
                acquired.set()

        with self.fence():
            with self.fence():
                thread = threading.Thread(target=worker)
                thread.start()
                self.assertTrue(entered.wait(0.2))
                time.sleep(0.05)
                self.assertFalse(acquired.is_set())
            self.assertFalse(acquired.is_set())
        thread.join(1.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(acquired.is_set())

    def test_cross_thread_timeout_does_not_break_owner(self):
        result = []

        def worker():
            try:
                with self.fence(timeout=0.05, poll_interval=0.01):
                    result.append("ACQUIRED")
            except FenceTimeout:
                result.append("TIMEOUT")

        with self.fence():
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(1.0)
            self.assertEqual(result, ["TIMEOUT"])
            require_publication_fence(lock_path=self.path)

    def test_cross_process_exclusion_uses_same_os_lock(self):
        context = multiprocessing.get_context("fork")
        queue = context.Queue()
        with self.fence():
            process = context.Process(target=_child_try_lock, args=(self.path, queue))
            process.start()
            process.join(2.0)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(queue.get(timeout=0.2), "TIMEOUT")
        process = context.Process(target=_child_try_lock, args=(self.path, queue))
        process.start()
        process.join(2.0)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(queue.get(timeout=0.2), "ACQUIRED")

    def test_symlink_lock_is_rejected_without_touching_target(self):
        target = Path(self.temp.name) / "target"
        target.write_text("unchanged", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises((FencePathError, OSError)):
            with self.fence():
                pass
        self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_relative_test_path_is_rejected_before_creation(self):
        with self.assertRaisesRegex(FencePathError, "ABSOLUTE_PATH"):
            with PublicationFence(lock_path="relative.lock", _test_only_path=True):
                pass

    def test_lock_file_is_regular_and_not_unlinked_after_release(self):
        with self.fence():
            self.assertTrue(self.path.is_file())
        inode = os.stat(self.path, follow_symlinks=False).st_ino
        with self.fence():
            self.assertEqual(os.stat(self.path, follow_symlinks=False).st_ino, inode)

    def test_invalid_timeout_and_poll_fail_before_effect(self):
        with self.assertRaises(ValueError):
            self.fence(timeout=-1)
        with self.assertRaises(ValueError):
            self.fence(poll_interval=0)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
