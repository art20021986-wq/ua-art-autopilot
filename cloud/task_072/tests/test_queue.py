import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from cloud.task_072 import queue_sidecar
from cloud.task_072 import writer as writer_mod
from cloud.task_072.tests.fixtures import make_synthetic_crm_db


class TestQueueSidecar(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.crm_path = os.path.join(self.tmpdir, "crm.db")
        self.queue_path = os.path.join(self.tmpdir, "queue.db")
        make_synthetic_crm_db(self.crm_path)
        self.qconn = queue_sidecar.open_queue(self.queue_path)
        self.crm_conn = sqlite3.connect(self.crm_path, timeout=5)

    def tearDown(self):
        self.qconn.close()
        self.crm_conn.close()

    def test_replay_same_chat_message_is_idempotent(self):
        r1 = queue_sidecar.enqueue(self.qconn, "111", "222", "UA-0001", "description", "first text")
        r2 = queue_sidecar.enqueue(self.qconn, "111", "222", "UA-0001", "description", "replayed identical send")
        self.assertFalse(r1.already_existed)
        self.assertTrue(r2.already_existed)
        queue_sidecar.drain_all(self.qconn, self.crm_conn)
        val = writer_mod.read_field(self.crm_conn, writer_mod.build_allowlist(self.crm_conn), "UA-0001", "condition_text")
        self.assertEqual(val, "first text")

    def test_last_intended_wins(self):
        queue_sidecar.enqueue(self.qconn, "1", "1", "UA-0002", "description", "OLD TEXT")
        queue_sidecar.enqueue(self.qconn, "1", "2", "UA-0002", "description", "NEW TEXT")
        queue_sidecar.drain_all(self.qconn, self.crm_conn)
        val = writer_mod.read_field(self.crm_conn, writer_mod.build_allowlist(self.crm_conn), "UA-0002", "condition_text")
        self.assertEqual(val, "NEW TEXT")

    def test_crash_after_crm_commit_before_ack_is_idempotent(self):
        queue_sidecar.enqueue(self.qconn, "5", "5", "UA-0003", "description", "already applied text")
        # Simulate CRM commit having already happened out-of-band (crash before ack):
        writer_mod.save_description(self.crm_conn, "UA-0003", "description", "already applied text", "5:5-shadow")
        handled = queue_sidecar.drain_one(self.qconn, self.crm_conn)
        self.assertIsNotNone(handled)
        row = self.qconn.execute(
            "SELECT status FROM description_ops WHERE operation_id = ?", ("5:5",)
        ).fetchone()
        self.assertEqual(row[0], "APPLIED")

    def test_100_sequential_last_wins_no_loss(self):
        for i in range(100):
            queue_sidecar.enqueue(self.qconn, "9", str(i), "UA-0004", "description", f"text number {i}")
        applied = queue_sidecar.drain_all(self.qconn, self.crm_conn)
        self.assertEqual(applied, 100)
        val = writer_mod.read_field(self.crm_conn, writer_mod.build_allowlist(self.crm_conn), "UA-0004", "condition_text")
        self.assertEqual(val, "text number 99")

    def test_concurrent_enqueue_then_drain_no_duplicates(self):
        def enqueue_batch(offset):
            local_qconn = sqlite3.connect(self.queue_path, timeout=5)
            for i in range(10):
                queue_sidecar.enqueue(local_qconn, "7", str(offset + i), "UA-0005", "description", f"val {offset + i}")
            local_qconn.close()

        threads = [threading.Thread(target=enqueue_batch, args=(i * 10,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = self.qconn.execute("SELECT COUNT(*) FROM description_ops").fetchone()[0]
        self.assertEqual(total, 50)
        applied = queue_sidecar.drain_all(self.qconn, self.crm_conn)
        self.assertEqual(applied, 50)


if __name__ == "__main__":
    unittest.main()
