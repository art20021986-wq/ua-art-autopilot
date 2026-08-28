"""
Stub Telegram call-path tests. These exercise a synthetic 'catch_message'-style
call path (button -> long text -> read-back) built on top of writer.py/queue_sidecar.py.
They do NOT exercise the real cars_ui.py/db.py (not available to this worker; see
GATE_A_REPORT.md).
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from cloud.task_072 import writer as writer_mod
from cloud.task_072 import queue_sidecar
from cloud.task_072.tests.fixtures import make_synthetic_crm_db, BuggyReferenceWaitState


class FakeBotController:
    """Synthetic reference implementation of the corrected call path:
    button('\U0001f4dd \u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435') -> apply_value -> set_field -> save_description.
    car_wait is only cleared AFTER a confirmed commit+read-back.
    """

    def __init__(self, crm_conn, qconn):
        self.crm_conn = crm_conn
        self.qconn = qconn
        self.user_data = {}

    def press_description_button(self, card_id: str):
        self.user_data["car_wait"] = {"card_id": card_id, "field": "description"}
        return "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435"

    def catch_message(self, chat_id: str, message_id: str, text: str, simulate_lock: bool = False):
        wait = self.user_data.get("car_wait")
        if not wait:
            return "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443 \u0441\u043d\u0430\u0447\u0430\u043b\u0430"
        card_id = wait["card_id"]
        field = wait["field"]
        operation_id = queue_sidecar.make_operation_id(chat_id, message_id)
        try:
            if simulate_lock:
                raise sqlite3.OperationalError("database is locked")
            result = writer_mod.save_description(self.crm_conn, card_id, field, text, operation_id)
            self.user_data.pop("car_wait", None)  # cleared only AFTER confirmed commit+read-back
            return writer_mod.confirm_message(result)
        except (sqlite3.OperationalError, writer_mod.WriteBudgetExceeded):
            queue_sidecar.enqueue(self.qconn, chat_id, message_id, card_id, field, text)
            # car_wait intentionally NOT popped: user can retry without re-entering the card.
            return "\u041f\u0440\u0438\u043d\u044f\u0442\u043e, \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e"


class TestBaselineReproducesDefect(unittest.TestCase):
    def test_baseline_loses_car_wait_on_lock(self):
        baseline = BuggyReferenceWaitState()
        baseline.user_data["car_wait"] = {"card_id": "UA-0001"}
        with self.assertRaises(sqlite3.OperationalError):
            baseline.catch_message("UA-0001", "text", simulate_lock=True)
        # Defect reproduced: wait state already gone even though the write failed.
        self.assertIsNone(baseline.user_data.get("car_wait"))


class TestPatchedCallPath(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.crm_path = os.path.join(self.tmpdir, "crm.db")
        self.queue_path = os.path.join(self.tmpdir, "queue.db")
        make_synthetic_crm_db(self.crm_path)
        self.crm_conn = sqlite3.connect(self.crm_path, timeout=5)
        self.qconn = queue_sidecar.open_queue(self.queue_path)
        self.bot = FakeBotController(self.crm_conn, self.qconn)

    def tearDown(self):
        self.crm_conn.close()
        self.qconn.close()

    def test_button_then_long_text_saves_and_reads_back(self):
        self.bot.press_description_button("UA-0007")
        long_text = (
            "\u041f\u0440\u043e\u0434\u0430\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e!\n"
            "VIN: SYNTHVIN00070000000\n\u0426\u0456\u043d\u0430: 500 $\n\ud83d\ude97\n"
            "\u0414\u0440\u0443\u0433\u0430 \u0441\u0442\u0440\u043e\u043a\u0430 \u0442\u0435\u043a\u0441\u0442\u0443."
        )
        reply = self.bot.catch_message("chatA", "msg1", long_text)
        self.assertIn("\u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e", reply)
        stored = writer_mod.read_field(self.crm_conn, writer_mod.build_allowlist(self.crm_conn), "UA-0007", "condition_text")
        self.assertEqual(stored, long_text)
        audit_count = self.crm_conn.execute(
            "SELECT COUNT(*) FROM audit WHERE card_id = ?", ("UA-0007",)
        ).fetchone()[0]
        self.assertEqual(audit_count, 1)

    def test_lock_does_not_lose_car_wait_and_retry_succeeds(self):
        self.bot.press_description_button("UA-0008")
        reply1 = self.bot.catch_message("chatB", "msg1", "text under lock", simulate_lock=True)
        self.assertIn("\u041f\u0440\u0438\u043d\u044f\u0442\u043e", reply1)
        self.assertIsNotNone(self.bot.user_data.get("car_wait"))  # wait state preserved
        # user retries without re-selecting the card
        reply2 = self.bot.catch_message("chatB", "msg2", "text after retry")
        self.assertIn("\u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e", reply2)
        stored = writer_mod.read_field(self.crm_conn, writer_mod.build_allowlist(self.crm_conn), "UA-0008", "condition_text")
        self.assertEqual(stored, "text after retry")

    def test_no_open_card_refuses_to_create_one(self):
        reply = self.bot.catch_message("chatC", "msg1", "orphan text, no card open")
        self.assertIn("\u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443", reply)


if __name__ == "__main__":
    unittest.main()
