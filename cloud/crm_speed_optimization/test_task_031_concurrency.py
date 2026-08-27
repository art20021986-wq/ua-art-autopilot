"""Offline, deterministic executable tests for TASK 031 phase A:
canonical concurrency primitives and secure writer.

No network access. No PythonAnywhere paths. Only temporary directories,
local processes and local threads are used.
"""
import multiprocessing
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest

from canonical_modules import (
    CrossProcessLock,
    LockEvidence,
    RebuildQueue,
    SafeWriter,
    SingletonGuard,
    _owner_status,
    _pid_alive,
    _process_start_time,
)


def _barrier_worker(lock_path, barrier, result_queue):
    lock = CrossProcessLock(lock_path, stale_after_seconds=5)
    barrier.wait()
    acquired = lock.acquire()
    # Wait until every contender in this round has attempted before the
    # winner releases, proving the winner is held throughout the round.
    barrier.wait()
    if acquired:
        result_queue.put(os.getpid())
        lock.release()
    barrier.wait()


class TestCrossProcessLockSafety(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task031_")
        self.lock_path = os.path.join(self.tmpdir, "test.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_live_owner_survives_expired_stale_after_seconds(self):
        lock = CrossProcessLock(self.lock_path, stale_after_seconds=0)
        self.assertTrue(lock.acquire())
        time.sleep(0.05)
        other = CrossProcessLock(self.lock_path, stale_after_seconds=0)
        self.assertFalse(other.acquire())
        lock.release()

    def test_dead_owner_stale_takeover(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        # Fabricate a dead-owner record: a PID that cannot exist.
        fake_pid = 999999
        while True:
            alive = _pid_alive(fake_pid)
            if alive is False:
                break
            fake_pid -= 1
            if fake_pid < 2:
                self.skipTest("could not find an unused pid for this environment")
        evidence = LockEvidence(fake_pid, "999999999", "deadtoken", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())
        lock._owned = False
        newcomer = CrossProcessLock(self.lock_path)
        self.assertTrue(newcomer.acquire())
        newcomer.release()

    def test_pid_reuse_start_mismatch_takeover(self):
        # pid is alive (this test process) but start_time is wrong ->
        # must be classified 'dead' (mismatch), allowing safe takeover.
        evidence = LockEvidence(os.getpid(), "not-the-real-start-time", "tok", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())
        status = _owner_status(evidence)
        self.assertEqual(status, "dead")
        newcomer = CrossProcessLock(self.lock_path)
        self.assertTrue(newcomer.acquire())
        newcomer.release()

    def test_unknown_identity_fails_closed(self):
        import canonical_modules as canon

        real_pid = os.getpid()
        evidence = LockEvidence(real_pid, _process_start_time(real_pid) or "x", "tok", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())

        original = canon._process_start_time
        canon._process_start_time = lambda pid: None
        try:
            status = _owner_status(evidence)
            self.assertEqual(status, "unknown")
            newcomer = CrossProcessLock(self.lock_path)
            self.assertFalse(newcomer.acquire())
        finally:
            canon._process_start_time = original

    def test_foreign_token_cannot_release(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        impostor = CrossProcessLock(self.lock_path)
        impostor._owned = True  # simulate an impostor believing it owns it
        impostor.release()
        # Real owner's evidence must remain untouched.
        self.assertTrue(os.path.exists(self.lock_path))
        current = lock._read_evidence()
        self.assertIsNotNone(current)
        self.assertEqual(current.token, lock.token)
        lock.release()

    def test_release_lifecycle_never_raises(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        lock.release()
        lock.release()  # double release must not raise

        lock2 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock2.acquire())
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pass
        finally:
            lock2.release()
        lock2.release()

        lock3 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock3.acquire())
        lock3.release()  # simulates an idempotent atexit invocation

        lock4 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock4.acquire())
        shutil.rmtree(self.tmpdir)
        # Deleted parent: release must be a safe no-op, never recreate it.
        lock4.release()
        self.assertFalse(os.path.exists(self.tmpdir))


class TestMultiprocessBarrier(unittest.TestCase):
    def test_100_rounds_exactly_one_winner(self):
        tmpdir = tempfile.mkdtemp(prefix="task031_mp_")
        try:
            lock_path = os.path.join(tmpdir, "barrier.lock")
            contenders = 4
            rounds = 100
            ctx = multiprocessing.get_context("fork")
            for i in range(rounds):
                barrier = ctx.Barrier(contenders)
                result_queue = ctx.Queue()
                procs = [
                    ctx.Process(target=_barrier_worker, args=(lock_path, barrier, result_queue))
                    for _ in range(contenders)
                ]
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(timeout=15)
                    self.assertFalse(p.is_alive(), f"round {i}: worker did not finish")
                winners = []
                while not result_queue.empty():
                    winners.append(result_queue.get())
                self.assertEqual(len(winners), 1, f"round {i} winners={winners}")
                for p in (lock_path, lock_path + ".guard"):
                    if os.path.exists(p):
                        try:
                            os.unlink(p)
                        except FileNotFoundError:
                            pass
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestRebuildQueue(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task031_rq_")
        self.lock_path = os.path.join(self.tmpdir, "rebuild.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_enqueue_returns_promptly_while_callback_is_slow(self):
        started = threading.Event()
        release_cb = threading.Event()

        def slow_cb():
            started.set()
            release_cb.wait(timeout=3)

        q = RebuildQueue(slow_cb, self.lock_path)
        t0 = time.time()
        result = q.enqueue()
        elapsed = time.time() - t0
        self.assertEqual(result, "accepted")
        self.assertLess(elapsed, 0.5)
        self.assertTrue(started.wait(timeout=2))
        release_cb.set()
        q.shutdown(timeout=5)
        self.assertEqual(q.runs, 1)

    def test_burst_produces_one_active_run_and_one_followup(self):
        calls = []
        gate = threading.Event()

        def cb():
            gate.wait(timeout=3)
            calls.append(1)

        q = RebuildQueue(cb, self.lock_path)
        r1 = q.enqueue()
        self.assertEqual(r1, "accepted")
        for _ in range(10):
            q.enqueue()
        gate.set()
        q.shutdown(timeout=5)
        self.assertEqual(len(calls), 2)
        self.assertEqual(q.runs, 2)
        self.assertGreaterEqual(q.coalesced, 1)

    def test_callback_exception_is_bounded_no_spin(self):
        attempts = {"n": 0}

        def failing_cb():
            attempts["n"] += 1
            raise ValueError("deliberate failure")

        q = RebuildQueue(failing_cb, self.lock_path)
        q.enqueue()
        deadline = time.time() + 3
        while attempts["n"] == 0 and time.time() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        q.shutdown(timeout=5)
        self.assertEqual(attempts["n"], 1)
        self.assertEqual(len(q.errors), 1)
        self.assertEqual(q.runs, 0)


class TestSafeWriter(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="task031_sw_")

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_reject_absolute_path(self):
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("/etc/passwd", b"x")

    def test_reject_traversal(self):
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("../escape.txt", b"x")

    def test_reject_symlink_parent(self):
        real_sub = os.path.join(self.run_dir, "realdir")
        os.mkdir(real_sub)
        link_sub = os.path.join(self.run_dir, "linkdir")
        os.symlink(real_sub, link_sub)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("linkdir/file.txt", b"x")

    def test_reject_target_symlink(self):
        target = os.path.join(self.run_dir, "file.txt")
        os.symlink("/etc/passwd", target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("file.txt", b"x")

    def test_reject_hardlink_target(self):
        other = os.path.join(self.run_dir, "other.txt")
        with open(other, "w") as fh:
            fh.write("hello")
        target = os.path.join(self.run_dir, "file.txt")
        os.link(other, target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("file.txt", b"x")

    def test_reject_non_regular_target(self):
        target = os.path.join(self.run_dir, "fifo")
        os.mkfifo(target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("fifo", b"x")

    def test_reject_deleted_parent(self):
        w = SafeWriter(self.run_dir)
        shutil.rmtree(self.run_dir)
        with self.assertRaises(Exception):
            w.write_bytes("sub/file.txt", b"x")

    def test_replacement_race_is_rejected(self):
        w = SafeWriter(self.run_dir)

        def hook(target, target_dir):
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink("/etc/passwd", target)

        w._pre_replace_hook = hook
        with self.assertRaises(ValueError):
            w.write_bytes("race.txt", b"payload")
        target = os.path.join(self.run_dir, "race.txt")
        self.assertTrue(os.path.islink(target))

    def test_successful_write_atomic_hash_recorded(self):
        w = SafeWriter(self.run_dir)
        data = b"hello world, byte exact\x00\x01\x02"
        target = w.write_bytes("reports/out.bin", data)
        with open(target, "rb") as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, data)
        st = os.stat(target)
        self.assertEqual(st.st_nlink, 1)
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(len(w.ledger), 1)
        entry = w.ledger[0]
        self.assertEqual(entry["relative_path"], os.path.normpath("reports/out.bin"))
        self.assertEqual(entry["size"], len(data))
        import hashlib
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())


class TestCompatibilityImports(unittest.TestCase):
    def test_reexports_resolve_to_canonical_objects(self):
        import canonical_modules as canon
        import cross_process_lock as cpl
        import rebuild_queue as rq
        import safe_writer as sw
        import singleton_guard as sg

        self.assertIs(cpl.CrossProcessLock, canon.CrossProcessLock)
        self.assertIs(cpl.LockEvidence, canon.LockEvidence)
        self.assertIs(cpl.SingletonGuard, canon.SingletonGuard)
        self.assertIs(rq.RebuildQueue, canon.RebuildQueue)
        self.assertIs(sw.SafeWriter, canon.SafeWriter)
        self.assertIs(sg.CrossProcessLock, canon.CrossProcessLock)
        self.assertIs(sg.SingletonGuard, canon.SingletonGuard)


if __name__ == "__main__":
    unittest.main()
