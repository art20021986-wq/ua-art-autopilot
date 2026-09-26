"""P4-SAFETY-001 regressions using the exact extracted private media helper."""
import json
from pathlib import Path
import sqlite3
import types
import unittest
from unittest.mock import patch

import mutation_recovery as recovery
import test_scoped_recovery as fixtures


class ExceptionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RecoveryTests(methodName="test_real_video_path_success_includes_media_and_cache")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.journal = recovery.MediaJournal(self.f.database, "UA-0007")
        self.journal.evidence_directory = self.f.root / "journal"
        self.journal.evidence_directory.mkdir()
        self.opened = []

    def connections(self, mode="normal"):
        opened = self.opened
        class Connection(sqlite3.Connection):
            def commit(self):
                if mode == "commit-before":
                    raise sqlite3.OperationalError("INJECTED_COMMIT_FAILURE")
                result = super().commit()
                if mode == "commit-after":
                    raise sqlite3.OperationalError("INJECTED_LOST_COMMIT_ACK")
                return result
        def connect(*args, **kwargs):
            con = sqlite3.connect(*args, factory=Connection, **kwargs)
            opened.append(con)
            return con
        self.f.ns["_s163"] = types.SimpleNamespace(connect=connect, Row=sqlite3.Row)

    def assert_closed_and_unlocked(self):
        for con in self.opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")
        con = sqlite3.connect(self.f.database, timeout=0.1)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.rollback()
        finally:
            con.close()

    def call_helper(self, code="UA-0007"):
        with self.f.ns["_ua114_publication_fence"](), self.journal.active():
            return self.f.ns["_v163_status"](code, "rejected", "ready")

    def test_evidence_error_propagates_rolls_back_and_closes(self):
        self.connections()
        with patch.object(recovery, "write_private_new", side_effect=OSError("INJECTED_JOURNAL_IO")):
            with self.assertRaisesRegex(OSError, "INJECTED_JOURNAL_IO"):
                self.call_helper()
        self.assert_closed_and_unlocked()
        self.assertEqual(self.f.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "ready")

    def test_commit_failure_rolls_back_and_closes(self):
        self.connections("commit-before")
        with self.assertRaisesRegex(sqlite3.OperationalError, "INJECTED_COMMIT_FAILURE"):
            self.call_helper()
        self.assert_closed_and_unlocked()
        self.assertEqual(self.journal.restore(), [])

    def test_lost_commit_ack_closes_and_retains_recovery_intent(self):
        self.connections("commit-after")
        with self.assertRaisesRegex(sqlite3.OperationalError, "INJECTED_LOST_COMMIT_ACK"):
            self.call_helper()
        self.assert_closed_and_unlocked()
        self.assertEqual(self.f.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "rejected")
        self.assertEqual(self.journal.restore(), [])
        self.assertEqual(self.f.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "ready")

    def test_missing_vehicle_is_failure_and_closes(self):
        self.connections()
        with self.assertRaisesRegex(RuntimeError, "MEDIA_STATUS_ROW_NOT_FOUND"):
            self.call_helper("UA-0099")
        self.assert_closed_and_unlocked()

    def test_begin_snapshot_failure_closes(self):
        self.connections()
        with patch.object(recovery, "_rows", side_effect=RuntimeError("INJECTED_SNAPSHOT_ERROR")):
            with self.assertRaisesRegex(RuntimeError, "INJECTED_SNAPSHOT_ERROR"):
                self.call_helper()
        self.assert_closed_and_unlocked()

    def test_success_closes_before_rebuild(self):
        self.connections()
        self.call_helper()
        self.assert_closed_and_unlocked()
        self.assertEqual(self.f.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "rejected")

    def test_outer_mutation_recovers_on_journal_io_failure(self):
        self.connections()
        self.f.seed_video()
        before = self.f.card()
        cache = json.loads(self.f.cache.read_text())
        original = recovery.write_private_new
        injected = []
        def write(path, data):
            if Path(path).name.startswith("media-commit-"):
                injected.append(True)
                raise OSError("INJECTED_JOURNAL_IO")
            return original(path, data)
        with patch.object(recovery, "write_private_new", write):
            result = self.f.ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual(injected, [True])
        self.assertEqual(result["rollback_conflicts"], [])
        self.assert_closed_and_unlocked()
        self.assertEqual(self.f.card(), before)
        self.assertEqual(json.loads(self.f.cache.read_text()), cache)
        self.assertEqual((self.f.video / "UA-0007.mp4").read_bytes(), b"video-original")


if __name__ == "__main__":
    unittest.main()
