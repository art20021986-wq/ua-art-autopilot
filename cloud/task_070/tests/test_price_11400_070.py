"""Gate A check: price=11400 write + read-back <=2s, exactly one
price_history row, no traceback surfaced.
"""
import os
import sqlite3
import sys
import tempfile
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


def test_price_11400_fast_and_single_history():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "crm.db")
        queue_path = os.path.join(d, "queue.jsonl")
        _make_db(db_path)
        w = CardFieldWriter070(db_path, queue_path)

        t0 = time.monotonic()
        res = w.write_price("UA-0009", 11400, "USD")
        dt = time.monotonic() - t0

        assert res.ok is True
        assert res.queued is False
        assert dt <= 2.0, f"write took {dt}s"

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT price FROM cards WHERE card_id='UA-0009'").fetchone()
        assert row[0] == 11400

        hist = conn.execute("SELECT COUNT(*) FROM price_history WHERE card_id='UA-0009'").fetchone()[0]
        assert hist == 1
        conn.close()
