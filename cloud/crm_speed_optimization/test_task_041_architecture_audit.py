"""Offline, deterministic executable tests for TASK 041: closing the
remaining fail-open candidate-transform defects identified by
independent audit of TASK 038 (commit
be8113a3c2bc0e1b6b5173c5fd13736332b13da2).

No network access. No PythonAnywhere paths. No /home/Carix access. Only
temporary directories and in-memory fixtures are used. Existing tests
are never modified except as explicitly authorized in
test_task_038_real_candidates.py (invalid assertion correction +
positive-fixture update).

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import candidate_transforms
import crm_speed_gate_a as gate_a
import sqlite_ownership

from test_task_038_real_candidates import (
    _make_full_extended_config, _fake_opener_404,
)


# ---------------------------------------------------------------------------
# 1. usercustomize positive allowlist (Defect: `import requests` -> OK)
# ---------------------------------------------------------------------------

class UsercustomizeAllowlistTests(unittest.TestCase):
    def test_import_requests_blocks(self):
        result = candidate_transforms.transform_usercustomize("import requests\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])

    def test_mixed_sys_team_bot_single_statement_preserves_sys_removes_team_bot(self):
        source = "import sys, team_bot\n"
        result = candidate_transforms.transform_usercustomize(source, "py310")
        self.assertEqual(result["status"], "OK")
        self.assertIn("import sys", result["candidate"])
        self.assertNotIn("team_bot", result["candidate"])

    def test_alias_and_from_import_variants(self):
        source = (
            "import team_bot as tb\n"
            "from team_bot import helper as h\n"
            "import sys as system_module\n"
        )
        result = candidate_transforms.transform_usercustomize(source, "py313")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("team_bot", result["candidate"])
        self.assertIn("sys", result["candidate"])

    def test_dynamic_import_blocks(self):
        result = candidate_transforms.transform_usercustomize("import importlib\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_unknown_local_import_blocks(self):
        result = candidate_transforms.transform_usercustomize("import cars_ui\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_from_requests_import_get_blocks(self):
        result = candidate_transforms.transform_usercustomize("from requests import get\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_py310_and_py313_remain_distinct_and_deterministic(self):
        source = "import sys\nimport team_bot\n"
        r1 = candidate_transforms.transform_usercustomize(source, "py310")
        r2 = candidate_transforms.transform_usercustomize(source, "py313")
        self.assertEqual(r1["metadata"]["version"], "py310")
        self.assertEqual(r2["metadata"]["version"], "py313")
        for _ in range(5):
            self.assertEqual(candidate_transforms.transform_usercustomize(source, "py310"), r1)


# ---------------------------------------------------------------------------
# 2. avtoperedacha call-graph proof negatives
# ---------------------------------------------------------------------------

class RebuildCallGraphNegativeTests(unittest.TestCase):
    def test_unrelated_ffmpeg_spawn_blocks(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_video():\n"
            "    subprocess.Popen(['ffmpeg', '-i', 'in.mp4', 'out.mp4'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])

    def test_generator_with_no_in_process_call_blocks(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def handle_update():\n"
            "    subprocess.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")

    def test_nonzero_argument_generator_excluded(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page(extra):\n"
            "    return extra\n\n"
            "def call_it():\n"
            "    return generate_stranica_page(1)\n\n"
            "def handle_update():\n"
            "    subprocess.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")

    def test_aliased_subprocess_import_still_resolves(self):
        source = (
            "import subprocess as sp\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_update():\n"
            "    sp.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("sp.Popen", result["candidate"])

    def test_dynamic_command_construction_does_not_count_as_anchor(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_update(cmd):\n"
            "    subprocess.Popen(cmd)\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 3. sqlite ownership: per-handle tracking, write-SQL, branch, escape
# ---------------------------------------------------------------------------

def _get_func(source, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError("function not found")


class SqliteOwnershipHardeningTests(unittest.TestCase):
    def test_unrelated_close_never_marks_real_handle_closed(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def f(other):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    other.close()\n"
            "    time.sleep(0)\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return 1\n"
        )
        func = _get_func(source, "f")
        violations = sqlite_ownership.verify_no_live_handle_across_slow_call(func)
        self.assertTrue(violations, "unrelated close must never suppress a real violation")

    def test_real_close_before_slow_call_has_no_violation(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    time.sleep(0)\n"
            "    return rows\n"
        )
        func = _get_func(source, "f")
        violations = sqlite_ownership.verify_no_live_handle_across_slow_call(func)
        self.assertEqual(violations, [])

    def test_multiple_connections_block_transform(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn1 = sqlite3.connect('a.db')\n"
            "    conn2 = sqlite3.connect('b.db')\n"
            "    conn1.close()\n"
            "    conn2.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_caller_owned_handle_not_touched(self):
        source = (
            "def f(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    return cur.fetchall()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_branch_in_ownership_segment_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f(flag):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    if flag:\n"
            "        cur = conn.execute('SELECT 1')\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_cursor_escape_via_return_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    return cur\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_write_sql_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    conn.execute('INSERT INTO t VALUES (1)')\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_commit_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    conn.commit()\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_fetchall_materialized_into_tuple(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        candidate = sqlite_ownership.transform_short_ownership(source, {"f"})
        compile(candidate, "<c>", "exec")
        self.assertIn("tuple(rows)", candidate)

    def test_cursor_closed_before_connection_in_generated_order(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    return rows\n"
        )
        candidate = sqlite_ownership.transform_short_ownership(source, {"f"})
        cur_idx = candidate.index("cur.close()")
        conn_idx = candidate.index("conn.close()")
        self.assertLess(cur_idx, conn_idx)


# ---------------------------------------------------------------------------
# 4. RebuildQueue callback error sanitization
# ---------------------------------------------------------------------------

class RebuildQueueSanitizationTests(unittest.TestCase):
    def test_callback_exception_message_never_stored(self):
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp(prefix="task041_sanitize_")
        try:
            def bad_callback():
                raise ValueError("secret-token-abc123-should-never-leak")

            q = canonical_modules.RebuildQueue(bad_callback, os.path.join(tmp, "r.lock"))
            q.enqueue()
            q.shutdown(timeout=3)
            self.assertTrue(any(e.startswith("CallbackError:ValueError") for e in q.errors))
            for e in q.errors:
                self.assertNotIn("secret-token", e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generated_runtime_support_also_sanitizes(self):
        source = candidate_transforms.generate_runtime_support_source()
        self.assertIn('"CallbackError:"', source)
        self.assertNotIn("str(exc)[:500]", source)


# ---------------------------------------------------------------------------
# 5. launcher transform structural correctness
# ---------------------------------------------------------------------------

class LauncherStructuralTests(unittest.TestCase):
    LOCK_PATH = "/home/Carix/qa/crm_speed_task020/launcher_singleton.lock"

    def test_future_import_preserved_before_runtime_import(self):
        source = (
            '"""doc"""\n'
            "from __future__ import annotations\n"
            "import sys\n\n"
            "def main():\n"
            "    pass\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = candidate_transforms.transform_launcher_singleton(source, self.LOCK_PATH)
        self.assertEqual(result["status"], "OK")
        tree = ast.parse(result["candidate"])
        future_idx = next(i for i, n in enumerate(tree.body)
                           if isinstance(n, ast.ImportFrom) and n.module == "__future__")
        runtime_idx = next(i for i, n in enumerate(tree.body)
                            if isinstance(n, ast.ImportFrom) and n.module == candidate_transforms.RUNTIME_MODULE_NAME)
        self.assertLess(future_idx, runtime_idx)

    def test_duplicate_start_uses_exit_code_78_and_diagnostic(self):
        source = (
            "def main():\n"
            "    pass\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = candidate_transforms.transform_launcher_singleton(source, self.LOCK_PATH)
        self.assertEqual(result["status"], "OK")
        self.assertIn("SystemExit(78)", result["candidate"])
        self.assertIn("stderr.write", result["candidate"])


# ---------------------------------------------------------------------------
# 6. orchestrator: exactly eight candidates, no legacy fallback to PASS
# ---------------------------------------------------------------------------

class OrchestratorEightCandidateTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_full_extended_config()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exactly_eight_extended_candidates_no_legacy_usercustomize(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        candidates_dir = os.path.join(run_dir, "candidates")
        names = set(os.listdir(candidates_dir))
        self.assertEqual(len(names), 8, names)
        self.assertIn("cars_ui.py", names)
        self.assertNotIn("usercustomize.py", names)

    def test_blocked_launcher_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        # Corrupt start_safe.py so its transform is structurally BLOCKED
        # (two main anchors), proving no legacy fallback can reach PASS.
        start_safe_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "start_safe.py"][0]
        with open(start_safe_path, "w") as fh:
            fh.write(
                "if __name__ == '__main__':\n    pass\n"
                "if __name__ == '__main__':\n    pass\n"
            )
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])

    def test_blocked_avtoperedacha_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        avto_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "avtoperedacha.py"][0]
        with open(avto_path, "w") as fh:
            fh.write("def helper():\n    return 1\n")
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])

    def test_blocked_sqlite_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        samo_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "samokontrol.py"][0]
        with open(samo_path, "w") as fh:
            fh.write("def helper():\n    return 1\n")
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])


# ---------------------------------------------------------------------------
# Compile sanity
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in (
            "canonical_modules.py", "candidate_transforms.py", "sqlite_ownership.py",
            "crm_speed_gate_a.py", "test_task_038_real_candidates.py",
            "test_task_041_architecture_audit.py",
        ):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()
