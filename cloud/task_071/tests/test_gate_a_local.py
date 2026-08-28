"""TASK 071 offline test suite — corrects TASK 070's schema defect.

Uses ONLY real field/table names confirmed in
cloud/task_070/evidence/real_context.json (cars.price_uah, cars.mileage_km,
cars.status, cars.sea_container, cars.days_to_kyiv, cars.eta_manual, and the
audit table) — never the invented probeg/etap/kontainer/srok or
cards/price_history-as-table/log_action names used by TASK 070.

Run with: pytest cloud/task_071/tests/test_gate_a_local.py -q
"""
from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

from cloud.task_071.writer import apply_field_update, read_back, RejectedField
from cloud.task_071.durable_queue import open_queue_db, enqueue, drain
from cloud.task_071.controller import SYNTHETIC_SCHEMA, _seed


@pytest.fixture()
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "crm.db"))
    _seed(c)
    yield c
    c.close()


def test_price_11400_single_history_single_audit(conn):
    op = str(uuid.uuid4())
    apply_field_update(conn, "cars", 3, "price_uah", 11400, op)
    assert read_back(conn, "cars", "price_uah", 3) == 11400
    history = json.loads(conn.execute("SELECT price_history FROM cars WHERE id=3").fetchone()[0])
    assert len(history) == 1
    audit_rows = conn.execute("SELECT COUNT(*) FROM audit WHERE operation_id=?", (op,)).fetchone()[0]
    assert audit_rows == 1


def test_idempotent_replay_no_duplicate(conn):
    op = str(uuid.uuid4())
    apply_field_update(conn, "cars", 3, "price_uah", 15000, op)
    apply_field_update(conn, "cars", 3, "price_uah", 15000, op)
    history = json.loads(conn.execute("SELECT price_history FROM cars WHERE id=3").fetchone()[0])
    assert len(history) == 1


@pytest.mark.parametrize("field,value", [
    ("mileage_km", 42000),
    ("status", "delivered"),
    ("sea_container", "MSCU1234567"),
    ("days_to_kyiv", 5),
    ("eta_manual", "2026-09-01"),
    ("stage", "customs"),  # legacy alias -> status
])
def test_scalar_field_smoke(conn, field, value):
    op = str(uuid.uuid4())
    apply_field_update(conn, "cars", 4, field, value, op)
    real_field = "status" if field == "stage" else field
    assert str(read_back(conn, "cars", real_field, 4)) == str(value)


def test_malicious_table_rejected(conn):
    with pytest.raises(RejectedField):
        apply_field_update(conn, "cars; DROP TABLE cars;--", 1, "price_uah", 1, str(uuid.uuid4()))


def test_unknown_field_rejected(conn):
    with pytest.raises(RejectedField):
        apply_field_update(conn, "cars", 1, "password", "x", str(uuid.uuid4()))


def test_ua0009_untouched_by_other_card_writes(conn):
    before = conn.execute("SELECT * FROM cars WHERE ua_code='UA-0009'").fetchone()
    apply_field_update(conn, "cars", 2, "price_uah", 99999, str(uuid.uuid4()))
    after = conn.execute("SELECT * FROM cars WHERE ua_code='UA-0009'").fetchone()
    assert before == after


def test_cars_count_stable_and_quick_check_ok(conn):
    apply_field_update(conn, "cars", 1, "status", "x", str(uuid.uuid4()))
    assert conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 11
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_bulk_100_price_writes_no_loss_no_dupe(conn):
    for i in range(100):
        op = str(uuid.uuid4())
        apply_field_update(conn, "cars", 5, "price_uah", 30000 + i, op)
    assert read_back(conn, "cars", "price_uah", 5) == 30099
    history = json.loads(conn.execute("SELECT price_history FROM cars WHERE id=5").fetchone()[0])
    assert len(history) == 100


def test_queue_fallback_and_crash_safe_drain(tmp_path, conn):
    qconn = open_queue_db(tmp_path / "queue.db")
    op = str(uuid.uuid4())
    enqueue(qconn, "cars", 6, "mileage_km", 7777, op)
    drain(qconn, conn, audit_check_conn=conn)
    assert read_back(conn, "cars", "mileage_km", 6) == 7777
    # simulate crash-restart re-enqueue of same op_id
    enqueue(qconn, "cars", 6, "mileage_km", 7777, op)
    results = drain(qconn, conn, audit_check_conn=conn)
    assert all(r["status"] == "duplicate_ignored" for r in results if r.get("operation_id") == op)
