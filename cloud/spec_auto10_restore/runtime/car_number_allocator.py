"""Reserve CRM card identifiers in the caller's existing SQLite transaction.

Committed reservations survive card deletion. A rolled-back creation is allowed
to reuse its *uncommitted* number. This module never commits a caller's work,
opens another database, imports CRM modules, or accesses the network/filesystem.
"""
from __future__ import annotations

import re

VERSION = "UA_AUTO10_CARD_NUMBER_V1"
_PREFIX = re.compile(r"[A-Z][A-Z0-9]{0,15}-\Z")
_TABLE = "ua_card_number_sequence"
_LIMIT = 9223372036854775806


class AllocationError(RuntimeError):
    pass


def _rows(connection, sql, parameters=()):
    cursor = connection.execute(sql, parameters)
    try:
        return cursor.fetchall()
    finally:
        cursor.close()


def _execute(connection, sql, parameters=()):
    cursor = connection.execute(sql, parameters)
    cursor.close()


def _suffix(value, prefix):
    value = str(value or "").strip().upper()
    tail = value[len(prefix):] if value.startswith(prefix) else ""
    if not tail or not tail.isascii() or not tail.isdecimal():
        return 0
    number = int(tail)
    if number > _LIMIT:
        raise AllocationError("CARD_NUMBER_RANGE_EXHAUSTED")
    return number


def _seed(connection, prefix):
    # Read only after acquiring the SQLite write lock. The CRM row id sequence
    # also retains the old high water after legacy deletion, before this feature
    # existed. It is a conservative floor, not an assumption that id == suffix.
    tables = {row[0] for row in _rows(connection,
              "SELECT name FROM sqlite_master WHERE type='table'")}
    if "cars" not in tables:
        raise AllocationError("CARD_NUMBER_CARS_TABLE_MISSING")
    maximum = 0
    for table in ("cars", "ua_spec_lifecycle_archive", "media"):
        if table not in tables:
            continue
        columns = {row[1] for row in _rows(connection, 'PRAGMA table_info("' + table + '")')}
        if "auto_number" not in columns:
            if table == "cars":
                raise AllocationError("CARD_NUMBER_COLUMN_MISSING")
            continue
        for row in _rows(connection, 'SELECT auto_number FROM "' + table + '"'):
            maximum = max(maximum, _suffix(row[0], prefix))
    if "sqlite_sequence" in tables:
        for row in _rows(connection, "SELECT seq FROM sqlite_sequence WHERE name='cars'"):
            maximum = max(maximum, int(row[0] or 0))
    if maximum >= _LIMIT:
        raise AllocationError("CARD_NUMBER_RANGE_EXHAUSTED")
    return maximum


def reserve(connection, prefix="UA-"):
    """Return a reserved unique number; the caller must commit with its INSERT.

    With an existing transaction, all earlier caller changes and its transaction
    remain intact, even on a local allocation error. With no transaction, this
    starts BEGIN IMMEDIATE and leaves the successful transaction to the caller.
    A stale read transaction may fail SQLITE_BUSY; it must never return a guess.
    """
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
        raise AllocationError("CARD_NUMBER_PREFIX_INVALID")
    started = not connection.in_transaction
    if started:
        _execute(connection, "BEGIN IMMEDIATE")
    _execute(connection, "SAVEPOINT ua_card_number_reserve")
    try:
        _execute(connection, "CREATE TABLE IF NOT EXISTS " + _TABLE + " ("
                 "prefix TEXT PRIMARY KEY, high_water INTEGER NOT NULL "
                 "CHECK(typeof(high_water)='integer' AND high_water>=0))")
        # This write happens BEFORE any identity/high-water reads, serializing
        # processes as well as threads even when the schema already exists.
        _execute(connection, "INSERT OR IGNORE INTO " + _TABLE +
                 "(prefix,high_water) VALUES(?,0)", (prefix,))
        _execute(connection, "UPDATE " + _TABLE +
                 " SET high_water=high_water WHERE prefix=?", (prefix,))
        floor = _seed(connection, prefix)
        rows = _rows(connection, "SELECT high_water FROM " + _TABLE +
                     " WHERE prefix=?", (prefix,))
        if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
            raise AllocationError("CARD_NUMBER_SEQUENCE_INVALID")
        number = max(rows[0][0], floor) + 1
        if number > _LIMIT:
            raise AllocationError("CARD_NUMBER_RANGE_EXHAUSTED")
        _execute(connection, "UPDATE " + _TABLE + " SET high_water=? WHERE prefix=?",
                 (number, prefix))
        _execute(connection, "RELEASE SAVEPOINT ua_card_number_reserve")
        return "%s%04d" % (prefix, number)
    except BaseException:
        _execute(connection, "ROLLBACK TO SAVEPOINT ua_card_number_reserve")
        _execute(connection, "RELEASE SAVEPOINT ua_card_number_reserve")
        if started:
            connection.rollback()
        raise


def ensure_card_number(connection, card_id):
    """Return (number, assigned_now), atomically filling a legacy blank UID.

    Newly created cards already have their reserved number; returning it must
    not allocate again, mutate identity, or overwrite another caller's value.
    """
    if type(card_id) is not int or card_id <= 0:
        raise AllocationError("CARD_NUMBER_CARD_ID_INVALID")
    started = not connection.in_transaction
    if started:
        _execute(connection, "BEGIN IMMEDIATE")
    _execute(connection, "SAVEPOINT ua_card_number_assign")
    try:
        rows = _rows(connection, "SELECT auto_number FROM cars WHERE id=?", (card_id,))
        if len(rows) != 1:
            raise AllocationError("CARD_NUMBER_CARD_MISSING")
        if str(rows[0][0] or "").strip():
            number, assigned = rows[0][0], False
        else:
            number, assigned = reserve(connection), True
            cursor = connection.execute("UPDATE cars SET auto_number=? WHERE id=? "
                                        "AND COALESCE(TRIM(auto_number),'')=''", (number, card_id))
            try:
                changed = cursor.rowcount
            finally:
                cursor.close()
            if changed != 1:
                raise AllocationError("CARD_NUMBER_CARD_CHANGED")
        _execute(connection, "RELEASE SAVEPOINT ua_card_number_assign")
        return number, assigned
    except BaseException:
        _execute(connection, "ROLLBACK TO SAVEPOINT ua_card_number_assign")
        _execute(connection, "RELEASE SAVEPOINT ua_card_number_assign")
        if started:
            connection.rollback()
        raise
