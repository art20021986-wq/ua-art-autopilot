"""Gate A: after a simulated process restart, queued items and their
eventual application must survive (durability check).
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate"))
from db_writer_070 import CardFieldWriter070, DurableQueue070  # noqa: E402


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cards(card_id TEXT PRIMARY KEY, price INTEGER, currency TEXT, mileage INTEGER, stage TEXT, container TEXT, deadline TEXT, updated_at REAL)")
    conn.execute("CREATE TABLE price_history(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, price INTEGER, currency TEXT, changed_at REAL)")
    conn.execute("CREATE TABLE log_action(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, field TEXT, value TEXT, at REAL)")
    conn.execute("INSERT INTO cards(card_id, price, currency) VALUES ('UA-0009', 0, 'USD')")
    conn.commit()
    conn.close()


def test_queue_survives_process_restart_simulation():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "crm.db")
        queue_path = os.path.join(d, "queue.jsonl")
        _make_db(db_path)

        q1 = DurableQueue070(queue_path)
        q1.enqueue({"kind": "field", "card_id": "UA-0009", "field": "mileage", "value": 50000})
        assert q1.size() == 1

        # Simulate process restart: new object, same file
        w2 = CardFieldWriter070(db_path, queue_path)
        assert w2.queue.size() == 1

        applied = w2.drain_queue()
        assert applied == 1
        assert w2.queue.size() == 0

        conn = sqlite3.connect(db_path)
        mileage = conn.execute("SELECT mileage FROM cards WHERE card_id='UA-0009'").fetchone()[0]
        assert mileage == 50000
        conn.close()
