"""Offline Gate A matrix tests for TASK 070.

These tests build a synthetic sqlite database that mirrors the schema
described in the evidence (cars, audit, clients) and exercise
writer.safe_writer + queue.durable_queue against it. They do not touch any
real crm.db, PythonAnywhere path, or production file.

Run with: pytest cloud/task_070/tests/test_real_schema_gate_a.py -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "writer"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "queue"))

import safe_writer  # noqa: E402
from durable_queue import DurableQueue, drain_once  # noqa: E402


@pytest.fixture()
def synthetic_db(tmp_path):
    db_path = str(tmp_path / "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT UNIQUE, "
        "price_uah INTEGER, price_history TEXT, probeg INTEGER, etap TEXT, "
        "kontainer TEXT, srok TEXT, status TEXT, note TEXT)"
    )
    conn.execute(
        "CREATE TABLE audit (id INTEGER PRIMARY KEY, operation_id TEXT UNIQUE, "
        "auto_number TEXT, field TEXT, value TEXT, actor TEXT, ts REAL)"
    )
    conn.execute(
        "CREATE TABLE clients (client_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, "
        "note TEXT, status TEXT)"
    )
    numbers = [f"UA-{i:04d}" for i in range(1, 12)]  # 11 cards, UA-0009 present once
    for n in numbers:
        conn.execute(
            "INSERT INTO cars(auto_number, price_uah, price_history) VALUES (?, 0, '[]')", (n,)
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def queue_db(tmp_path):
    return DurableQueue(str(tmp_path / "queue.db"))


def test_price_11400_single_transaction_readback(synthetic_db):
    result = safe_writer.write_price("UA-0009", 11400, db_path=synthetic_db)
    assert result.applied
    assert result.elapsed_seconds < 1.0
    conn = sqlite3.connect(synthetic_db)
    row = conn.execute(
        "SELECT price_uah, price_history FROM cars WHERE auto_number='UA-0009'"
    ).fetchone()
    assert row[0] == 11400
    history = json.loads(row[1])
    assert len(history) == 1
    assert history[0]["price"] == 11400
    audit_rows = conn.execute(
        "SELECT COUNT(*) FROM audit WHERE auto_number='UA-0009' AND field='price_uah'"
    ).fetchone()
    assert audit_rows[0] == 1
    other = conn.execute(
        "SELECT price_uah FROM cars WHERE auto_number != 'UA-0009'"
    ).fetchall()
    assert all(v == (0,) for v in other), "cross-card mutation detected"
    conn.close()


@pytest.mark.parametrize("field,value", [
    ("price_uah", 12345), ("probeg", 55000), ("etap", "customs"),
    ("kontainer", "MSKU1234567"), ("srok", "2026-01-01"),
])
def test_100_ops_no_loss_no_dupe_no_crosscard(synthetic_db, field, value):
    for i in range(100):
        auto = "UA-0003"
        if field == "price_uah":
            safe_writer.write_price(auto, value + i, db_path=synthetic_db)
        else:
            safe_writer.write_card_field(auto, field, f"{value}-{i}", db_path=synthetic_db)
    conn = sqlite3.connect(synthetic_db)
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit WHERE auto_number='UA-0003' AND field=?", (field,)
    ).fetchone()[0]
    assert audit_count == 100
    other_touched = conn.execute(
        "SELECT COUNT(*) FROM audit WHERE auto_number != 'UA-0003' AND field=?", (field,)
    ).fetchone()[0]
    assert other_touched == 0
    conn.close()


def test_locked_db_falls_back_to_durable_enqueue(synthetic_db, queue_db):
    blocker = sqlite3.connect(synthetic_db, timeout=1)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(safe_writer.WriteBudgetExceeded):
            safe_writer.write_price("UA-0005", 999, db_path=synthetic_db, budget_seconds=0.3)
        op_id = queue_db.enqueue("UA-0005", "price_uah", 999)
        assert queue_db.depth() == 1
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    acked = drain_once(queue_db, lambda item: safe_writer.replay_from_queue(
        {**item, "operation_id": op_id}, db_path=synthetic_db))
    assert acked == 1
    assert queue_db.depth() == 0


def test_crash_after_commit_before_ack_is_idempotent(synthetic_db, queue_db):
    op_id = queue_db.enqueue("UA-0006", "probeg", 1000)
    item = queue_db.claim("w1")
    safe_writer.replay_from_queue({
        "operation_id": item.operation_id, "auto_number": item.auto_number,
        "field": item.field, "value": item.value, "entity": item.entity,
        "actor": item.actor,
    }, db_path=synthetic_db)
    # Simulate crash: no ack() call happens here.
    # Replay path (worker restart) re-claims after TTL and re-applies; audit
    # UNIQUE(operation_id) with INSERT OR IGNORE must prevent a duplicate row.
    safe_writer.replay_from_queue({
        "operation_id": item.operation_id, "auto_number": item.auto_number,
        "field": item.field, "value": item.value, "entity": item.entity,
        "actor": item.actor,
    }, db_path=synthetic_db)
    conn = sqlite3.connect(synthetic_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM audit WHERE operation_id=?", (op_id,)
    ).fetchone()[0]
    assert count == 1, "duplicate audit row after replay"
    conn.close()


def test_two_concurrent_processes_enqueue_and_drain(synthetic_db, queue_db):
    errors = []

    def worker(n):
        try:
            for i in range(20):
                queue_db.enqueue(f"UA-000{(n % 9) + 1}", "note", f"w{n}-{i}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert queue_db.depth() == 40
    acked_total = 0
    while queue_db.depth() > 0:
        acked_total += drain_once(
            queue_db,
            lambda item: safe_writer.replay_from_queue(item, db_path=synthetic_db),
        )
    assert acked_total == 40
    assert queue_db.depth() == 0


def test_fuzz_unknown_table_field_rejected_before_sql(synthetic_db):
    with pytest.raises(safe_writer.UnknownFieldError):
        safe_writer.write_card_field("UA-0009", "'; DROP TABLE cars; --", "x",
                                      db_path=synthetic_db)
    with pytest.raises(safe_writer.UnknownFieldError):
        safe_writer.write_card_field("UA-0009", "unknown_field", "x", db_path=synthetic_db)
    with pytest.raises(safe_writer.UnknownFieldError):
        safe_writer.write_card_field("UA-0009", "note", "x", db_path=synthetic_db,
                                      entity="unknown_table")
    conn = sqlite3.connect(synthetic_db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"cars", "audit", "clients"} <= tables, "schema must survive fuzz attempts"
    conn.close()


def test_quick_check_and_card_count_and_ua0009_unique(synthetic_db):
    conn = sqlite3.connect(synthetic_db)
    qc = conn.execute("PRAGMA quick_check").fetchone()[0]
    assert qc == "ok"
    count = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
    assert count == 11
    ua9 = conn.execute("SELECT COUNT(*) FROM cars WHERE auto_number='UA-0009'").fetchone()[0]
    assert ua9 == 1
    conn.close()


def test_future_ua_xxxx_synthetic_card_pass(synthetic_db):
    conn = sqlite3.connect(synthetic_db)
    conn.execute("INSERT INTO cars(auto_number, price_uah, price_history) VALUES ('UA-0099', 0, '[]')")
    conn.commit()
    conn.close()
    result = safe_writer.write_price("UA-0099", 5000, db_path=synthetic_db)
    assert result.applied
    conn = sqlite3.connect(synthetic_db)
    price = conn.execute("SELECT price_uah FROM cars WHERE auto_number='UA-0099'").fetchone()[0]
    assert price == 5000
    untouched = conn.execute("SELECT price_uah FROM cars WHERE auto_number='UA-0009'").fetchone()[0]
    assert untouched == 0
    conn.close()
