"""Gate A matrix: 100 operations each for price, mileage, stage, container,
deadline -- across two independent cards to check no cross-card writes and
no losses/duplicates.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate"))
from db_writer_070 import CardFieldWriter070  # noqa: E402


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cards(card_id TEXT PRIMARY KEY, price INTEGER, currency TEXT, mileage INTEGER, stage TEXT, container TEXT, deadline TEXT, updated_at REAL)")
    conn.execute("CREATE TABLE price_history(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, price INTEGER, currency TEXT, changed_at REAL)")
    conn.execute("CREATE TABLE log_action(id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, field TEXT, value TEXT, at REAL)")
    conn.execute("INSERT INTO cards(card_id, price, currency) VALUES ('UA-0009', 0, 'USD')")
    conn.execute("INSERT INTO cards(card_id, price, currency) VALUES ('UA-XXXX', 0, 'USD')")
    conn.commit()
    conn.close()


def test_100x_each_field_no_loss_no_dup_no_crosscard():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "crm.db")
        queue_path = os.path.join(d, "queue.jsonl")
        _make_db(db_path)
        w = CardFieldWriter070(db_path, queue_path)

        for i in range(1, 101):
            r = w.write_price("UA-0009", 10000 + i, "USD")
            assert r.ok
            r = w.write_field("UA-0009", "mileage", i * 1000)
            assert r.ok
            r = w.write_field("UA-0009", "stage", f"stage_{i}")
            assert r.ok
            r = w.write_field("UA-0009", "container", f"cont_{i}")
            assert r.ok
            r = w.write_field("UA-0009", "deadline", f"2026-01-{(i % 28) + 1:02d}")
            assert r.ok
            # sanity write on other card to check isolation
            r2 = w.write_field("UA-XXXX", "mileage", i)
            assert r2.ok

        conn = sqlite3.connect(db_path)
        price, mileage, stage, container, deadline = conn.execute(
            "SELECT price, mileage, stage, container, deadline FROM cards WHERE card_id='UA-0009'"
        ).fetchone()
        assert price == 10100
        assert mileage == 100000
        assert stage == "stage_100"
        assert container == "cont_100"

        hist_count = conn.execute("SELECT COUNT(*) FROM price_history WHERE card_id='UA-0009'").fetchone()[0]
        assert hist_count == 100

        other_mileage = conn.execute("SELECT mileage FROM cards WHERE card_id='UA-XXXX'").fetchone()[0]
        assert other_mileage == 100

        other_price = conn.execute("SELECT price FROM cards WHERE card_id='UA-XXXX'").fetchone()[0]
        assert other_price == 0, "cross-card contamination detected"
        conn.close()
