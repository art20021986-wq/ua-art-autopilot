import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from cloud.task_072 import writer as writer_mod
from cloud.task_072.tests.fixtures import make_synthetic_crm_db, cars_count, quick_check


class TestWriterContract(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "crm.db")
        make_synthetic_crm_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_legacy_description_alias_writes_condition_text(self):
        long_text = (
            "\u041f\u0440\u043e\u0434\u0430\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e VIN SYNTHVIN00030000000\n"
            "\u0426\u0456\u043d\u0430: 500 $\n\ud83d\ude97\ud83d\udd25\n\u0410\u0432\u0442\u043e \u0432 \u0432\u0456\u0434\u043c\u0456\u043d\u043d\u043e\u043c\u0443 \u0441\u0442\u0430\u043d\u0456."
        )
        result = writer_mod.save_description(
            self.conn, "UA-0003", "description", long_text, operation_id="chat1:msg1"
        )
        self.assertEqual(result.field_written, "condition_text")
        self.assertEqual(result.stored_text, long_text)
        readback = writer_mod.read_description_with_fallback(self.conn, writer_mod.build_allowlist(self.conn), "UA-0003")
        self.assertEqual(readback, long_text)

    def test_diag_text_never_written(self):
        with self.assertRaises(writer_mod.ValidationError):
            writer_mod.save_description(self.conn, "UA-0001", "diag_text", "hack", "chat2:msg2")

    def test_unknown_field_rejected(self):
        with self.assertRaises(writer_mod.ValidationError):
            writer_mod.save_description(self.conn, "UA-0001", "not_a_real_field", "x", "chat3:msg3")

    def test_empty_text_rejected(self):
        with self.assertRaises(writer_mod.ValidationError):
            writer_mod.save_description(self.conn, "UA-0001", "description", "", "chat4:msg4")

    def test_too_long_rejected(self):
        too_long = "a" * 12001
        with self.assertRaises(writer_mod.ValidationError):
            writer_mod.save_description(self.conn, "UA-0001", "description", too_long, "chat5:msg5")

    def test_nul_bytes_stripped(self):
        text = "line1\x00line2"
        result = writer_mod.save_description(self.conn, "UA-0001", "description", text, "chat6:msg6")
        self.assertNotIn("\x00", result.stored_text)

    def test_max_len_boundary_12000_passes(self):
        text = "a" * 12000
        result = writer_mod.save_description(self.conn, "UA-0002", "description", text, "chat7:msg7")
        self.assertEqual(len(result.stored_text), 12000)

    def test_no_new_card_created_on_unknown_id(self):
        before = cars_count(self.db_path)
        with self.assertRaises(writer_mod.ValidationError):
            writer_mod.save_description(self.conn, "UA-9912-NOT-YET", "description", "text", "chat8:msg8")
        after = cars_count(self.db_path)
        self.assertEqual(before, after)

    def test_future_card_gets_same_path_once_it_exists(self):
        self.conn.execute(
            "INSERT INTO cars (card_id, vin, condition_text, description, diag_text, price) "
            "VALUES ('UA-9912', 'X', NULL, NULL, NULL, '500 $')"
        )
        self.conn.commit()
        result = writer_mod.save_description(self.conn, "UA-9912", "description", "future card text", "chat9:msg9")
        self.assertEqual(result.card_id, "UA-9912")

    def test_all_11_existing_cards_isolated(self):
        for i in range(1, 12):
            card_id = f"UA-{i:04d}"
            unique_text = f"description for {card_id} only"
            writer_mod.save_description(self.conn, card_id, "description", unique_text, f"chatX:{i}")
        for i in range(1, 12):
            card_id = f"UA-{i:04d}"
            expected = f"description for {card_id} only"
            actual = writer_mod.read_field(self.conn, writer_mod.build_allowlist(self.conn), card_id, "condition_text")
            self.assertEqual(actual, expected)
        self.assertEqual(cars_count(self.db_path), 11)
        self.assertEqual(quick_check(self.db_path), "ok")

    def test_readback_verified_or_raises(self):
        result = writer_mod.save_description(self.conn, "UA-0004", "description", "verified text", "chat10:msg10")
        self.assertEqual(result.stored_text, "verified text")

    def test_confirm_message_short(self):
        result = writer_mod.save_description(self.conn, "UA-0005", "description", "x" * 5000, "chat11:msg11")
        msg = writer_mod.confirm_message(result)
        self.assertLessEqual(len(msg), 900)

    def test_safe_error_message_no_traceback(self):
        try:
            writer_mod.save_description(self.conn, "UA-0006", "diag_text", "x", "chat12:msg12")
        except Exception as exc:  # noqa: BLE001
            msg = writer_mod.safe_error_message(exc)
            self.assertNotIn("Traceback", msg)
            self.assertNotIn("/home/", msg)
            self.assertNotIn("locked", msg.lower())


if __name__ == "__main__":
    unittest.main()
