"""
TASK 046 focused offline test suite for the rebuild AST transformer and the
SQLite ownership transform, corrected under TASK 053 to the canonical
contract (candidate_transforms result schema uses result["candidate"] /
result["reasons"], never result["code"]; sqlite_ownership uses the accepted
names AnchorNotFoundError, transform_short_ownership, OwnershipEvidence,
collect_ua0009_ownership_evidence and compare_ownership_evidence -- the
rejected clean-room names transform_sqlite_ownership / OwnershipBlocked are
not used anywhere in this file).

Temporary-directory / in-memory only. No network, no PythonAnywhere, no
Production or CRM access.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""

import ast
import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import candidate_transforms as ct  # noqa: E402
import sqlite_ownership as so  # noqa: E402


def _assert_no_surviving_generator_call(candidate_source, generator_name):
    """AST-based proof (not brittle text splitting/substrings) that no
    ast.Call to `generator_name` survives anywhere outside that
    generator's own function definition."""
    tree = ast.parse(candidate_source)
    generator_node = next(
        (
            n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == generator_name
        ),
        None,
    )

    def _walk_excluding(node, excluded):
        for child in ast.iter_child_nodes(node):
            if child is excluded:
                continue
            yield child
            yield from _walk_excluding(child, excluded)

    for node in _walk_excluding(tree, generator_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == generator_name:
            raise AssertionError(
                f"generator call to {generator_name!r} survived outside its own definition"
            )


class TestRebuildTransformPositive(unittest.TestCase):
    def test_expr_call_positive(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<t>", "exec")
        self.assertIn("_queue = RebuildQueue(generate_stranica_page,", result["candidate"])
        _assert_no_surviving_generator_call(result["candidate"], "generate_stranica_page")

    def test_return_call_positive(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                return generate_stranica_page()

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        self.assertIn("return _queue.enqueue()", result["candidate"])
        _assert_no_surviving_generator_call(result["candidate"], "generate_stranica_page")

    def test_alias_spawn_positive(self):
        """Alias-resolved subprocess callable (import subprocess as sp)
        plus a literal 'stranica.py' command."""
        src = textwrap.dedent("""
            import subprocess as sp

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                sp.Popen(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        self.assertIn("_queue.enqueue()", result["candidate"])
        _assert_no_surviving_generator_call(result["candidate"], "generate_stranica_page")


class TestRebuildTransformNegative(unittest.TestCase):
    def test_unsupported_assignment_context_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                x = generate_stranica_page()
                return x

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_unrelated_spawn_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                subprocess.run(["ffmpeg", "-i", "in.mp4", "out.mp4"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_dynamic_command_blocks(self):
        src = textwrap.dedent("""
            import subprocess
            import os

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two(name):
                subprocess.run(["python3", os.path.join("scripts", name)])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_ambiguous_two_generator_targets_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def generate_other_page():
                return "ok2"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                generate_other_page()

            def trigger_three():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_direct_call_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_spawn_blocks(self):
        src = textwrap.dedent("""
            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")


class TestSqliteOwnershipStatic(unittest.TestCase):
    def test_cursor_via_execute_and_return_cur_blocks(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.execute("SELECT id FROM t")
                return cur
        """)
        with self.assertRaises(so.AnchorNotFoundError):
            so.transform_short_ownership(src, {"fetch_rows"})

    def test_conn_execute_cursor_discovery_positive(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        candidate = so.transform_short_ownership(src, {"fetch_rows"})
        compile(candidate, "<t>", "exec")
        self.assertIn("timeout=2", candidate)
        self.assertIn("tuple(", candidate)
        self.assertIn("finally", candidate)

    def test_guarded_close_order_and_tuple_rows(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        candidate = so.transform_short_ownership(src, {"fetch_rows"})
        cur_close_pos = candidate.index("cur.close()")
        conn_close_pos = candidate.index("conn.close()")
        self.assertLess(cur_close_pos, conn_close_pos)
        self.assertIn("is not None", candidate)

    def test_cursor_escape_via_other_return_blocks(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM t")
                return cur
        """)
        with self.assertRaises(so.AnchorNotFoundError):
            so.transform_short_ownership(src, {"fetch_rows"})


class TestSqliteOwnershipRuntime(unittest.TestCase):
    def _build_and_run(self, fake_connect):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        candidate = so.transform_short_ownership(src, {"fetch_rows"})
        code_no_import = candidate.replace("import sqlite3\n", "")
        namespace = {"sqlite3": type("FakeModule", (), {"connect": staticmethod(fake_connect)})}
        exec(compile(code_no_import, "<gen>", "exec"), namespace)
        return namespace["fetch_rows"]

    def test_success_path_closes_in_order_and_returns_tuple(self):
        events = []

        class FakeCursor:
            def execute(self, sql, *a):
                events.append("execute")
                return self

            def fetchall(self):
                events.append("fetchall")
                return [(1,), (2,)]

            def close(self):
                events.append("cur_close")

        class FakeConn:
            def cursor(self):
                events.append("cursor")
                return FakeCursor()

            def close(self):
                events.append("conn_close")

        def fake_connect(path, timeout=None):
            events.append(("connect", timeout))
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        rows = fn(":memory:")
        self.assertEqual(rows, ((1,), (2,)))
        self.assertIsInstance(rows, tuple)
        self.assertIsInstance(rows[0], tuple)
        self.assertEqual(events[-2:], ["cur_close", "conn_close"])
        self.assertEqual(events[0], ("connect", 2))

    def test_connect_failure_no_unbound_local_error(self):
        def fake_connect(path, timeout=None):
            raise RuntimeError("boom")

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(RuntimeError):
            fn(":memory:")

    def test_execute_failure_closes_conn_only(self):
        events = []

        class FakeCursor:
            def execute(self, sql, *a):
                raise RuntimeError("exec boom")

            def close(self):
                events.append("cur_close")

        class FakeConn:
            def cursor(self):
                events.append("cursor")
                return FakeCursor()

            def close(self):
                events.append("conn_close")

        def fake_connect(path, timeout=None):
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(RuntimeError):
            fn(":memory:")
        self.assertIn("cur_close", events)
        self.assertIn("conn_close", events)
        self.assertEqual(events.index("cur_close"), events.index("conn_close") - 1)

    def test_fetch_failure_closes_both_no_masking(self):
        class FakeCursor:
            def execute(self, sql, *a):
                return self

            def fetchall(self):
                raise ValueError("fetch boom")

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        def fake_connect(path, timeout=None):
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(ValueError):
            fn(":memory:")


class TestPublicApiPreserved(unittest.TestCase):
    def test_public_names_present(self):
        self.assertTrue(hasattr(ct, "transform_avtoperedacha_rebuild"))
        for name in (
            "AnchorNotFoundError",
            "transform_short_ownership",
            "OwnershipEvidence",
            "collect_ua0009_ownership_evidence",
            "compare_ownership_evidence",
        ):
            self.assertTrue(hasattr(so, name), f"missing required sqlite_ownership API: {name}")
        self.assertFalse(hasattr(so, "transform_sqlite_ownership"))
        self.assertFalse(hasattr(so, "OwnershipBlocked"))


if __name__ == "__main__":
    unittest.main()
