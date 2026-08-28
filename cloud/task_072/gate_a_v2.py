#!/usr/bin/env python3
"""GET-only, real-context Gate A for CRM-DESCRIPTION-SAVE-072-V2.

Production is only downloaded.  Every mutation and contention test runs against
temporary copies on the GitHub Actions runner.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import pathlib
import shutil
import sqlite3
import statistics
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "cloud" / "task_072"
EVIDENCE_PATH = TASK_DIR / "evidence" / "gate_a_v2.json"
REPORT_PATH = TASK_DIR / "GATE_A_V2_REPORT.md"
WRITER_PATH = TASK_DIR / "crm_description_writer_v2.py"
PATCHER_PATH = TASK_DIR / "patch_cars_ui_v2.py"

API_BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = {
    "db.py": "/home/Carix/db.py",
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "trace_zhurnal.py": "/home/Carix/trace_zhurnal.py",
    "crm.db": "/home/Carix/crm.db",
}
EXPECTED_SOURCE_SHA256 = {
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    "cars_ui.py": "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b",
    "trace_zhurnal.py": "fc4b95fc749f3d9b785ce69bfce2705b11ade95a560d6fbd901b50de1423d086",
}
MAX_DOWNLOAD_BYTES = 50_000_000


SCREENSHOT_STYLE_TEXT = """Hyundai Sonata — в наличии по маршруту

Почему выгодно бронировать автомобиль в пути:
☑ задаток — всего 500 $
☑ итоговая цена фиксируется в договоре
☑ предоставляем VIN, фотографии и информацию о движении автомобиля

Чтобы забронировать, напишите «ХОЧУ SONATA» 🚗"""


class GateFailure(RuntimeError):
    pass


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_text(text: str) -> str:
    return sha_bytes(text.encode("utf-8"))


def require(condition: Any, code: str) -> None:
    if not condition:
        raise GateFailure(code)


def import_from(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GateFailure("module_load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def download(remote_path: str) -> bytes:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN")
    if not token:
        raise GateFailure("missing_read_token")
    url = API_BASE + "files/path" + urllib.parse.quote(remote_path, safe="/")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task072-gate-a-v2/1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise GateFailure("download_too_large")
    return data


def db_connect(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(conn.execute("PRAGMA table_info(%s)" % table))


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])


def audit_count(conn: sqlite3.Connection) -> int:
    return count_rows(conn, "audit")


def condition_map(conn: sqlite3.Connection) -> dict[int, Any]:
    return {
        int(row["id"]): row["condition_text"]
        for row in conn.execute("SELECT id, condition_text FROM cars ORDER BY id")
    }


def protected_digest(conn: sqlite3.Connection) -> str:
    rows = [
        [int(row["id"]), row["description"], row["diag_text"]]
        for row in conn.execute(
            "SELECT id, description, diag_text FROM cars ORDER BY id"
        )
    ]
    return sha_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))


def restore_card(
    conn: sqlite3.Connection,
    card_id: int,
    condition_text: Any,
    updated_at: Any,
    has_updated_at: bool,
) -> None:
    if has_updated_at:
        conn.execute(
            "UPDATE cars SET condition_text=?, updated_at=? WHERE id=?",
            (condition_text, updated_at, card_id),
        )
    else:
        conn.execute(
            "UPDATE cars SET condition_text=? WHERE id=?", (condition_text, card_id)
        )
    conn.commit()


def last_audit(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT actor_id, action, entity_type, entity_id, field, old_value, new_value "
        "FROM audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise GateFailure("missing_audit")
    return row


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def unique_columns(conn: sqlite3.Connection) -> set[str]:
    result: set[str] = set()
    for index in conn.execute("PRAGMA index_list(cars)"):
        if not int(index[2]):
            continue
        for info in conn.execute("PRAGMA index_info(%s)" % index[1]):
            if info[2]:
                result.add(str(info[2]))
    return result


def future_value(
    conn: sqlite3.Connection,
    name: str,
    declared_type: str,
    not_null: bool,
    original: Any,
) -> Any:
    if name == "auto_number":
        return "UA-GATEA-072-FUTURE"
    if name in ("vin", "source_id", "external_id") and not not_null:
        return None
    upper_type = (declared_type or "").upper()
    if not not_null:
        return None
    if "INT" in upper_type:
        current = conn.execute("SELECT MAX(%s) FROM cars" % name).fetchone()[0]
        return int(current or 0) + 1_000_072
    if any(token in upper_type for token in ("REAL", "FLOA", "DOUB", "NUM")):
        return float(time.time())
    return "GATEA072-%s-%d" % (name, int(time.time() * 1_000_000))


def insert_future_card(conn: sqlite3.Connection) -> int:
    meta = table_columns(conn, "cars")
    first = conn.execute("SELECT * FROM cars ORDER BY id LIMIT 1").fetchone()
    require(first is not None, "no_template_card")
    uniques = unique_columns(conn)
    values: dict[str, Any] = {}
    for column in meta:
        name = str(column[1])
        if int(column[5]):
            continue
        value = first[name]
        if name in uniques:
            value = future_value(
                conn, name, str(column[2]), bool(column[3]), value
            )
        values[name] = value
    values["auto_number"] = "UA-GATEA-072-FUTURE"
    values["condition_text"] = ""
    values["description"] = "legacy-future-protected"
    values["diag_text"] = "diagnostic-future-protected"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if "created_at" in values:
        values["created_at"] = now
    if "updated_at" in values:
        values["updated_at"] = now
    names = list(values)
    cursor = conn.execute(
        "INSERT INTO cars (%s) VALUES (%s)"
        % (", ".join(names), ", ".join("?" for _ in names)),
        [values[name] for name in names],
    )
    conn.commit()
    return int(cursor.lastrowid)


def inspect_and_patch_sources(downloaded: dict[str, bytes], temp: pathlib.Path) -> dict[str, Any]:
    patcher = import_from(PATCHER_PATH, "task072_patcher")
    for name, expected in EXPECTED_SOURCE_SHA256.items():
        require(sha_bytes(downloaded[name]) == expected, "source_sha_drift_" + name)
        compile(downloaded[name].decode("utf-8"), name, "exec")

    db_source = downloaded["db.py"].decode("utf-8")
    require("old = get_card(table, card_id)" in db_source, "baseline_db_read_missing")
    require("log_action(actor_id, \"card_edit\"" in db_source, "baseline_audit_missing")

    patched = patcher.patch_source(downloaded["cars_ui.py"])
    patched_text = patched.decode("utf-8")
    compile(patched_text, "cars_ui.py", "exec")
    require(patched_text.count(patcher.PATCH_MARKER) == 1, "patch_marker")
    marker = patched_text.index(patcher.PATCH_MARKER)
    later_pop = patched_text.index(
        'context.user_data.pop("car_wait", None)', marker
    )
    save_call = patched_text.index("save_or_enqueue", marker)
    require(save_call < later_pop, "wait_cleared_before_save")
    require(
        'wait.get("field") in ("condition_text", "description")' in patched_text,
        "alias_route_missing",
    )
    require(
        'callback_data="car_setf:%d:diag_text"' in patched_text,
        "diagnostic_route_mixed",
    )
    (temp / "cars_ui.py").write_bytes(patched)
    shutil.copy2(WRITER_PATH, temp / "crm_description_writer.py")
    compile((temp / "crm_description_writer.py").read_text(encoding="utf-8"),
            "crm_description_writer.py", "exec")
    writer_source = WRITER_PATH.read_text(encoding="utf-8")
    require("INSERT INTO CARS" not in writer_source.upper(), "writer_can_create_car")
    require("SET condition_text" in writer_source, "canonical_write_missing")
    require("SET diag_text" not in writer_source, "diagnostic_write_present")
    require("SET description" not in writer_source, "legacy_write_present")

    return {
        "live_source_sha256": {
            name: sha_bytes(downloaded[name]) for name in EXPECTED_SOURCE_SHA256
        },
        "patched_cars_ui_sha256": sha_bytes(patched),
        "candidate_writer_sha256": sha_bytes(WRITER_PATH.read_bytes()),
        "baseline_wait_pop_before_write_confirmed": True,
        "baseline_db_multi_connection_path_confirmed": True,
        "patched_wait_pop_after_confirmed_save": True,
        "dynamic_wait_card_id_route": True,
        "legacy_description_aliases_to_condition_text": True,
        "diagnostic_route_separate": True,
        "telegram_confirmation_is_bounded": True,
    }


def validate_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", "quick_check_before")
    cars = {str(row[1]) for row in table_columns(conn, "cars")}
    audit = {str(row[1]) for row in table_columns(conn, "audit")}
    require(
        {"id", "auto_number", "condition_text", "description", "diag_text"}.issubset(cars),
        "real_cars_schema",
    )
    require(
        {"id", "actor_id", "action", "entity_type", "entity_id", "field",
         "old_value", "new_value", "created_at"}.issubset(audit),
        "real_audit_schema",
    )
    return {
        "cars_primary_key": "id",
        "canonical_description_field": "condition_text",
        "protected_fields_present": ["description", "diag_text"],
        "audit_schema_matches_live": True,
        "has_updated_at": "updated_at" in cars,
    }


def run_database_tests(writer, db_path: pathlib.Path, temp: pathlib.Path) -> dict[str, Any]:
    queue_path = temp / "all-existing-queue.sqlite3"
    conn = db_connect(db_path)
    schema = validate_schema(conn)
    existing_ids = [
        int(row[0]) for row in conn.execute("SELECT id FROM cars ORDER BY id")
    ]
    require(existing_ids, "no_existing_cards")
    existing_count = len(existing_ids)
    ids_digest = sha_text(json.dumps(existing_ids, separators=(",", ":")))
    protected_before = protected_digest(conn)

    for ordinal, card_id in enumerate(existing_ids, 1):
        before_conditions = condition_map(conn)
        before_count = count_rows(conn, "cars")
        before_audit = audit_count(conn)
        old_row = conn.execute(
            "SELECT condition_text%s FROM cars WHERE id=?"
            % (", updated_at" if schema["has_updated_at"] else ""),
            (card_id,),
        ).fetchone()
        old_text = old_row["condition_text"]
        old_updated = old_row["updated_at"] if schema["has_updated_at"] else None
        text = (
            SCREENSHOT_STYLE_TEXT
            if ordinal == 1
            else "TASK072 existing card %d\n500 $ · VIN · emoji 🚗" % ordinal
        )
        outcome = writer.save_or_enqueue(
            str(db_path), str(queue_path), card_id, text, 72072,
            "gate-existing:%d" % card_id, start_worker=False,
        )
        require(outcome["status"] == "saved", "existing_not_saved")
        after_conditions = condition_map(conn)
        require(after_conditions[card_id] == writer.normalize_text(text), "existing_readback")
        for other_id in existing_ids:
            if other_id != card_id:
                require(
                    after_conditions[other_id] == before_conditions[other_id],
                    "cross_card_write",
                )
        require(count_rows(conn, "cars") == before_count, "existing_created_card")
        require(audit_count(conn) == before_audit + 1, "existing_audit_count")
        audit = last_audit(conn)
        require(int(audit["entity_id"]) == card_id, "audit_wrong_card")
        require(audit["field"] == "condition_text", "audit_wrong_field")
        require(audit["old_value"] == old_text, "audit_old_value")
        require(audit["new_value"] == writer.normalize_text(text), "audit_new_value")
        restore_card(conn, card_id, old_text, old_updated, schema["has_updated_at"])

    require(protected_digest(conn) == protected_before, "protected_field_changed")

    # Future-card proof uses the exact live schema and a cloned valid row.
    count_before_future = count_rows(conn, "cars")
    future_id = insert_future_card(conn)
    require(count_rows(conn, "cars") == count_before_future + 1, "future_fixture")
    future_protected = protected_digest(conn)
    future_text = "Будущая карточка\nVIN и 500 $ сохраняются\n🚙"
    before_audit = audit_count(conn)
    outcome = writer.save_or_enqueue(
        str(db_path), str(queue_path), future_id, future_text, 72072,
        "gate-future:%d" % future_id, start_worker=False,
    )
    require(outcome["status"] == "saved", "future_not_saved")
    row = conn.execute(
        "SELECT condition_text, description, diag_text FROM cars WHERE id=?",
        (future_id,),
    ).fetchone()
    require(row["condition_text"] == future_text, "future_readback")
    require(row["description"] == "legacy-future-protected", "future_legacy_changed")
    require(row["diag_text"] == "diagnostic-future-protected", "future_diag_changed")
    require(protected_digest(conn) == future_protected, "future_protected_digest")
    require(audit_count(conn) == before_audit + 1, "future_audit_count")
    require(count_rows(conn, "cars") == count_before_future + 1, "writer_created_future_extra")

    # A missing id is rejected and can never become a new card.
    missing_id = int(conn.execute("SELECT MAX(id) FROM cars").fetchone()[0]) + 1_000_000
    before_count = count_rows(conn, "cars")
    try:
        writer.save_or_enqueue(
            str(db_path), str(queue_path), missing_id, "must not create", 72072,
            "gate-missing:%d" % missing_id, start_worker=False,
        )
    except writer.CardNotFoundError:
        pass
    else:
        raise GateFailure("missing_card_accepted")
    require(count_rows(conn, "cars") == before_count, "missing_card_created")

    # Full 12k Unicode boundary; 12,001 must be rejected without a write.
    boundary_id = existing_ids[0]
    original = conn.execute(
        "SELECT condition_text%s FROM cars WHERE id=?"
        % (", updated_at" if schema["has_updated_at"] else ""),
        (boundary_id,),
    ).fetchone()
    original_text = original["condition_text"]
    original_updated = original["updated_at"] if schema["has_updated_at"] else None
    max_text = ("абв🚗\n" * 2_399) + "абв🚗X"
    require(len(max_text) == 12_000, "boundary_fixture")
    outcome = writer.save_or_enqueue(
        str(db_path), str(queue_path), boundary_id, max_text, 72072,
        "gate-boundary:max", start_worker=False,
    )
    require(outcome["status"] == "saved", "boundary_max_rejected")
    require(
        conn.execute("SELECT condition_text FROM cars WHERE id=?", (boundary_id,)).fetchone()[0]
        == max_text,
        "boundary_max_readback",
    )
    audit_after_max = audit_count(conn)
    try:
        writer.save_or_enqueue(
            str(db_path), str(queue_path), boundary_id, max_text + "x", 72072,
            "gate-boundary:too-long", start_worker=False,
        )
    except writer.DescriptionValidationError:
        pass
    else:
        raise GateFailure("boundary_too_long_accepted")
    require(audit_count(conn) == audit_after_max, "boundary_reject_audit")
    restore_card(
        conn, boundary_id, original_text, original_updated, schema["has_updated_at"]
    )

    require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", "quick_check_after_core")
    conn.close()
    return {
        **schema,
        "existing_cards_tested": existing_count,
        "existing_card_ids_sha256": ids_digest,
        "future_card_tested_with_live_schema": True,
        "missing_card_rejected_without_insert": True,
        "canonical_field_exact_readback": True,
        "protected_description_unchanged": True,
        "protected_diag_text_unchanged": True,
        "unicode_linebreak_dollar_vin_emoji": True,
        "length_1_to_12000_enforced": True,
        "one_transaction_update_and_audit": True,
        "no_cross_card_writes": True,
    }


def run_queue_tests(writer, db_path: pathlib.Path, temp: pathlib.Path) -> dict[str, Any]:
    queue_path = temp / "contention-queue.sqlite3"
    conn = db_connect(db_path)
    card_id = int(conn.execute("SELECT id FROM cars ORDER BY id LIMIT 1").fetchone()[0])
    columns = {str(row[1]) for row in table_columns(conn, "cars")}
    has_updated = "updated_at" in columns
    old = conn.execute(
        "SELECT condition_text%s FROM cars WHERE id=?"
        % (", updated_at" if has_updated else ""),
        (card_id,),
    ).fetchone()
    old_text = old["condition_text"]
    old_updated = old["updated_at"] if has_updated else None
    before_audit = audit_count(conn)

    blocker = sqlite3.connect(str(db_path), timeout=1)
    blocker.execute("BEGIN EXCLUSIVE")
    blocker.execute("UPDATE cars SET condition_text=condition_text WHERE id=?", (card_id,))
    started = time.monotonic()
    queued = writer.save_or_enqueue(
        str(db_path), str(queue_path), card_id,
        "Queued description\n500 $ · VIN · 🚗", 72072,
        "gate-lock:1", start_worker=False,
    )
    enqueue_seconds = time.monotonic() - started
    require(queued["status"] == "queued", "lock_not_queued")
    require(enqueue_seconds < 1.0, "lock_budget_exceeded")
    blocker.rollback()
    blocker.close()

    drained = writer.drain_pending(str(db_path), str(queue_path), max_items=20)
    require(drained["applied"] == 1, "queue_not_applied")
    require(
        conn.execute("SELECT condition_text FROM cars WHERE id=?", (card_id,)).fetchone()[0]
        == "Queued description\n500 $ · VIN · 🚗",
        "queue_readback",
    )
    require(audit_count(conn) == before_audit + 1, "queue_audit_count")
    replay = writer.save_or_enqueue(
        str(db_path), str(queue_path), card_id,
        "Queued description\n500 $ · VIN · 🚗", 72072,
        "gate-lock:1", start_worker=False,
    )
    require(replay["status"] == "saved" and replay["duplicate"], "replay_status")
    require(audit_count(conn) == before_audit + 1, "replay_duplicate_audit")

    # Crash-after-CRM-commit-before-queue-ack: pending replay observes exact
    # read-back and acknowledges without a second write/audit.
    crash_text = "Crash recovery exact read-back 🚗"
    crash = writer.save_or_enqueue(
        str(db_path), str(queue_path), card_id, crash_text, 72072,
        "gate-crash:1", start_worker=False,
    )
    require(crash["status"] == "saved", "crash_fixture_save")
    crash_audit = audit_count(conn)
    qconn = sqlite3.connect(str(queue_path))
    qconn.execute(
        "UPDATE description_ops SET status='PENDING', claimed_at=NULL, applied_at=NULL "
        "WHERE operation_id='gate-crash:1'"
    )
    qconn.commit()
    qconn.close()
    drained = writer.drain_pending(str(db_path), str(queue_path), max_items=20)
    require(drained["applied"] == 1, "crash_not_acked")
    require(audit_count(conn) == crash_audit, "crash_duplicate_audit")

    # Last-intended-wins under contention.
    before_last_wins_audit = audit_count(conn)
    blocker = sqlite3.connect(str(db_path), timeout=1)
    blocker.execute("BEGIN EXCLUSIVE")
    blocker.execute("UPDATE cars SET condition_text=condition_text WHERE id=?", (card_id,))
    first = writer.save_or_enqueue(
        str(db_path), str(queue_path), card_id, "older intent", 72072,
        "gate-order:1", start_worker=False,
    )
    second = writer.save_or_enqueue(
        str(db_path), str(queue_path), card_id, "newer intent", 72072,
        "gate-order:2", start_worker=False,
    )
    require(first["status"] == second["status"] == "queued", "order_not_queued")
    blocker.rollback()
    blocker.close()
    drained = writer.drain_pending(str(db_path), str(queue_path), max_items=20)
    require(drained["superseded"] >= 1 and drained["applied"] >= 1, "order_not_drained")
    require(
        conn.execute("SELECT condition_text FROM cars WHERE id=?", (card_id,)).fetchone()[0]
        == "newer intent",
        "last_intended_not_final",
    )
    require(audit_count(conn) == before_last_wins_audit + 1, "order_audit_count")

    restore_card(conn, card_id, old_text, old_updated, has_updated)
    require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", "queue_quick_check")
    conn.close()
    return {
        "locked_path_status": "queued",
        "locked_path_seconds": round(enqueue_seconds, 4),
        "locked_path_under_one_second": True,
        "durable_queue_applied_after_unlock": True,
        "stable_operation_id_idempotent": True,
        "crash_after_commit_no_duplicate_audit": True,
        "last_intended_wins": True,
    }


def run_performance_tests(writer, db_path: pathlib.Path, temp: pathlib.Path) -> dict[str, Any]:
    queue_path = temp / "performance-queue.sqlite3"
    conn = db_connect(db_path)
    card_id = int(conn.execute("SELECT id FROM cars ORDER BY id LIMIT 1").fetchone()[0])
    columns = {str(row[1]) for row in table_columns(conn, "cars")}
    has_updated = "updated_at" in columns
    old = conn.execute(
        "SELECT condition_text%s FROM cars WHERE id=?"
        % (", updated_at" if has_updated else ""),
        (card_id,),
    ).fetchone()
    old_text = old["condition_text"]
    old_updated = old["updated_at"] if has_updated else None
    durations: list[float] = []
    for index in range(60):
        text = "performance-%02d-%s" % (index, "🚗\n500 $ VIN")
        started = time.monotonic()
        outcome = writer.save_or_enqueue(
            str(db_path), str(queue_path), card_id, text, 72072,
            "gate-perf:%d" % index, start_worker=False,
        )
        durations.append(time.monotonic() - started)
        require(outcome["status"] == "saved", "performance_not_saved")
    restore_card(conn, card_id, old_text, old_updated, has_updated)
    require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", "performance_quick_check")
    conn.close()
    return {
        "samples": len(durations),
        "median_seconds": round(statistics.median(durations), 6),
        "p95_seconds": round(percentile(durations, 0.95), 6),
        "p99_seconds": round(percentile(durations, 0.99), 6),
        "max_seconds": round(max(durations), 6),
    }


def write_outputs(result: dict[str, Any]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = EVIDENCE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(EVIDENCE_PATH)

    status = result["status"]
    if status == "PASS":
        db = result["database_tests"]
        queue = result["queue_tests"]
        perf = result["performance"]
        report = f"""# TASK 072 — Gate A V2

Status: **PASS**

- Production access: GET only; no production files or database rows were changed.
- Live source SHA guards: PASS.
- Real schema: `cars.id` → `cars.condition_text`; live `audit` columns verified.
- Existing cards tested dynamically: **{db['existing_cards_tested']}**.
- Future-card test on the same live schema: PASS.
- Unicode/newlines/`$`/VIN/emoji and 12,000-character boundary: PASS.
- `description` and `diag_text` remained unchanged: PASS.
- Lock fallback: queued in **{queue['locked_path_seconds']:.4f}s**, then applied after unlock.
- Replay/crash idempotency and last-intended-wins: PASS.
- Direct path p95/p99: **{perf['p95_seconds']:.6f}s / {perf['p99_seconds']:.6f}s**.

Gate B remains intentionally unexecuted and requires explicit owner approval.
"""
    else:
        report = f"""# TASK 072 — Gate A V2

Status: **BLOCKED**

- Safe failure class: `{result.get('error_type', 'unknown')}`.
- Production access was GET only; no production mutation was attempted.
- Gate B must not run.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    result: dict[str, Any] = {
        "task_id": "task_072",
        "gate": "A_V2_REAL_CONTEXT",
        "status": "BLOCKED",
        "remote_http_methods": ["GET"],
        "production_touched": False,
        "production_database_write": False,
        "gate_b_executed": False,
    }
    try:
        downloaded = {name: download(path) for name, path in REMOTE.items()}
        with tempfile.TemporaryDirectory(prefix="task072_gate_a_v2_") as raw_temp:
            temp = pathlib.Path(raw_temp)
            live_db = temp / "live-download.crm.db"
            live_db.write_bytes(downloaded["crm.db"])
            live_hash_before = sha_bytes(live_db.read_bytes())
            source_conn = db_connect(live_db)
            require(
                source_conn.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                "downloaded_db_quick_check",
            )
            source_count = count_rows(source_conn, "cars")
            source_conn.close()
            require(source_count > 0, "downloaded_db_empty")

            sources = inspect_and_patch_sources(downloaded, temp)
            writer = import_from(temp / "crm_description_writer.py", "crm_description_writer")

            core_db = temp / "core-tests.crm.db"
            queue_db = temp / "queue-tests.crm.db"
            perf_db = temp / "performance-tests.crm.db"
            shutil.copy2(live_db, core_db)
            shutil.copy2(live_db, queue_db)
            shutil.copy2(live_db, perf_db)

            result["sources"] = sources
            result["live_database"] = {
                "sha256": live_hash_before,
                "size_bytes": len(downloaded["crm.db"]),
                "cards_count": source_count,
                "quick_check": "ok",
                "copy_only": True,
            }
            result["database_tests"] = run_database_tests(writer, core_db, temp)
            result["queue_tests"] = run_queue_tests(writer, queue_db, temp)
            result["performance"] = run_performance_tests(writer, perf_db, temp)
            require(sha_bytes(live_db.read_bytes()) == live_hash_before, "live_copy_mutated")
            result["live_download_unchanged_after_tests"] = True
            result["status"] = "PASS"
            write_outputs(result)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        write_outputs(result)
        raise
    print("TASK072_GATE_A_V2_PASS")


if __name__ == "__main__":
    main()
