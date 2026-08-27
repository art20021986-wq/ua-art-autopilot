"""
test_crm_speed_gate_a.py

Behavioral test suite for the corrected CRM-SPEED-001 package. These are
offline tests against synthetic fixtures and independent subprocesses;
none of them import, execute, or modify any real /home/Carix file.

This suite is authored by Claude for independent controller execution.
Claude does not claim to have executed this suite on PythonAnywhere or in
production; execution and pass/fail evidence must be produced by the
controller per the AUTOPILOT protocol (see cloud_report_020.md).
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from cross_process_lock import CrossProcessLock  # noqa: E402
from singleton_guard import DUPLICATE_START_EXIT_CODE  # noqa: E402
from rebuild_queue import find_stranica_generation_anchors  # noqa: E402
from sqlite_ownership import (  # noqa: E402
    transform_short_ownership, verify_no_live_handle_across_slow_call, _iter_functions,
    AnchorNotFoundError as SqliteAnchorError,
)
from media_call_graph import find_reachable_media_calls  # noqa: E402
from ua0009_publication_check import check_ua0009_not_public  # noqa: E402
import ua0009_publication_check as ua0009_mod  # noqa: E402
from safe_writer import SafeWriter, UnsafePathError, InsufficientSpaceError  # noqa: E402


def run_subprocess_snippet(code: str, timeout=10):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           timeout=timeout)


class CrossProcessLockTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.tmpdir, "test.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_two_independent_processes_one_wins(self):
        snippet = textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {_HERE!r})
            from cross_process_lock import CrossProcessLock
            lock = CrossProcessLock({self.lock_path!r}, label='t')
            ok = lock.try_acquire()
            print(ok)
            if ok:
                time.sleep(1.5)
        """)
        p1 = subprocess.Popen([sys.executable, "-c", snippet], stdout=subprocess.PIPE, text=True)
        time.sleep(0.3)
        p2 = run_subprocess_snippet(textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {_HERE!r})
            from cross_process_lock import CrossProcessLock
            lock = CrossProcessLock({self.lock_path!r}, label='t')
            print(lock.try_acquire())
        """))
        out1, _ = p1.communicate(timeout=5)
        self.assertIn("True", out1)
        self.assertIn("False", p2.stdout)

    def test_stale_dead_pid_takeover(self):
        lock = CrossProcessLock(self.lock_path, label="t")
        fake_payload = {"pid": 999999, "start_time": 123, "token": "deadbeef",
                         "created_at": time.time(), "label": "t"}
        with open(self.lock_path, "w") as fh:
            json.dump(fake_payload, fh)
        self.assertTrue(lock.try_acquire())

    def test_foreign_token_release_denied(self):
        lock = CrossProcessLock(self.lock_path, label="t")
        self.assertTrue(lock.try_acquire())
        lock.token = "not-the-real-token"
        self.assertFalse(lock.release())

    def test_clean_release_and_reacquire(self):
        lock = CrossProcessLock(self.lock_path, label="t")
        self.assertTrue(lock.try_acquire())
        self.assertTrue(lock.release())
        lock2 = CrossProcessLock(self.lock_path, label="t")
        self.assertTrue(lock2.try_acquire())

    def test_exception_path_still_releases_via_context_manager(self):
        lock = CrossProcessLock(self.lock_path, label="t")
        try:
            with lock:
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        lock2 = CrossProcessLock(self.lock_path, label="t")
        self.assertTrue(lock2.try_acquire())

    def test_simultaneous_stale_takeover_only_one_wins(self):
        fake_payload = {"pid": 999998, "start_time": 1, "token": "old",
                         "created_at": time.time(), "label": "t"}
        with open(self.lock_path, "w") as fh:
            json.dump(fake_payload, fh)
        snippet = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {_HERE!r})
            from cross_process_lock import CrossProcessLock
            lock = CrossProcessLock({self.lock_path!r}, label='t')
            print(lock.try_acquire())
        """)
        procs = [subprocess.Popen([sys.executable, "-c", snippet],
                                   stdout=subprocess.PIPE, text=True) for _ in range(4)]
        outs = [p.communicate(timeout=5)[0] for p in procs]
        trues = sum(1 for o in outs if "True" in o)
        self.assertEqual(trues, 1)


class SingletonGuardTests(unittest.TestCase):
    def test_duplicate_start_exits_nonzero(self):
        tmpdir = tempfile.mkdtemp()
        try:
            lock_path = os.path.join(tmpdir, "singleton.lock")
            holder_snippet = textwrap.dedent(f"""
                import sys, time
                sys.path.insert(0, {_HERE!r})
                from singleton_guard import acquire_singleton_or_exit
                lock = acquire_singleton_or_exit({lock_path!r}, 'demo')
                time.sleep(1.5)
            """)
            holder = subprocess.Popen([sys.executable, "-c", holder_snippet])
            time.sleep(0.4)
            dup = run_subprocess_snippet(textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {_HERE!r})
                from singleton_guard import acquire_singleton_or_exit
                acquire_singleton_or_exit({lock_path!r}, 'demo')
            """))
            self.assertEqual(dup.returncode, DUPLICATE_START_EXIT_CODE)
            holder.wait(timeout=5)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


FIXTURE_STRANICA_MODULE = textwrap.dedent("""
    import stranica
    import subprocess

    def rebuild_pages():
        stranica.generate_all()

    def legacy_rebuild_pages():
        subprocess.run(["python3", "stranica.py"])
""")

FIXTURE_STRANICA_AMBIGUOUS = textwrap.dedent("""
    import stranica

    def rebuild_pages():
        stranica.generate_all()

    def rebuild_pages_alt():
        stranica.generate_variant()
""")


class RebuildAnchorTests(unittest.TestCase):
    def test_single_safe_anchor_found(self):
        candidates = find_stranica_generation_anchors(FIXTURE_STRANICA_MODULE)
        names = [c.name for c in candidates]
        self.assertEqual(names, ["rebuild_pages"])

    def test_ambiguous_anchors_blocked(self):
        candidates = find_stranica_generation_anchors(FIXTURE_STRANICA_AMBIGUOUS)
        self.assertEqual(len(candidates), 2)


class RebuildQueueCoalescingTests(unittest.TestCase):
    def test_burst_produces_bounded_followups_two_processes(self):
        from rebuild_queue import RebuildQueue  # local import for isolation
        tmpdir = tempfile.mkdtemp()
        try:
            lock_path = os.path.join(tmpdir, "rebuild.lock")
            call_log = os.path.join(tmpdir, "calls.log")

            worker_snippet = textwrap.dedent(f"""
                import sys, time
                sys.path.insert(0, {_HERE!r})
                from rebuild_queue import RebuildQueue

                def cb():
                    with open({call_log!r}, "a") as fh:
                        fh.write("call\\n")
                    time.sleep(0.8)

                q = RebuildQueue({lock_path!r}, cb)
                q.enqueue()
                time.sleep(0.2)
                q.enqueue()
                q.enqueue()
                q.enqueue()
                time.sleep(2.5)
            """)
            p = subprocess.Popen([sys.executable, "-c", worker_snippet])
            time.sleep(0.4)
            second_snippet = textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {_HERE!r})
                from rebuild_queue import RebuildQueue
                q = RebuildQueue({lock_path!r}, lambda: None)
                q.enqueue()
            """)
            run_subprocess_snippet(second_snippet)
            p.wait(timeout=6)
            with open(call_log) as fh:
                calls = fh.read().count("call")
            self.assertLessEqual(calls, 2)
            self.assertGreaterEqual(calls, 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


FIXTURE_DB_FUNC_BAD = textwrap.dedent("""
    import sqlite3
    import time

    def kolonki_cars(path):
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM cars")
        rows = cur.fetchall()
        time.sleep(1)
        return rows
""")


class SqliteOwnershipTests(unittest.TestCase):
    def test_negative_case_has_violation_before_transform(self):
        tree = ast.parse(FIXTURE_DB_FUNC_BAD)
        funcs = list(_iter_functions(tree, {"kolonki_cars"}))
        self.assertEqual(len(funcs), 1)
        violations = verify_no_live_handle_across_slow_call(funcs[0])
        self.assertTrue(violations)

    def test_transform_removes_violation(self):
        patched = transform_short_ownership(FIXTURE_DB_FUNC_BAD, {"kolonki_cars"})
        tree = ast.parse(patched)
        funcs = list(_iter_functions(tree, {"kolonki_cars"}))
        violations = verify_no_live_handle_across_slow_call(funcs[0])
        self.assertEqual(violations, [])

    def test_missing_function_blocked(self):
        with self.assertRaises(SqliteAnchorError):
            transform_short_ownership(FIXTURE_DB_FUNC_BAD, {"does_not_exist"})


FIXTURE_CARS_UI_CLEAN = textwrap.dedent("""
    def gallery(update, context):
        count = count_photos()
        update.message.reply_text(f"{count} photos")

    def video_gallery(update, context):
        count = count_videos()
        update.message.reply_text(f"{count} videos")

    def diag_photo_show(update, context):
        show_summary("photo")

    def diag_video_show(update, context):
        show_summary("video")

    def show_summary(kind):
        pass

    def count_photos():
        return 3

    def count_videos():
        return 2

    def upload_photo(path):
        return True

    def delete_media(media_id):
        return True
""")

FIXTURE_CARS_UI_INDIRECT_VIOLATION = textwrap.dedent("""
    def gallery(update, context):
        helper_send(update)

    def helper_send(update):
        update.message.reply_photo(open("x.jpg", "rb"))

    def video_gallery(update, context):
        pass

    def diag_photo_show(update, context):
        pass

    def diag_video_show(update, context):
        pass
""")

FIXTURE_CARS_UI_DYNAMIC_AMBIGUOUS = textwrap.dedent("""
    def gallery(update, context):
        fn = getattr(update.message, "reply_photo")
        fn(open("x.jpg", "rb"))

    def video_gallery(update, context):
        pass

    def diag_photo_show(update, context):
        pass

    def diag_video_show(update, context):
        pass
""")


class MediaCallGraphTests(unittest.TestCase):
    def test_clean_module_passes(self):
        result = find_reachable_media_calls(FIXTURE_CARS_UI_CLEAN)
        self.assertTrue(result.is_clean())

    def test_indirect_helper_violation_detected(self):
        result = find_reachable_media_calls(FIXTURE_CARS_UI_INDIRECT_VIOLATION)
        self.assertFalse(result.is_clean())
        self.assertIn("gallery", result.violations)

    def test_dynamic_dispatch_is_blocked_not_passed(self):
        result = find_reachable_media_calls(FIXTURE_CARS_UI_DYNAMIC_AMBIGUOUS)
        self.assertFalse(result.is_clean())
        self.assertIn("gallery", result.blocked)


class Ua0009PublicationCheckTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.pop(ua0009_mod.CONFIG_ENV_VAR, None)

    def tearDown(self):
        if self._old_env is not None:
            os.environ[ua0009_mod.CONFIG_ENV_VAR] = self._old_env

    def test_missing_config_is_blocked_not_skipped(self):
        result = check_ua0009_not_public("/nonexistent/crm.db")
        self.assertFalse(result.ok)
        self.assertIn("BLOCKED", result.reason)

    def test_404_and_quick_check_ok_passes(self):
        os.environ[ua0009_mod.CONFIG_ENV_VAR] = "https://example.invalid/ua-0009"
        orig_probe = ua0009_mod.probe_no_redirect
        orig_quick = ua0009_mod.sqlite_quick_check
        ua0009_mod.probe_no_redirect = lambda url, timeout=5.0: 404
        ua0009_mod.sqlite_quick_check = lambda db_path, timeout=2.0: "ok"
        try:
            result = check_ua0009_not_public(":memory:")
            self.assertTrue(result.ok)
        finally:
            ua0009_mod.probe_no_redirect = orig_probe
            ua0009_mod.sqlite_quick_check = orig_quick

    def test_200_status_is_blocked(self):
        os.environ[ua0009_mod.CONFIG_ENV_VAR] = "https://example.invalid/ua-0009"
        orig_probe = ua0009_mod.probe_no_redirect
        orig_quick = ua0009_mod.sqlite_quick_check
        ua0009_mod.probe_no_redirect = lambda url, timeout=5.0: 200
        ua0009_mod.sqlite_quick_check = lambda db_path, timeout=2.0: "ok"
        try:
            result = check_ua0009_not_public(":memory:")
            self.assertFalse(result.ok)
        finally:
            ua0009_mod.probe_no_redirect = orig_probe
            ua0009_mod.sqlite_quick_check = orig_quick


class SafeWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.writer = SafeWriter(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_atomic_write_and_hash(self):
        digest = self.writer.write_bytes("a/b.txt", b"hello")
        with open(os.path.join(self.tmpdir, "a", "b.txt"), "rb") as fh:
            self.assertEqual(fh.read(), b"hello")
        self.assertEqual(len(digest), 64)

    def test_traversal_rejected(self):
        with self.assertRaises(UnsafePathError):
            self.writer.write_bytes("../escape.txt", b"x")

    def test_symlink_parent_rejected(self):
        real_dir = os.path.join(self.tmpdir, "real")
        os.makedirs(real_dir)
        link_dir = os.path.join(self.tmpdir, "link")
        os.symlink(real_dir, link_dir)
        with self.assertRaises(UnsafePathError):
            self.writer.write_bytes("link/file.txt", b"x")

    def test_hardlink_target_rejected(self):
        target = os.path.join(self.tmpdir, "orig.txt")
        with open(target, "w") as fh:
            fh.write("x")
        hardlink = os.path.join(self.tmpdir, "hl.txt")
        os.link(target, hardlink)
        with self.assertRaises(UnsafePathError):
            self.writer.write_bytes("hl.txt", b"y")

    def test_insufficient_free_space_rejected(self):
        import safe_writer as sw

        class FakeUsage:
            free = 0
            total = 0
            used = 0

        orig = sw.shutil.disk_usage
        sw.shutil.disk_usage = lambda path: FakeUsage()
        try:
            with self.assertRaises(InsufficientSpaceError):
                self.writer.write_bytes("z.txt", b"x")
        finally:
            sw.shutil.disk_usage = orig


if __name__ == "__main__":
    unittest.main()
