"""Gate A: simulate a real SQLite lock and verify fast response + FIFO
queue drain to zero after the lock is released.
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


def test_lock_then_fifo_drain_to_zero():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "crm.db")
        queue_path = os.path.join(d, "queue.jsonl")
        _make_db(db_path)
        w = CardFieldWriter070(db_path, queue_path)

        lock_conn = sqlite3.connect(db_path, timeout=0.1)
        lock_conn.execute("BEGIN EXCLUSIVE")

        release_event = threading.Event()

        def _release_later():
            release_event.wait(0.3)
            lock_conn.execute("COMMIT")
            lock_conn.close()

        t = threading.Thread(target=_release_later)
        t.start()

        t0 = time.monotonic()
        res = w.write_price("UA-0009", 11400, "USD")
        dt = time.monotonic() - t0

        assert res.ok is True
        assert res.queued is True, "expected queued write while locked"
        assert dt <= 1.5, f"fast-fail path too slow: {dt}s"

        release_event.set()
        t.join()

        # allow the exclusive lock to fully release, then drain
        for _ in range(20):
            applied = w.drain_queue()
            if applied and w.queue.size() == 0:
                break
            time.sleep(0.1)

        assert w.queue.size() == 0, "queue must drain to zero after lock release"

        conn = sqlite3.connect(db_path)
        price = conn.execute("SELECT price FROM cards WHERE card_id='UA-0009'").fetchone()[0]
        assert price == 11400
        hist = conn.execute("SELECT COUNT(*) FROM price_history WHERE card_id='UA-0009'").fetchone()[0]
        assert hist == 1
        conn.close()
