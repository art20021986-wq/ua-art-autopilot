"""TASK088's bounded, reversible SQLite proof on an explicit unpublished car."""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sqlite3
import tempfile
import time
import uuid
from urllib.parse import quote

BUSY_TIMEOUT_MS = 3000
PRICES = ("price_uah", "price_georgia")


class VerificationError(RuntimeError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def _connect(db_path, *, readonly=False):
    path = pathlib.Path(db_path)
    if not path.is_file() or path.is_symlink():
        raise VerificationError("DB_TARGET_INVALID")
    uri = "file:" + quote(str(path.resolve()), safe="/")
    conn = sqlite3.connect(uri + ("?mode=ro" if readonly else "?mode=rw"),
                           uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=%d" % BUSY_TIMEOUT_MS)
    return conn


def _row(conn, car_id):
    rows = conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchall()
    if len(rows) != 1:
        raise VerificationError("EXPLICIT_TEST_CAR_NOT_UNIQUE_OR_MISSING")
    return dict(rows[0])


def _read_fresh(db_path, car_id):
    conn = _connect(db_path, readonly=True)
    try:
        return _row(conn, car_id)
    finally:
        conn.close()


def _json_value(value):
    if isinstance(value, bytes):
        return {"sqlite_blob_base64": base64.b64encode(value).decode("ascii")}
    raise TypeError(type(value).__name__)


def _journal(path, details):
    """Persist intent before COMMIT so an interrupted proof remains recoverable."""
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(details, stream, sort_keys=True, indent=2, default=_json_value)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def _identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _expected_cars(conn, car_id, field, value):
    """Snapshot all cars, allowing exactly the selected price to change."""
    return [dict(row, **{field: value}) if row["id"] == car_id else dict(row)
            for row in conn.execute("SELECT * FROM cars ORDER BY id")]


def _cars_unchanged_except_price(conn, expected):
    return [dict(row) for row in conn.execute("SELECT * FROM cars ORDER BY id")] == expected


def _restore(db_path, car_id, original, expected, field):
    """Compare-and-set the test value; never overwrite a concurrent edit."""
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = _row(conn, car_id)
        if current == original:
            conn.commit()  # A failed COMMIT may already have rolled back.
        elif current != expected:
            raise VerificationError("RESTORATION_CONFLICT", {
                "observed_prices": {key: current.get(key) for key in PRICES},
                "changed_columns": [key for key in expected if current.get(key) != expected[key]],
            })
        else:
            expected_cars = _expected_cars(conn, original["id"], field, original[field])
            predicate = " AND ".join(_identifier(key) + " IS ?" for key in expected)
            result = conn.execute("UPDATE cars SET " + _identifier(field) + "=? WHERE " + predicate,
                                  [original[field], *expected.values()])
            if result.rowcount != 1 or _row(conn, car_id) != original:
                raise VerificationError("RESTORATION_INVARIANT_FAILED")
            if not _cars_unchanged_except_price(conn, expected_cars):
                raise VerificationError("RESTORATION_CARS_INVARIANT_FAILED")
            conn.commit()
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()
    if _read_fresh(db_path, car_id) != original:
        raise VerificationError("RESTORATION_FRESH_READBACK_FAILED")


def _direction(db_path, car_id, original, field, journal_path, details):
    sentinel = 1 if original[field] != 1 else 2
    expected = dict(original, **{field: sentinel})
    details.update(status="PREPARING", field=field, test_value=sentinel,
                   expected_prices={key: expected[key] for key in PRICES},
                   restoration_needed=False)
    commit_attempted = False
    problem = None
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if _row(conn, car_id) != original:
            raise VerificationError("CONCURRENT_EDIT_BEFORE_TEST")
        expected_cars = _expected_cars(conn, original["id"], field, sentinel)
        result = conn.execute("UPDATE cars SET " + _identifier(field) + "=? WHERE id=?",
                              (sentinel, car_id))
        if result.rowcount != 1 or _row(conn, car_id) != expected:
            raise VerificationError("PRECOMMIT_ROW_INVARIANT_FAILED:" + field)
        if not _cars_unchanged_except_price(conn, expected_cars):
            raise VerificationError("PRECOMMIT_CARS_INVARIANT_FAILED:" + field)
        details.update(status="COMMIT_PENDING", restoration_needed=True)
        _journal(journal_path, details)
        commit_attempted = True
        conn.commit()
    except Exception as exc:
        problem = exc
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()

    if commit_attempted:
        try:
            if problem is None and _read_fresh(db_path, car_id) != expected:
                raise VerificationError("POSTCOMMIT_ROW_INVARIANT_FAILED:" + field)
        except Exception as exc:
            problem = exc
        finally:
            try:
                _restore(db_path, car_id, original, expected, field)
                details["restoration_needed"] = False
            except Exception as restore_error:
                details.update(status="RESTORATION_NEEDED", restoration_needed=True,
                               restore_error=str(restore_error),
                               restore_detail=getattr(restore_error, "details", {}),
                               error=str(problem) if problem else None)
                _journal(journal_path, details)
                raise VerificationError("RESTORATION_NEEDED", dict(details)) from restore_error
    if problem is not None:
        details.update(status="FAILED_RESTORED", error=str(problem))
        _journal(journal_path, details)
        raise VerificationError(str(problem), dict(details)) from problem
    details["directions"][field] = {
        "write": "PASS", "commit": "PASS", "fresh_readback": "PASS",
        "other_price_unchanged": "PASS", "full_row_invariant": "PASS",
        "other_cars_unchanged": "PASS",
        "restore_commit": "PASS", "restore_fresh_readback": "PASS",
    }
    details.update(status="DIRECTION_RESTORED", restoration_needed=False)
    _journal(journal_path, details)


def verify_price_roundtrip(db_path, car_id):
    """Return proof only after both committed price tests are durably restored.

    A conflicting concurrent edit stops restoration and leaves a durable journal;
    callers must report FAIL and retain that journal for controlled recovery.
    No vehicle is selected implicitly, and published/unknown status is rejected.
    """
    if car_id is None or isinstance(car_id, bool) or not isinstance(car_id, (int, str)) or not str(car_id).strip():
        raise VerificationError("EXPLICIT_TEST_CAR_ID_REQUIRED")
    original = _read_fresh(db_path, car_id)
    if not {"id", "published", *PRICES} <= original.keys():
        raise VerificationError("REQUIRED_CAR_COLUMNS_MISSING")
    if type(original["published"]) is not int or original["published"] != 0:
        raise VerificationError("TEST_CAR_MUST_BE_EXPLICITLY_UNPUBLISHED")
    journal_path = pathlib.Path(db_path).resolve().with_name(
        "task088-price-roundtrip-" + uuid.uuid4().hex + ".json")
    details = {
        "test_car_id": car_id, "db_path": str(pathlib.Path(db_path).resolve()),
        "original_prices": {key: original[key] for key in PRICES},
        "journal_path": str(journal_path), "directions": {},
        "status": "STARTED", "restoration_needed": False,
    }
    _journal(journal_path, details)
    for field in ("price_georgia", "price_uah"):
        _direction(db_path, car_id, original, field, journal_path, details)
    details.update(status="PASS", db_commit="PASS", read_back="PASS",
                   price_uah_unchanged="PASS", price_georgia_unchanged="PASS",
                   ua_ge_independence="PASS", rollback_test_value="PASS")
    _journal(journal_path, details)
    return details


def backup_sqlite(db_path, backup_path):
    """SQLite-consistent backup including WAL, to a new path only."""
    target = pathlib.Path(backup_path)
    if target.resolve() == pathlib.Path(db_path).resolve():
        raise VerificationError("BACKUP_EQUALS_SOURCE")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    source = destination = None
    try:
        source = _connect(db_path, readonly=True)
        destination = sqlite3.connect(str(target), timeout=BUSY_TIMEOUT_MS / 1000)
        deadline = time.monotonic() + 5

        def bounded_backup(status, remaining, total):
            if time.monotonic() > deadline:
                raise VerificationError("BACKUP_TIMEOUT")

        source.backup(destination, pages=64, progress=bounded_backup, sleep=0.05)
        destination.close()
        destination = None
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
        return str(target.resolve())
    except Exception:
        if destination is not None:
            destination.close()
            destination = None
        target.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()
        if destination is not None:
            destination.close()
