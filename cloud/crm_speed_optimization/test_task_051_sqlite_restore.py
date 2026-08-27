"""
test_task_051_sqlite_restore.py

Compact offline test suite for the TASK 051 restoration/correction of
sqlite_ownership.py. Uses only fake in-process sqlite-like objects and
temporary files -- no network, no production paths, no real database
writes beyond a throwaway temp SQLite file used for the minimal legacy
evidence-API smoke test.

This file authors tests only; it does not itself execute pytest/CI.
Controllers should run: python -m pytest test_task_051_sqlite_restore.py -v
"""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sqlite_ownership as so  # noqa: E402


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------

class FakeCursor:
    def __init__(self, events, fail_execute=False, fail_fetch=False, fetch_rows=None):
        self.events = events
        self.fail_execute = fail_execute
        self.fail_fetch = fail_fetch
        self.fetch_rows = fetch_rows if fetch_rows is not None else [(1, 2), (3, 4)]
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        if self.fail_execute:
            raise ValueError("execute boom")
        self.last_sql = sql
        self.last_params = params
        return self

    def fetchall(self):
        if self.fail_fetch:
            raise ValueError("fetch boom")
        return list(self.fetch_rows)

    def close(self):
        self.events.append("cur_close")


class FakeConn:
    def __init__(self, events, fail_execute=False, fail_fetch=False, fetch_rows=None):
        self.events = events
        self.fail_execute = fail_execute
        self.fail_fetch = fail_fetch
        self.fetch_rows = fetch_rows

    def cursor(self):
        return FakeCursor(self.events, self.fail_execute, self.fail_fetch, self.fetch_rows)

    def execute(self, sql, params=None):
        cur = FakeCursor(self.events, self.fail_execute, self.fail_fetch, self.fetch_rows)
        return cur.execute(sql, params)

    def close(self):
        self.events.append("conn_close")


class FakeSqlite3Module:
    def __init__(self, events, fail_connect=False, fail_execute=False,
                 fail_fetch=False, fetch_rows=None):
        self.events = events
        self.fail_connect = fail_connect
        self.fail_execute = fail_execute
        self.fail_fetch = fail_fetch
        self.fetch_rows = fetch_rows
        self.connect_calls = []

    def connect(self, *args, **kwargs):
        self.connect_calls.append((args, kwargs))
        self.events.append("connect")
        if self.fail_connect:
            raise RuntimeError("connect boom")
        return FakeConn(self.events, self.fail_execute, self.fail_fetch, self.fetch_rows)


def _transform_and_load(source, fn_name, fake_module):
    new_source = so.transform_short_ownership(source, {fn_name})
    compile(new_source, "<generated>", "exec")  # must compile deterministically
    ns = {"sqlite3": fake_module}
    exec(new_source, ns)
    return ns[fn_name], new_source


# ---------------------------------------------------------------------
# Negative shapes (must raise AnchorNotFoundError)
# ---------------------------------------------------------------------

SRC_RETURN_CUR = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute("SELECT 1").fetchall()
    return cur
'''

SRC_ALIAS = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    other = cur
    rows = cur.execute("SELECT 1").fetchall()
    return rows
'''

SRC_CALLER_OWNED = '''
def q(conn):
    cur = conn.cursor()
    rows = cur.execute("SELECT 1").fetchall()
    return rows
'''

SRC_MULTI = '''
def q(db_path):
    conn1 = sqlite3.connect(db_path)
    conn2 = sqlite3.connect(db_path)
    cur = conn1.cursor()
    rows = cur.execute("SELECT 1").fetchall()
    return rows
'''

SRC_BRANCH = '''
def q(db_path, flag):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    if flag:
        rows = cur.execute("SELECT 1").fetchall()
    else:
        rows = []
    return rows
'''

SRC_WRITE = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM t")
    return None
'''

SRC_NONLIT = '''
def q(db_path, sql):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute(sql).fetchall()
    return rows
'''

SRC_ESCAPE_ARG = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute("SELECT 1").fetchall()
    log(cur)
    return rows
'''


class TestNegativeShapes(unittest.TestCase):
    def _expect_block(self, src):
        with self.assertRaises(so.AnchorNotFoundError):
            so.transform_short_ownership(src, {"q"})

    def test_return_cur_rejected(self):
        self._expect_block(SRC_RETURN_CUR)

    def test_alias_rejected(self):
        self._expect_block(SRC_ALIAS)

    def test_caller_owned_rejected(self):
        self._expect_block(SRC_CALLER_OWNED)

    def test_multiple_handles_rejected(self):
        self._expect_block(SRC_MULTI)

    def test_branch_rejected(self):
        self._expect_block(SRC_BRANCH)

    def test_write_sql_rejected(self):
        self._expect_block(SRC_WRITE)

    def test_nonliteral_sql_rejected(self):
        self._expect_block(SRC_NONLIT)

    def test_escape_via_call_argument_rejected(self):
        self._expect_block(SRC_ESCAPE_ARG)


# ---------------------------------------------------------------------
# Positive shapes: cursor discovery via conn.cursor() and conn.execute()
# ---------------------------------------------------------------------

SRC_OK_CURSOR = '''
def q(db_path, qid):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()
    rows = cur.execute("SELECT a,b FROM t WHERE id=?", (qid,)).fetchall()
    cur.close()
    conn.close()
    return rows
'''

SRC_OK_CONN_EXECUTE = '''
def q(db_path, qid):
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT a,b FROM t WHERE id=?", (qid,))
    rows = cur.fetchall()
    return rows
'''

SRC_TIMEOUT_EXISTING = '''
def q(db_path):
    conn = sqlite3.connect(db_path, timeout=9)
    cur = conn.cursor()
    rows = cur.execute("SELECT 1").fetchall()
    return rows
'''


class TestCursorDiscoveryAndTimeout(unittest.TestCase):
    def test_conn_cursor_discovery_and_timeout_once(self):
        events = []
        fake = FakeSqlite3Module(events)
        fn, _src = _transform_and_load(SRC_OK_CURSOR, "q", fake)
        result = fn("db.sqlite", 42)
        self.assertEqual(result, ((1, 2), (3, 4)))
        args, kwargs = fake.connect_calls[0]
        self.assertEqual(args, ("db.sqlite",))
        self.assertEqual(kwargs.get("timeout"), 2)
        self.assertEqual(kwargs.get("check_same_thread"), False)
        self.assertEqual(list(kwargs.keys()).count("timeout"), 1)

    def test_conn_execute_cursor_discovery(self):
        events = []
        fake = FakeSqlite3Module(events)
        fn, _src = _transform_and_load(SRC_OK_CONN_EXECUTE, "q", fake)
        result = fn("db.sqlite", 7)
        self.assertEqual(result, ((1, 2), (3, 4)))

    def test_existing_timeout_normalized_to_2(self):
        events = []
        fake = FakeSqlite3Module(events)
        fn, _src = _transform_and_load(SRC_TIMEOUT_EXISTING, "q", fake)
        fn("db.sqlite")
        args, kwargs = fake.connect_calls[0]
        self.assertEqual(kwargs.get("timeout"), 2)
        self.assertEqual(list(kwargs.values()).count(2), kwargs.get("timeout") == 2 and 1 or 0)


# ---------------------------------------------------------------------
# Close ordering, tuple materialization, exception propagation
# ---------------------------------------------------------------------

class TestCloseOrderingAndExceptions(unittest.TestCase):
    def test_tuple_of_tuples_and_close_order(self):
        events = []
        fake = FakeSqlite3Module(events, fetch_rows=[(9, 8), (7, 6)])
        fn, _src = _transform_and_load(SRC_OK_CURSOR, "q", fake)
        result = fn("db.sqlite", 1)
        self.assertIsInstance(result, tuple)
        self.assertTrue(all(isinstance(r, tuple) for r in result))
        self.assertEqual(result, ((9, 8), (7, 6)))
        self.assertEqual(events.count("cur_close"), 1)
        self.assertEqual(events.count("conn_close"), 1)
        self.assertEqual(events.index("cur_close"), events.index("conn_close") - 1)

    def test_connect_failure_propagates_original_exception(self):
        events = []
        fake = FakeSqlite3Module(events, fail_connect=True)
        fn, _src = _transform_and_load(SRC_OK_CURSOR, "q", fake)
        with self.assertRaises(RuntimeError) as ctx:
            fn("db.sqlite", 1)
        self.assertEqual(str(ctx.exception), "connect boom")

    def test_execute_failure_propagates_and_still_closes(self):
        events = []
        fake = FakeSqlite3Module(events, fail_execute=True)
        fn, _src = _transform_and_load(SRC_OK_CURSOR, "q", fake)
        with self.assertRaises(ValueError) as ctx:
            fn("db.sqlite", 1)
        self.assertEqual(str(ctx.exception), "execute boom")
        self.assertIn("cur_close", events)
        self.assertIn("conn_close", events)

    def test_fetch_failure_propagates_and_still_closes(self):
        events = []
        fake = FakeSqlite3Module(events, fail_fetch=True)
        fn, _src = _transform_and_load(SRC_OK_CURSOR, "q", fake)
        with self.assertRaises(ValueError) as ctx:
            fn("db.sqlite", 1)
        self.assertEqual(str(ctx.exception), "fetch boom")
        self.assertIn("cur_close", events)
        self.assertIn("conn_close", events)

    def test_deterministic_transform_same_bytes(self):
        src1 = so.transform_short_ownership(SRC_OK_CURSOR, {"q"})
        src2 = so.transform_short_ownership(SRC_OK_CURSOR, {"q"})
        self.assertEqual(src1, src2)


# ---------------------------------------------------------------------
# verify_no_live_handle_across_slow_call: unrelated close cannot
# suppress a real violation.
# ---------------------------------------------------------------------

SRC_UNRELATED_CLOSE = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    unrelated = object()
    unrelated.close()
    time.sleep(1)
    conn.close()
    cur.close()
'''

SRC_PROPERLY_CLOSED_BEFORE_SLEEP = '''
def q(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.close()
    conn.close()
    time.sleep(1)
'''


class TestVerifierUnrelatedClose(unittest.TestCase):
    def _func(self, src):
        tree = ast.parse(src)
        return tree.body[0]

    def test_unrelated_close_does_not_suppress_violation(self):
        func = self._func(SRC_UNRELATED_CLOSE)
        violations = so.verify_no_live_handle_across_slow_call(func)
        self.assertTrue(violations, "expected a violation to be reported")

    def test_proper_close_before_slow_call_has_no_violation(self):
        func = self._func(SRC_PROPERLY_CLOSED_BEFORE_SLEEP)
        violations = so.verify_no_live_handle_across_slow_call(func)
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------
# Baseline evidence API preserved: names exist + minimal legacy smoke.
# ---------------------------------------------------------------------

class TestEvidenceApiPreserved(unittest.TestCase):
    def test_public_names_exist(self):
        for name in (
            "AnchorNotFoundError", "find_db_handle_names", "find_cursor_names",
            "verify_no_live_handle_across_slow_call", "transform_short_ownership",
            "OwnershipEvidence", "collect_ua0009_ownership_evidence",
            "compare_ownership_evidence",
        ):
            self.assertTrue(hasattr(so, name), f"missing public name: {name}")

    def test_minimal_evidence_legacy_behavior(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy.sqlite3")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE orders (order_id TEXT PRIMARY KEY, note TEXT)")
            conn.execute("INSERT INTO orders VALUES (?, ?)", ("UA-0009", "secret-note"))
            conn.commit()
            conn.close()

            before = so.collect_ua0009_ownership_evidence(db_path, "orders", "order_id")
            self.assertEqual(before.status, "OK")
            self.assertEqual(before.table, "orders")
            self.assertEqual(before.row_count, 1)
            self.assertIsNotNone(before.evidence_sha256)
            # No raw field values ever appear in the evidence dict.
            dumped = str(before.to_dict())
            self.assertNotIn("secret-note", dumped)

            after = so.collect_ua0009_ownership_evidence(db_path, "orders", "order_id")
            ok, reason = so.compare_ownership_evidence(before, after)
            self.assertTrue(ok)
            self.assertEqual(reason, "ok")

            missing = so.collect_ua0009_ownership_evidence(db_path, "orders", "order_id", id_value="UA-9999")
            self.assertEqual(missing.status, "BLOCKED")
            self.assertEqual(missing.reason, "missing_row")


# ---------------------------------------------------------------------
# Compile every package Python file.
# ---------------------------------------------------------------------

class TestPackageCompiles(unittest.TestCase):
    def test_all_py_files_compile(self):
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        for fname in os.listdir(pkg_dir):
            if fname.endswith(".py"):
                path = os.path.join(pkg_dir, fname)
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                compile(src, path, "exec")


if __name__ == "__main__":
    unittest.main()
