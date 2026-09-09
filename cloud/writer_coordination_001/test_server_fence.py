"""Actual competing local processes; no application imports/network/tasks API.

These tests do not prove cross-host PythonAnywhere lock semantics or a drained
platform scheduler. One test specifically demonstrates why that proof matters.
"""
import datetime as dt
import fcntl
import importlib.util
import json
import multiprocessing
import os
import pathlib
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).with_name("server_fence.py")
spec = importlib.util.spec_from_file_location("server_fence", SOURCE)
fence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fence)
CTX = multiprocessing.get_context("fork")


def try_lock(path, queue):
    with open(path, "r+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            queue.put("ACQUIRED")
        except BlockingIOError:
            queue.put("BUSY")


def queued_writer(path, ready, finished):
    with open(path, "r+b") as stream:
        ready.set()
        fcntl.flock(stream, fcntl.LOCK_EX)
        finished.set()


def hold_child(root, control, session, ready):
    lease = fence.FenceLease(pathlib.Path(root), pathlib.Path(control), session)
    lease.acquire()
    response = lease.challenge({"schema": fence.CHALLENGE_SCHEMA, "session": session,
                                "command": "PROBE", "challenge": "b" * 64})
    fence.write_json(lease.directory / "response.json", response)
    ready.set()
    while True:
        time.sleep(0.1)


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / "app"
        self.control = pathlib.Path(self.temp.name) / "control"
        self.root.mkdir()
        self.control.mkdir()
        self.nonce = "a" * 64
        self.directory = self.control / "sessions" / self.nonce
        self.directory.mkdir(parents=True)
        for name in fence.LOCK_NAMES:
            (self.root / name).touch()
        self.session = {"repository": "art20021986-wq/ua-art-autopilot", "account": "Carix",
                        "production_root": "/home/Carix", "task_id": "UA-ART-WRITER-001",
                        "expected_main": "1" * 40, "plan_sha256": "2" * 64,
                        "run_id": "12345", "run_attempt": 1, "nonce": self.nonce,
                        "epoch": 1, "source_sha256": fence.sha(SOURCE.read_bytes())}
        self.lease = fence.FenceLease(self.root, self.control, self.session)

    def tearDown(self):
        self.lease.close()
        self.temp.cleanup()

    def probe(self, challenge="b" * 64, command="PROBE", session=None):
        return self.lease.challenge({"schema": fence.CHALLENGE_SCHEMA,
                                     "session": session or self.session,
                                     "command": command, "challenge": challenge})

    def lock_attempt(self, path):
        queue = CTX.Queue()
        process = CTX.Process(target=try_lock, args=(str(path), queue))
        process.start()
        try:
            result = queue.get(timeout=3)
            process.join(3)
            self.assertEqual(process.exitcode, 0)
            return result
        finally:
            if process.is_alive():
                process.terminate()
                process.join(3)
            queue.close()

    def test_all_exact_lock_inodes_exclude_competing_process(self):
        before = {name: (self.root / name).stat().st_ino for name in fence.LOCK_NAMES}
        self.lease.acquire()
        for name in fence.LOCK_NAMES:
            self.assertEqual(self.lock_attempt(self.root / name), "BUSY")
        proof = self.probe()
        self.assertEqual(len(proof["locks"]), 6)
        self.assertEqual([value["inode"] for value in proof["locks"]], list(before.values()))
        self.assertEqual(proof["lock_manifest_sha256"], fence.sha(fence.canonical(proof["locks"])))
        self.assertFalse(proof["external_writers_verified"])
        self.assertFalse(proof["cross_host_lock_verified"])

    def test_proof_binds_session_and_has_bounded_freshness(self):
        self.lease.acquire()
        proof = self.probe()
        for key, value in self.session.items():
            self.assertEqual(proof[key], value)
        issued, expires = (dt.datetime.fromisoformat(proof[key]) for key in ("issued_at", "expires_at"))
        self.assertEqual((expires - issued).total_seconds(), 30)
        self.assertEqual(proof["scope"], "LEGACY_LOCKS_HELD_ONLY")
        self.assertTrue(proof["durable_intent"])

    def test_release_persists_intent_and_does_not_delete_locks(self):
        self.lease.acquire()
        proof = self.probe(command="RELEASE")
        self.assertEqual(proof["state"], "RELEASED")
        self.assertEqual(proof["ttl_seconds"], 0)
        self.assertEqual(json.loads((self.control / "active-intent.json").read_text())["state"], "RELEASED")
        for name in fence.LOCK_NAMES:
            self.assertEqual(self.lock_attempt(self.root / name), "ACQUIRED")
        with self.assertRaises(fence.FenceError):
            self.probe("c" * 64)

    def test_old_challenge_cannot_extend_its_validity_after_other_challenge(self):
        self.lease.acquire()
        self.probe("b" * 64)
        self.probe("c" * 64)
        with self.assertRaisesRegex(fence.FenceError, "CHALLENGE_REPLAY"):
            self.probe("b" * 64)

    def test_wrong_context_refused_for_every_binding(self):
        self.lease.acquire()
        for key in self.session:
            changed = dict(self.session, **{key: "wrong"})
            with self.subTest(key=key), self.assertRaisesRegex(fence.FenceError, "CHALLENGE_BINDING"):
                self.probe(session=changed)

    def test_invalid_session_types_or_extra_keys_refused(self):
        for changed in (dict(self.session, epoch=True), dict(self.session, run_attempt=True),
                        dict(self.session, source_sha256="0" * 64), dict(self.session, extra="x")):
            with self.assertRaises(fence.FenceError):
                fence.FenceLease(self.root, self.control, changed)

    def test_missing_legacy_lock_is_not_created(self):
        missing = self.root / fence.LOCK_NAMES[-1]
        missing.unlink()
        with self.assertRaises(FileNotFoundError):
            self.lease.acquire()
        self.assertFalse(missing.exists())
        self.assertFalse(self.lease.held)
        self.assertEqual(self.lock_attempt(self.root / fence.LOCK_NAMES[0]), "ACQUIRED")

    def test_busy_lock_fails_and_releases_partial_acquisition(self):
        with open(self.root / fence.LOCK_NAMES[3], "r+b") as occupied:
            fcntl.flock(occupied, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.lease.acquire()
            self.assertEqual(self.lock_attempt(self.root / fence.LOCK_NAMES[0]), "ACQUIRED")
            self.assertEqual(self.lock_attempt(self.root / fence.LOCK_NAMES[3]), "BUSY")
        self.assertEqual(json.loads((self.control / "active-intent.json").read_text())["state"], "FAILED")

    def test_symlink_lock_and_parent_refused(self):
        target = self.root / fence.LOCK_NAMES[-1]
        target.unlink()
        target.symlink_to(self.root / fence.LOCK_NAMES[0])
        with self.assertRaises(OSError):
            self.lease.acquire()
        link = pathlib.Path(self.temp.name) / "link"
        link.symlink_to(self.control, target_is_directory=True)
        with self.assertRaises(fence.FenceError):
            fence.FenceLease(self.root, link, self.session)

    def test_replaced_resource_lock_refuses_new_proof(self):
        self.lease.acquire()
        path = self.root / fence.LOCK_NAMES[2]
        path.rename(path.with_name(path.name + ".replaced"))
        path.touch()
        with self.assertRaisesRegex(fence.FenceError, "RESOURCE_LOCK_REPLACED"):
            self.probe()

    def test_replaced_coordinator_lock_refuses_new_proof(self):
        self.lease.acquire()
        path = self.control / "coordinator.lock"
        path.rename(self.control / "coordinator.old")
        path.touch()
        with self.assertRaisesRegex(fence.FenceError, "COORDINATOR_LOCK_REPLACED"):
            self.probe()

    def test_changed_intent_refuses_new_proof(self):
        self.lease.acquire()
        fence.write_json(self.control / "active-intent.json", {"state": "HELD", "holder_instance": "other"})
        with self.assertRaisesRegex(fence.FenceError, "INTENT_CHANGED"):
            self.probe()

    def test_unsupported_lock_fails_without_fallback(self):
        with patch.object(fence.fcntl, "flock", side_effect=OSError(22, "Unsupported lock")):
            with self.assertRaises(OSError):
                self.lease.acquire()
        self.assertFalse(self.lease.held)
        self.assertIsNone(self.lease.own_fd)

    def test_stale_intent_prevents_second_holder_after_release(self):
        self.lease.acquire()
        self.lease.close()
        other = fence.FenceLease(self.root, self.control, self.session)
        with self.assertRaises(FileExistsError):
            other.acquire()
        self.assertIsNone(other.own_fd)

    def test_failed_intent_write_on_close_still_releases_all_locks(self):
        self.lease.acquire()
        with patch.object(self.lease, "_intent", side_effect=OSError(28, "disk full")):
            with self.assertRaises(OSError):
                self.lease.close()
        self.assertFalse(self.lease.held)
        self.assertIsNone(self.lease.own_fd)
        for name in fence.LOCK_NAMES:
            self.assertEqual(self.lock_attempt(self.root / name), "ACQUIRED")
        self.assertTrue((self.control / "active-intent.json").exists())

    def test_partial_acquire_journal_failure_preserves_original_and_releases_locks(self):
        (self.root / fence.LOCK_NAMES[-1]).unlink()
        original = self.lease._intent

        def journal(state, **kwargs):
            if state == "FAILED":
                raise OSError(28, "disk full")
            return original(state, **kwargs)

        with patch.object(self.lease, "_intent", side_effect=journal):
            with self.assertRaises(FileNotFoundError) as caught:
                self.lease.acquire()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertIsNone(self.lease.own_fd)
        self.assertEqual(self.lock_attempt(self.root / fence.LOCK_NAMES[0]), "ACQUIRED")

    def test_unlock_error_closes_remaining_owned_descriptors(self):
        self.lease.acquire()
        real_flock = fence.fcntl.flock

        def fail_unlock(fd, operation):
            if operation == fcntl.LOCK_UN:
                raise OSError(5, "lock IO error")
            return real_flock(fd, operation)

        with patch.object(fence.fcntl, "flock", side_effect=fail_unlock):
            with self.assertRaises(OSError):
                self.lease.close()
        self.assertEqual(self.lease.handles, [])
        self.assertIsNone(self.lease.own_fd)
        for name in fence.LOCK_NAMES:
            self.assertEqual(self.lock_attempt(self.root / name), "ACQUIRED")

    def test_holder_death_leaves_intent_and_cannot_answer_fresh_challenge(self):
        ready = CTX.Event()
        child = CTX.Process(target=hold_child, args=(str(self.root), str(self.control), self.session, ready))
        child.start()
        try:
            self.assertTrue(ready.wait(3))
            previous = (self.directory / "response.json").read_bytes()
            os.kill(child.pid, signal.SIGKILL)
            child.join(3)
            self.assertEqual(child.exitcode, -signal.SIGKILL)
            fence.write_json(self.directory / "challenge.json", {"schema": fence.CHALLENGE_SCHEMA,
                "session": self.session, "command": "PROBE", "challenge": "c" * 64})
            self.assertEqual((self.directory / "response.json").read_bytes(), previous)
            self.assertNotEqual(json.loads(previous)["challenge"], "c" * 64)
            self.assertTrue((self.control / "active-intent.json").exists())
            self.assertEqual(self.lock_attempt(self.root / fence.LOCK_NAMES[0]), "ACQUIRED")
            with self.assertRaises(FileExistsError):
                self.lease.acquire()
        finally:
            if child.is_alive():
                child.terminate()
                child.join(3)

    def test_waiting_legacy_writer_proves_why_separate_drain_is_required(self):
        self.lease.acquire()
        ready, finished = CTX.Event(), CTX.Event()
        child = CTX.Process(target=queued_writer, args=(str(self.root / fence.LOCK_NAMES[1]), ready, finished))
        child.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertFalse(finished.wait(0.1))
            self.assertFalse(self.probe()["external_writers_verified"])
            self.lease.close()
            self.assertTrue(finished.wait(3))
            child.join(3)
            self.assertEqual(child.exitcode, 0)
        finally:
            if child.is_alive():
                child.terminate()
                child.join(3)


if __name__ == "__main__":
    unittest.main()
