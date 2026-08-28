"""Gate A: writer must never surface 'database is locked' or a raw
traceback string to the caller/bot layer.
"""
import os
import sqlite3
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate"))
from db_writer_070 import CardFieldWriter070  # noqa: E402


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cards(card_id TEXT PRIMARY KEY, price INTEGER, currency TEXT, mileage INTEGER, stage TEXT, container TEXT, deadline TEXT, updated_at REAL)")
    conn.execute("CREATE TABLE price_history(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, price INTEGER, currency TEXT, changed_at REAL)")
    conn.execute("CREATE TABLE log_action(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, field TEXT, value TEXT, at REAL)")
    conn.execute("INSERT INTO cards(card_id, price, currency) VALUES ('UA-0009', 0, 'USD')")
    conn.commit()
    conn.close()


def test_no_locked_string_no_exception_under_contention():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "crm.db")
        queue_path = os.path.join(d, "queue.jsonl")
        _make_db(db_path)
        w = CardFieldWriter070(db_path, queue_path)

        lock_conn = sqlite3.connect(db_path, timeout=0.1)
        lock_conn.execute("BEGIN EXCLUSIVE")

        try:
            res = w.write_price("UA-0009", 11400, "USD")
            assert res.error is None
            assert res.ok is True
            # simulate the bot-facing message builder
            user_message = "Цена сохранена" if res.ok else "Ошибка"
            assert "locked" not in user_message.lower()
            assert "traceback" not in user_message.lower()
        finally:
            lock_conn.execute("COMMIT")
            lock_conn.close()
