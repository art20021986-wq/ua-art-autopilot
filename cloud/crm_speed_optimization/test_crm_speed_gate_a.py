"""Behavioral test suite for CRM-SPEED-001 Gate A round 2.

Covers: cross-process lock correctness under real multiprocess contention,
idempotent/exception-safe release and atexit lifecycle, evidence-derived
predicates (mutation -> BLOCKED), bounded site inventory, fail-closed
publication probe, and the AST-based structural transforms against
synthetic fixtures.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a as gate_a  # noqa: E402


# --------------------------------------------------------------------------
# Helper worker functions for multiprocessing tests (must be top-level to be
# picklable under the spawn/fork contexts).
# --------------------------------------------------------------------------

def _contender_worker(lock_path, ready_event, start_event, hold_event, result_queue, hold_timeout):
    lock = gate_a.CrossProcessLock(lock_path)
    ready_event.set()
    start_event.wait()
    acquired = lock.acquire(timeout=0)
    if acquired:
        result_queue.put(("acquired", os.getpid()))
        hold_event.wait(timeout=hold_timeout)
        lock.release()
    else:
        result_queue.put(("rejected", os.getpid()))


def _fresh_contender_worker(lock_path, result_queue):
    lock = gate_a.CrossProcessLock(lock_path)
    acquired = lock.acquire(timeout=0)
    result_queue.put(("acquired" if acquired else "rejected", os.getpid()))
    if acquired:
        lock.release()


class CrossProcessLockTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_stale(self, path, pid=999999):
        with open(path, "w") as f:
            json.dump({"pid": pid, "start_time_ns": 1, "token": "stale", "acquired_at": 0}, f)

    def test_clean_acquire_release(self):
        path = os.path.join(self.tmpdir, "a.lock")
        lock = gate_a.CrossProcessLock(path)
        self.assertTrue(lock.acquire(timeout=0))
        self.assertTrue(os.path.exists(path))
        lock.release()
        self.assertFalse(os.path.exists(path))

    def test_repeated_release_is_idempotent(self):
        path = os.path.join(self.tmpdir, "b.lock")
        lock = gate_a.CrossProcessLock(path)
        lock.acquire(timeout=0)
        lock.release()
        lock.release()  # must not raise
        lock.release()

    def test_release_after_run_dir_removed_does_not_raise(self):
        run_dir = tempfile.mkdtemp()
        path = os.path.join(run_dir, "c.lock")
        lock = gate_a.CrossProcessLock(path)
        lock.acquire(timeout=0)
        shutil.rmtree(run_dir, ignore_errors=True)
        # explicit release after directory is gone must be silent
        lock.release()
        # simulated atexit call after cleanup must also be silent
        lock._atexit_release()

    def test_explicit_release_unregisters_atexit(self):
        path = os.path.join(self.tmpdir, "d.lock")
        lock = gate_a.CrossProcessLock(path)
        lock.acquire(timeout=0)
        self.assertTrue(lock._atexit_registered)
        lock.release()
        self.assertFalse(lock._atexit_registered)

    def test_foreign_token_release_does_not_delete_file(self):
        path = os.path.join(self.tmpdir, "e.lock")
        lock = gate_a.CrossProcessLock(path)
        lock.acquire(timeout=0)
        # simulate foreign takeover overwriting the file with a different token
        with open(path, "w") as f:
            json.dump({"pid": os.getpid(), "start_time_ns": 1, "token": "someone_else", "acquired_at": 0}, f)
        lock.release()
        self.assertTrue(os.path.exists(path))

    def test_stale_dead_pid_takeover(self):
        path = os.path.join(self.tmpdir, "f.lock")
        self._write_stale(path, pid=999999)
        lock = gate_a.CrossProcessLock(path)
        self.assertTrue(lock.acquire(timeout=0))
        lock.release()

    def test_pid_reuse_start_time_mismatch_treated_as_dead(self):
        path = os.path.join(self.tmpdir, "g.lock")
        real_start = gate_a.CrossProcessLock._proc_start_time_ns(os.getpid())
        with open(path, "w") as f:
            json.dump(
                {"pid": os.getpid(), "start_time_ns": (real_start or 0) + 999999, "token": "x", "acquired_at": 0},
                f,
            )
        lock = gate_a.CrossProcessLock(path)
        self.assertTrue(lock.acquire(timeout=0))
        lock.release()

    def test_live_duplicate_is_rejected(self):
        path = os.path.join(self.tmpdir, "h.lock")
        owner = gate_a.CrossProcessLock(path)
        self.assertTrue(owner.acquire(timeout=0))
        try:
            duplicate = gate_a.CrossProcessLock(path)
            self.assertFalse(duplicate.acquire(timeout=0))
        finally:
            owner.release()

    def test_exception_during_hold_still_allows_release_via_finally(self):
        path = os.path.join(self.tmpdir, "i.lock")
        lock = gate_a.CrossProcessLock(path)
        lock.acquire(timeout=0)
        try:
            try:
                raise RuntimeError("boom")
            finally:
                lock.release()
        except RuntimeError:
            pass
        self.assertFalse(os.path.exists(path))

    def test_simultaneous_stale_takeover_only_one_wins(self):
        path = os.path.join(self.tmpdir, "stale_race.lock")
        self._write_stale(path)
        ctx = mp.get_context("spawn")
        n = 6
        ready_events = [ctx.Event() for _ in range(n)]
        start_event = ctx.Event()
        hold_event = ctx.Event()
        result_queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_contender_worker,
                args=(path, ready_events[i], start_event, hold_event, result_queue, 5.0),
            )
            for i in range(n)
        ]
        for p in procs:
            p.start()
        for e in ready_events:
            self.assertTrue(e.wait(timeout=15))
        start_event.set()

        results = [result_queue.get(timeout=15) for _ in range(n)]
        acquired = [r for r in results if r[0] == "acquired"]
        rejected = [r for r in results if r[0] == "rejected"]
        self.assertEqual(len(acquired), 1, f"expected exactly 1 winner, got {len(acquired)}: {results}")
        self.assertEqual(len(rejected), n - 1)

        winner_pid = acquired[0][1]
        end_check = time.monotonic() + 1.0
        while time.monotonic() < end_check:
            with open(path, "r") as f:
                data = json.load(f)
            self.assertEqual(data["pid"], winner_pid)
            time.sleep(0.05)

        hold_event.set()
        for p in procs:
            p.join(timeout=15)

        fresh_queue = ctx.Queue()
        fp = ctx.Process(target=_fresh_contender_worker, args=(path, fresh_queue))
        fp.start()
        fp.join(timeout=15)
        fresh_result = fresh_queue.get(timeout=15)
        self.assertEqual(fresh_result[0], "acquired")

    @unittest.skipUnless(hasattr(os, "fork"), "requires fork for fast stress loop")
    def test_stale_takeover_stress_100_rounds(self):
        ctx = mp.get_context("fork")
        rounds = 100
        n = 4
        for round_i in range(rounds):
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "stress.lock")
                self._write_stale(path)
                ready_events = [ctx.Event() for _ in range(n)]
                start_event = ctx.Event()
                hold_event = ctx.Event()
                rq = ctx.Queue()
                procs = [
                    ctx.Process(
                        target=_contender_worker,
                        args=(path, ready_events[i], start_event, hold_event, rq, 2.0),
                    )
                    for i in range(n)
                ]
                for p in procs:
                    p.start()
                for e in ready_events:
                    self.assertTrue(e.wait(timeout=5))
                start_event.set()
                results = [rq.get(timeout=5) for _ in range(n)]
                acquired = [r for r in results if r[0] == "acquired"]
                self.assertEqual(len(acquired), 1, f"round {round_i}: {results}")
                hold_event.set()
                for p in procs:
                    p.join(timeout=5)


class SingletonGuardTests(unittest.TestCase):
    def test_duplicate_start_exits_with_defined_code(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "singleton.lock")
            owner = gate_a.CrossProcessLock(path)
            owner.acquire(timeout=0)
            try:
                guard = gate_a.SingletonGuard(path)
                code = guard.run(lambda: 0, exit_code_on_duplicate=7)
                self.assertEqual(code, 7)
            finally:
                owner.release()

    def test_normal_run_releases_lock_after_main(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "singleton2.lock")
            guard = gate_a.SingletonGuard(path)
            result = guard.run(lambda: 42)
            self.assertEqual(result, 42)
            self.assertFalse(os.path.exists(path))

    def test_exception_in_main_still_releases_lock(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "singleton3.lock")
            guard = gate_a.SingletonGuard(path)

            def boom():
                raise RuntimeError("x")

            with self.assertRaises(RuntimeError):
                guard.run(boom)
            self.assertFalse(os.path.exists(path))


class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_bounded_calls(self):
        with tempfile.TemporaryDirectory() as d:
            lock_path = os.path.join(d, "rq.lock")
            pending_path = os.path.join(d, "rq.pending")
            calls = []
            call_lock = __import__("threading").Lock()

            def cb():
                with call_lock:
                    calls.append(time.time())
                time.sleep(0.05)

            rq = gate_a.RebuildQueue(lock_path, pending_path, cb)
            for _ in range(10):
                rq.enqueue()
            time.sleep(1.0)
            self.assertGreaterEqual(len(calls), 1)
            self.assertLess(len(calls), 10)

    def test_enqueue_returns_immediately(self):
        with tempfile.TemporaryDirectory() as d:
            lock_path = os.path.join(d, "rq2.lock")
            pending_path = os.path.join(d, "rq2.pending")

            def slow_cb():
                time.sleep(1.0)

            rq = gate_a.RebuildQueue(lock_path, pending_path, slow_cb)
            start = time.monotonic()
            rq.enqueue()
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.2)


class EvidenceFrameworkTests(unittest.TestCase):
    def test_no_placeholder_true_without_condition(self):
        ev = gate_a.Evidence("x")
        result = ev.finalize(True)
        self.assertTrue(result)
        self.assertEqual(ev.measurements, {})

    def test_fail_locks_passed_false_even_if_finalize_called_with_true(self):
        ev = gate_a.Evidence("x")
        ev.fail("bad_measurement")
        result = ev.finalize(True)
        self.assertFalse(result)
        self.assertFalse(ev.passed)


class SiteInventoryTests(unittest.TestCase):
    def _make_roots(self, base):
        roots = [os.path.join(base, n) for n in ("site", "video", "public_html")]
        for r in roots:
            os.makedirs(r, exist_ok=True)
        return roots

    def test_missing_root_blocks(self):
        with tempfile.TemporaryDirectory() as base:
            roots = [os.path.join(base, "site")]  # only create nothing
            inv, blocked = gate_a.scan_bounded_inventory(roots)
            self.assertTrue(any(b.startswith("missing_root") for b in blocked))

    def test_unchanged_pass(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            with open(os.path.join(roots[0], "index.html"), "w") as f:
                f.write("hello")
            before, b1 = gate_a.scan_bounded_inventory(roots)
            after, b2 = gate_a.scan_bounded_inventory(roots)
            self.assertEqual(b1, [])
            self.assertEqual(b2, [])
            self.assertTrue(gate_a.inventories_equal(before, after))

    def test_mutation_detected(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            p = os.path.join(roots[0], "index.html")
            with open(p, "w") as f:
                f.write("hello")
            before, _ = gate_a.scan_bounded_inventory(roots)
            time.sleep(0.01)
            with open(p, "w") as f:
                f.write("changed")
            after, _ = gate_a.scan_bounded_inventory(roots)
            self.assertFalse(gate_a.inventories_equal(before, after))

    def test_symlink_blocks(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            real = os.path.join(base, "real.html")
            with open(real, "w") as f:
                f.write("x")
            link = os.path.join(roots[0], "index.html")
            os.symlink(real, link)
            inv, blocked = gate_a.scan_bounded_inventory(roots)
            self.assertTrue(any(b.startswith("symlink:") for b in blocked))

    def test_hardlink_blocks(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            p1 = os.path.join(roots[0], "index.html")
            with open(p1, "w") as f:
                f.write("x")
            p2 = os.path.join(roots[0], "katalog.html")
            try:
                os.link(p1, p2)
            except OSError:
                self.skipTest("hard links unsupported on this filesystem")
            inv, blocked = gate_a.scan_bounded_inventory(roots)
            self.assertTrue(any(b.startswith("hardlink:") for b in blocked))

    def test_overflow_blocks(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            allowed = sorted(gate_a.ALLOWED_SITE_NAMES)
            for name in allowed[: gate_a.MAX_FILES_PER_ROOT + 1]:
                with open(os.path.join(roots[0], name), "w") as f:
                    f.write("x")
            inv, blocked = gate_a.scan_bounded_inventory(roots)
            self.assertTrue(any(b.startswith("overflow:") for b in blocked))

    def test_add_remove_allowed_file_detected(self):
        with tempfile.TemporaryDirectory() as base:
            roots = self._make_roots(base)
            before, _ = gate_a.scan_bounded_inventory(roots)
            with open(os.path.join(roots[0], "UA-0001.html"), "w") as f:
                f.write("x")
            after, _ = gate_a.scan_bounded_inventory(roots)
            self.assertFalse(gate_a.inventories_equal(before, after))


class PublicationProbeTests(unittest.TestCase):
    def test_missing_url_blocks(self):
        ev = gate_a.probe_ua0009_not_public("")
        self.assertFalse(ev.passed)

    def test_non_https_blocks(self):
        ev = gate_a.probe_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertFalse(ev.passed)

    def test_connection_refused_blocks(self):
        # bind to a free port then close it so connection is refused
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        ev = gate_a.probe_ua0009_not_public(f"https://127.0.0.1:{port}/UA-0009.html")
        self.assertFalse(ev.passed)

    def test_404_passes(self):
        import unittest.mock as mock

        class FakeHTTPError(urllib.error.HTTPError):
            pass

        def fake_open(self, req, timeout=5):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        with mock.patch("urllib.request.OpenerDirector.open", fake_open):
            ev = gate_a.probe_ua0009_not_public("https://example.invalid/UA-0009.html")
        self.assertTrue(ev.passed)

    def test_200_blocks(self):
        import io
        import unittest.mock as mock

        class FakeResp:
            def getcode(self):
                return 200

        def fake_open(self, req, timeout=5):
            return FakeResp()

        with mock.patch("urllib.request.OpenerDirector.open", fake_open):
            ev = gate_a.probe_ua0009_not_public("https://example.invalid/UA-0009.html")
        self.assertFalse(ev.passed)

    def test_redirect_blocks(self):
        import unittest.mock as mock

        def fake_open(self, req, timeout=5):
            raise urllib.error.HTTPError(req.full_url, 301, "Moved", {}, None)

        with mock.patch("urllib.request.OpenerDirector.open", fake_open):
            ev = gate_a.probe_ua0009_not_public("https://example.invalid/UA-0009.html")
        self.assertFalse(ev.passed)

    def test_timeout_blocks(self):
        import unittest.mock as mock

        def fake_open(self, req, timeout=5):
            raise socket.timeout()

        with mock.patch("urllib.request.OpenerDirector.open", fake_open):
            ev = gate_a.probe_ua0009_not_public("https://example.invalid/UA-0009.html")
        self.assertFalse(ev.passed)


class SqliteQuickCheckTests(unittest.TestCase):
    def test_ok_db_passes(self):
        with tempfile.TemporaryDirectory() as d:
            db_path = os.path.join(d, "t.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
            conn.close()
            ev = gate_a.sqlite_quick_check(db_path)
            self.assertTrue(ev.passed)

    def test_missing_db_blocks(self):
        ev = gate_a.sqlite_quick_check("/nonexistent/path/does_not_exist.db")
        self.assertFalse(ev.passed)


class UsercustomizeTransformTests(unittest.TestCase):
    def test_clean_inert_source_passes(self):
        src = "import sys\nimport os\n\ndef helper():\n    return 1\n"
        candidate, reasons = gate_a.transform_usercustomize(src)
        self.assertIsNotNone(candidate)
        self.assertEqual(reasons, [])

    def test_forbidden_import_removed(self):
        src = "import team_bot\nimport sys\n"
        candidate, reasons = gate_a.transform_usercustomize(src)
        self.assertIsNotNone(candidate)
        self.assertNotIn("team_bot", candidate)

    def test_unclassified_toplevel_call_blocks(self):
        src = "start_background_worker()\n"
        candidate, reasons = gate_a.transform_usercustomize(src)
        self.assertIsNone(candidate)
        self.assertTrue(reasons)

    def test_toplevel_thread_start_blocks(self):
        src = "import threading\nthreading.Thread(target=lambda: None).start()\n"
        candidate, reasons = gate_a.transform_usercustomize(src)
        self.assertIsNone(candidate)


class SingletonWrapTransformTests(unittest.TestCase):
    def test_clean_main_guard_wrapped(self):
        src = "def main():\n    return 0\n\nif __name__ == \"__main__\":\n    main()\n"
        candidate, reasons = gate_a.transform_singleton_wrap(src, "/tmp/x.lock")
        self.assertIsNotNone(candidate)
        self.assertIn("SingletonGuard", candidate)

    def test_missing_guard_blocks(self):
        src = "def main():\n    return 0\n"
        candidate, reasons = gate_a.transform_singleton_wrap(src, "/tmp/x.lock")
        self.assertIsNone(candidate)

    def test_ambiguous_guard_body_blocks(self):
        src = (
            "def main():\n    return 0\n\n"
            "if __name__ == \"__main__\":\n    main()\n    print('extra')\n"
        )
        candidate, reasons = gate_a.transform_singleton_wrap(src, "/tmp/x.lock")
        self.assertIsNone(candidate)


class AvtoperedachaRebuildTransformTests(unittest.TestCase):
    def test_single_subprocess_call_replaced(self):
        src = (
            "import subprocess\n\n"
            "def rebuild():\n    subprocess.run(['python3', 'stranica.py'])\n"
        )
        candidate, reasons = gate_a.transform_avtoperedacha_rebuild(src)
        self.assertIsNotNone(candidate)
        self.assertIn("REBUILD_QUEUE.enqueue", candidate)
        self.assertNotIn("subprocess.run", candidate)

    def test_zero_calls_blocks(self):
        src = "def rebuild():\n    return 1\n"
        candidate, reasons = gate_a.transform_avtoperedacha_rebuild(src)
        self.assertIsNone(candidate)

    def test_multiple_calls_blocks(self):
        src = (
            "import subprocess\n\n"
            "def rebuild():\n    subprocess.run(['a'])\n\n"
            "def rebuild2():\n    subprocess.run(['b'])\n"
        )
        candidate, reasons = gate_a.transform_avtoperedacha_rebuild(src)
        self.assertIsNone(candidate)


class CarsUiTransformTests(unittest.TestCase):
    def test_simple_media_call_rewritten(self):
        src = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('a.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('a.mp4', 'rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    update.message.reply_photo(open('b.jpg', 'rb'))\n"
            "def diag_video_show(update, context):\n"
            "    update.message.reply_video(open('b.mp4', 'rb'))\n"
        )
        routes = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]
        candidate, reasons = gate_a.transform_cars_ui_admin_routes(src, routes)
        self.assertIsNotNone(candidate, reasons)
        self.assertNotIn("reply_photo", candidate)
        self.assertNotIn("reply_video", candidate)

    def test_dynamic_dispatch_blocks(self):
        src = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('a.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n    pass\n"
            "def diag_photo_show(update, context):\n    pass\n"
            "def diag_video_show(update, context):\n    pass\n"
        )
        routes = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]
        candidate, reasons = gate_a.transform_cars_ui_admin_routes(src, routes)
        self.assertIsNone(candidate)

    def test_missing_route_blocks(self):
        src = "def gallery(update, context):\n    pass\n"
        routes = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]
        candidate, reasons = gate_a.transform_cars_ui_admin_routes(src, routes)
        self.assertIsNone(candidate)


class DbShortOwnershipTransformTests(unittest.TestCase):
    def test_missing_close_inserted(self):
        src = (
            "def kolonki(self):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    rows = conn.execute('SELECT 1').fetchall()\n"
            "    time.sleep(1)\n"
            "    return rows\n"
        )
        candidate, reasons = gate_a.transform_db_short_ownership(src, ["kolonki"])
        self.assertIsNotNone(candidate, reasons)
        self.assertIn("conn.close()", candidate)

    def test_already_closed_unchanged_semantics(self):
        src = (
            "def kolonki(self):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    rows = conn.execute('SELECT 1').fetchall()\n"
            "    conn.close()\n"
            "    time.sleep(1)\n"
            "    return rows\n"
        )
        candidate, reasons = gate_a.transform_db_short_ownership(src, ["kolonki"])
        self.assertIsNotNone(candidate, reasons)

    def test_db_used_after_slow_call_blocks(self):
        src = (
            "def kolonki(self):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    rows = conn.execute('SELECT 1').fetchall()\n"
            "    time.sleep(1)\n"
            "    more = conn.execute('SELECT 2').fetchall()\n"
            "    return rows, more\n"
        )
        candidate, reasons = gate_a.transform_db_short_ownership(src, ["kolonki"])
        self.assertIsNone(candidate)

    def test_loop_control_flow_blocks(self):
        src = (
            "def kolonki(self):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    for i in range(3):\n"
            "        conn.execute('SELECT 1')\n"
            "    time.sleep(1)\n"
        )
        candidate, reasons = gate_a.transform_db_short_ownership(src, ["kolonki"])
        self.assertIsNone(candidate)


class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_all_identical(self):
        src = "import sys\n"
        ev = gate_a.measure_deterministic_repeat(gate_a.transform_usercustomize, src, repeats=10)
        self.assertTrue(ev.passed)

    def test_nondeterministic_transform_blocks(self):
        import random

        def flaky_transform(source):
            if random.random() < 0.5:
                return "import sys\n", []
            return "import sys\nimport os\n", []

        ev = gate_a.measure_deterministic_repeat(flaky_transform, src="x", repeats=10)
        self.assertFalse(ev.passed)


class SafeWriterTests(unittest.TestCase):
    def test_write_confined_to_run_dir(self):
        with tempfile.TemporaryDirectory() as d:
            writer = gate_a.SafeWriter(d)
            path = writer.write_text("a/b.txt", "hello")
            self.assertTrue(path.startswith(os.path.realpath(d)))

    def test_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            writer = gate_a.SafeWriter(d)
            with self.assertRaises(gate_a.SafeWriteError):
                writer.write_text("../escape.txt", "x")

    def test_symlink_target_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            writer = gate_a.SafeWriter(d)
            real = os.path.join(d, "real.txt")
            with open(real, "w") as f:
                f.write("x")
            link = os.path.join(d, "link.txt")
            os.symlink(real, link)
            with self.assertRaises(gate_a.SafeWriteError):
                writer.write_text("link.txt", "y")

    def test_hardlink_target_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            writer = gate_a.SafeWriter(d)
            p1 = os.path.join(d, "p1.txt")
            with open(p1, "w") as f:
                f.write("x")
            p2 = os.path.join(d, "p2.txt")
            try:
                os.link(p1, p2)
            except OSError:
                self.skipTest("hard links unsupported")
            with self.assertRaises(gate_a.SafeWriteError):
                writer.write_text("p2.txt", "y")


class EndToEndFixtureTests(unittest.TestCase):
    def _fixture(self, base):
        os.makedirs(os.path.join(base, "site"), exist_ok=True)
        os.makedirs(os.path.join(base, "video"), exist_ok=True)
        os.makedirs(os.path.join(base, "public_html"), exist_ok=True)
        db_path = os.path.join(base, "crm.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE cars (id INTEGER)")
        conn.commit()
        conn.close()
        return db_path

    def test_sqlite_quick_check_ok_in_fixture(self):
        with tempfile.TemporaryDirectory() as base:
            db_path = self._fixture(base)
            ev = gate_a.sqlite_quick_check(db_path)
            self.assertTrue(ev.passed)

    def test_fixture_tree_unchanged_after_scan(self):
        with tempfile.TemporaryDirectory() as base:
            db_path = self._fixture(base)
            before = gate_a.sha256_file(db_path)
            gate_a.sqlite_quick_check(db_path)
            after = gate_a.sha256_file(db_path)
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
