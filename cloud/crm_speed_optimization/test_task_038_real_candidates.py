"""Offline, deterministic executable tests for TASK 038: RebuildQueue
no-escaped-exception correction and real candidate-transform pipeline
(candidate_transforms.py) plus its integration into
crm_speed_gate_a.orchestrate_gate_a.

No network access. No PythonAnywhere paths. No /home/Carix access. Only
temporary directories, local threads/processes and a fake 404 HTTPS
opener are used. Existing tests are never modified, skipped, or
weakened.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""
import ast
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import candidate_transforms
import crm_speed_gate_a as gate_a
import sqlite_ownership

from test_crm_speed_gate_a import CLEAN_CARS_UI, _FakeOpener


def _fake_opener_404():
    return _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))


# ---------------------------------------------------------------------------
# 1. RebuildQueue no-escaped-exception correction (Defect A)
# ---------------------------------------------------------------------------

class RebuildQueueNoEscapeTests(unittest.TestCase):
    def test_deleted_lock_parent_no_escaped_exception(self):
        tmp = tempfile.mkdtemp(prefix="task038_rq_")
        sub = os.path.join(tmp, "sub")
        os.makedirs(sub)
        lock_path = os.path.join(sub, "rebuild.lock")

        excepthook_calls = []
        original_hook = threading.excepthook

        def spy_hook(args):
            excepthook_calls.append(args)

        threading.excepthook = spy_hook
        try:
            callback_calls = []
            q = canonical_modules.RebuildQueue(lambda: callback_calls.append(1), lock_path)
            shutil.rmtree(tmp)  # delete the lock parent before the worker runs
            status = q.enqueue()
            self.assertEqual(status, "accepted")

            deadline = time.time() + 3
            while not q.is_idle() and time.time() < deadline:
                time.sleep(0.01)
            q.shutdown(timeout=3)

            self.assertEqual(excepthook_calls, [])
            self.assertEqual(callback_calls, [])
            self.assertEqual(len(q.errors), 1)
            self.assertTrue(q.is_idle())
            self.assertFalse(os.path.exists(tmp))
        finally:
            threading.excepthook = original_hook
            shutil.rmtree(tmp, ignore_errors=True)

    def test_burst_still_coalesces_after_correction(self):
        tmp = tempfile.mkdtemp(prefix="task038_rq2_")
        try:
            gate = threading.Event()
            calls = []

            def cb():
                gate.wait(timeout=3)
                calls.append(1)

            q = canonical_modules.RebuildQueue(cb, os.path.join(tmp, "rebuild.lock"))
            self.assertEqual(q.enqueue(), "accepted")
            for _ in range(5):
                q.enqueue()
            gate.set()
            q.shutdown(timeout=5)
            self.assertEqual(len(calls), 2)
            self.assertEqual(q.runs, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3/4. usercustomize candidate transforms and two-path resolution
# ---------------------------------------------------------------------------

USERCUSTOMIZE_310_SOURCE = (
    '"""py310 sitecustomize"""\n'
    "import sys\n"
    "import team_bot\n"
    "X = 1\n"
    "def helper():\n"
    "    return 42\n"
)

USERCUSTOMIZE_313_SOURCE = (
    '"""py313 sitecustomize"""\n'
    "import sys\n"
    "import avtoperedacha\n"
    "Y = [1, 2, 3]\n"
)

USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT = (
    "import sys\n"
    "print('hello')\n"
)


class UsercustomizeTransformTests(unittest.TestCase):
    def test_forbidden_import_removed_harmless_preserved(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_310_SOURCE, "py310")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("team_bot", result["candidate"])
        self.assertIn("def helper", result["candidate"])
        self.assertIn("X = 1", result["candidate"])
        compile(result["candidate"], "<c>", "exec")

    def test_second_version_removes_different_forbidden_import(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_313_SOURCE, "py313")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("avtoperedacha", result["candidate"])
        self.assertIn("Y = ", result["candidate"])

    def test_unknown_top_level_side_effect_blocks(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT, "py310")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])


class TwoPathResolutionTests(unittest.TestCase):
    def test_two_distinct_paths_resolve(self):
        cfg = {"required_inputs": [
            "/x/python3.10/site-packages/usercustomize.py",
            "/x/python3.13/site-packages/usercustomize.py",
        ]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(err)
        self.assertNotEqual(p310, p313)

    def test_single_flat_usercustomize_blocks(self):
        cfg = {"required_inputs": ["/x/usercustomize.py"]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(p310)
        self.assertIsNone(p313)
        self.assertIsNotNone(err)

    def test_duplicate_python310_paths_block(self):
        cfg = {"required_inputs": [
            "/x/python3.10/a/usercustomize.py",
            "/x/python3.10/b/usercustomize.py",
            "/x/python3.13/site-packages/usercustomize.py",
        ]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(p310)
        self.assertIsNotNone(err)


# ---------------------------------------------------------------------------
# 5. start_safe.py / run_all.py singleton candidates
# ---------------------------------------------------------------------------

START_SAFE_SOURCE = (
    "import sys\n\n"
    "def main():\n"
    "    print('running')\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

RUN_ALL_SOURCE = (
    "import sys\n\n"
    "def entry():\n"
    "    return 1\n\n"
    "if __name__ == '__main__':\n"
    "    entry()\n"
)

START_SAFE_BAD_IMPORT_TIME_EFFECT = (
    "import sys\n"
    "sys.stdout.write('start')\n"
    "if __name__ == '__main__':\n"
    "    pass\n"
)

START_SAFE_BAD_TWO_MAIN = (
    "if __name__ == '__main__':\n"
    "    pass\n"
    "if __name__ == '__main__':\n"
    "    pass\n"
)


class LauncherSingletonTests(unittest.TestCase):
    LOCK_PATH = "/home/Carix/qa/crm_speed_task020/launcher_singleton.lock"

    def test_start_safe_and_run_all_get_same_singleton_lock(self):
        r1 = candidate_transforms.transform_launcher_singleton(START_SAFE_SOURCE, self.LOCK_PATH)
        r2 = candidate_transforms.transform_launcher_singleton(RUN_ALL_SOURCE, self.LOCK_PATH)
        self.assertEqual(r1["status"], "OK")
        self.assertEqual(r2["status"], "OK")
        self.assertIn("SingletonGuard", r1["candidate"])
        self.assertIn("SingletonGuard", r2["candidate"])
        self.assertIn(self.LOCK_PATH, r1["candidate"])
        self.assertIn(self.LOCK_PATH, r2["candidate"])
        self.assertIn(candidate_transforms.RUNTIME_MODULE_NAME, r1["candidate"])
        compile(r1["candidate"], "<c>", "exec")
        compile(r2["candidate"], "<c>", "exec")

    def test_import_time_side_effect_blocks(self):
        result = candidate_transforms.transform_launcher_singleton(START_SAFE_BAD_IMPORT_TIME_EFFECT, self.LOCK_PATH)
        self.assertEqual(result["status"], "BLOCKED")

    def test_multiple_main_anchors_block(self):
        result = candidate_transforms.transform_launcher_singleton(STARTSAFE if False else STARTSAFEBAD if False else START_SAFE_BAD_TWO_MAIN, self.LOCK_PATH)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 6. avtoperedacha rebuild-queue binding
# ---------------------------------------------------------------------------

AVTOPEREDACHA_SOURCE = (
    "import subprocess\n\n"
    "def generate_stranica_page():\n"
    "    return 'page'\n\n"
    "def handle_update():\n"
    "    subprocess.Popen(['python3', 'rebuild.py'])\n"
)

AVTOPEREDACHA_TWO_GENERATORS = (
    "import subprocess\n\n"
    "def generate_stranica_a():\n"
    "    return 1\n\n"
    "def generate_stranica_b():\n"
    "    return 2\n\n"
    "def handle():\n"
    "    subprocess.Popen(['x'])\n"
)


class AvtoperedachaRebuildTests(unittest.TestCase):
    def test_single_generator_binds_to_one_queue_no_spawn(self):
        result = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_SOURCE)
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("subprocess", result["candidate"])
        self.assertIn("_queue.enqueue()", result["candidate"])
        self.assertIn("RebuildQueue", result["candidate"])
        compile(result["candidate"], "<c>", "exec")
        # The generator must never be executed during transform.
        self.assertNotIn("generate_stranica_page()", result["candidate"].split("_queue =")[0])

    def test_two_generator_candidates_block(self):
        result = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_TWO_GENERATORS)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_spawn_present_blocks(self):
        source = "def generate_stranica_page():\n    return 1\n"
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 7. sqlite short ownership candidate for avtoperedacha/samokontrol
# ---------------------------------------------------------------------------

SAMOKONTROL_SOURCE = (
    "import sqlite3\n"
    "import time\n\n"
    "def check_db():\n"
    "    conn = sqlite3.connect('x.db')\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

SAMOKONTROL_NO_DB_FUNCTIONS = (
    "def helper():\n"
    "    return 1\n"
)


class SqliteOwnershipCandidateTests(unittest.TestCase):
    def test_samokontrol_candidate_materializes_and_closes_before_slow_work(self):
        result = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_SOURCE)
        self.assertEqual(result["status"], "OK")
        check = candidate_transforms.check_db_closed_before_slow_work_candidate(result["candidate"])
        self.assertEqual(check["status"], "OK", check)
        tree = ast.parse(result["candidate"])
        found_try = any(isinstance(n, ast.Try) and n.finalbody for n in ast.walk(tree))
        self.assertTrue(found_try)

    def test_avtoperedacha_style_db_function_also_transforms(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def kolonki_cars(conn=None):\n"
            "    conn = sqlite3.connect('y.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    time.sleep(0)\n"
            "    return rows\n"
        )
        result = candidate_transforms.transform_sqlite_short_ownership(source)
        self.assertEqual(result["status"], "OK")

    def test_no_db_functions_blocks(self):
        result = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_NO_DB_FUNCTIONS)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 8/9/13. compile all eight candidates + deterministic repeat + support module
# ---------------------------------------------------------------------------

class EightCandidateCompileAndDeterminismTests(unittest.TestCase):
    def test_compile_all_eight_without_import(self):
        support = candidate_transforms.generate_runtime_support_source()
        r_uc310 = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_310_SOURCE, "py310")
        r_uc313 = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_313_SOURCE, "py313")
        r_start = candidate_transforms.transform_launcher_singleton(START_SAFE_SOURCE, LauncherSingletonTests.LOCK_PATH)
        r_run = candidate_transforms.transform_launcher_singleton(RUN_ALL_SOURCE, LauncherSingletonTests.LOCK_PATH)
        r_avto = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_SOURCE)
        r_samo = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_SOURCE)
        cars_ui_result = gate_a.transform_cars_ui(CLEAN_CARS_UI)

        sources = {
            "crm_speed_runtime.py": support,
            "usercustomize_py310.py": r_uc310["candidate"],
            "usercustomize_py313.py": r_uc313["candidate"],
            "start_safe.py": r_start["candidate"],
            "run_all.py": r_run["candidate"],
            "avtoperedacha.py": r_avto["candidate"],
            "samokontrol.py": r_samo["candidate"],
            "cars_ui.py": cars_ui_result["candidate"],
        }
        self.assertEqual(len(sources), 8)
        for name, src in sources.items():
            self.assertIsNotNone(src, name)
            compile(src, name, "exec")
        self.assertNotIn("usercustomize_py310", sys.modules)
        self.assertNotIn("crm_speed_runtime", sys.modules)

    def test_all_seven_transforms_plus_support_are_deterministic(self):
        cases = [
            (candidate_transforms.transform_usercustomize, USERCUSTOMIZE_310_SOURCE, ("py310",)),
            (candidate_transforms.transform_usercustomize, USERCUSTOMIZE_313_SOURCE, ("py313",)),
            (candidate_transforms.transform_launcher_singleton, START_SAFE_SOURCE, (LauncherSingletonTests.LOCK_PATH,)),
            (candidate_transforms.transform_launcher_singleton, RUN_ALL_SOURCE, (LauncherSingletonTests.LOCK_PATH,)),
            (candidate_transforms.transform_avtoperedacha_rebuild, AVTOPEREDACHA_SOURCE, ()),
            (candidate_transforms.transform_sqlite_short_ownership, SAMOKONTROL_SOURCE, ()),
            (gate_a.transform_cars_ui, CLEAN_CARS_UI, ()),
        ]
        for fn, source, args in cases:
            measurement = gate_a.measure_deterministic_repeat(fn, source, args=args, repeats=10)
            self.assertTrue(measurement["deterministic"], fn.__name__)

        support_hashes = set()
        for _ in range(10):
            support_hashes.add(gate_a._sha256_bytes(candidate_transforms.generate_runtime_support_source().encode("utf-8")))
        self.assertEqual(len(support_hashes), 1)

    def test_blocked_transform_never_yields_a_candidate(self):
        blocked_results = [
            candidate_transforms.transform_usercustomize(USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT, "py310"),
            candidate_transforms.transform_launcher_singleton(START_SAFE_BAD_TWO_MAIN, LauncherSingletonTests.LOCK_PATH),
            candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_TWO_GENERATORS),
            candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_NO_DB_FUNCTIONS),
        ]
        for r in blocked_results:
            self.assertEqual(r["status"], "BLOCKED")
            self.assertIsNone(r["candidate"])


# ---------------------------------------------------------------------------
# 10/12/14. Full synthetic orchestrate_gate_a integration
# ---------------------------------------------------------------------------

def _make_full_extended_config():
    tmp = tempfile.mkdtemp(prefix="task038_full_")
    py310_dir = os.path.join(tmp, "python3.10", "site-packages")
    py313_dir = os.path.join(tmp, "python3.13", "site-packages")
    os.makedirs(py310_dir)
    os.makedirs(py313_dir)

    required = []

    def _write(path, content):
        with open(path, "w") as fh:
            fh.write(content)
        required.append(path)

    _write(os.path.join(py310_dir, "usercustomize.py"), USERCUSTOMIZE_310_SOURCE)
    _write(os.path.join(py313_dir, "usercustomize.py"), USERCUSTOMIZE_313_SOURCE)
    _write(os.path.join(tmp, "start_safe.py"), START_SAFE_SOURCE)
    _write(os.path.join(tmp, "run_all.py"), RUN_ALL_SOURCE)
    _write(os.path.join(tmp, "cars_ui.py"), CLEAN_CARS_UI)
    _write(os.path.join(tmp, "avtoperedacha.py"), AVTOPEREDACHA_SOURCE)
    _write(os.path.join(tmp, "samokontrol.py"), SAMOKONTROL_SOURCE)
    _write(os.path.join(tmp, "db.py"), "# fixture\n")
    _write(os.path.join(tmp, "team_bot.py"), "# fixture\n")
    _write(os.path.join(tmp, "stranica.py"), "# fixture\n")

    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_path = os.path.join(tmp, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha = gate_a._sha256_file(backup_path)

    site_root = os.path.join(tmp, "site")
    os.makedirs(site_root)
    with open(os.path.join(site_root, "index.html"), "w") as fh:
        fh.write("<html></html>")
    with open(os.path.join(site_root, "katalog.html"), "w") as fh:
        fh.write("<html></html>")

    run_root = os.path.join(tmp, "qa_root")
    os.makedirs(run_root, mode=0o700)

    config = {
        "required_inputs": required,
        "site_roots": {site_root: ["index.html", "katalog.html"]},
        "ua0009_url": "https://example.com/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": [],
        "db_function_source": None,
        "min_free_bytes": 1024,
    }
    return config, tmp


class FullExtendedOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_full_extended_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot(self):
        snap = {}
        for p in self.cfg["required_inputs"]:
            with open(p, "rb") as fh:
                snap[p] = fh.read()
        return snap

    def test_extended_available_and_eight_artifacts_written_originals_unchanged(self):
        before = self._snapshot()
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        after = self._snapshot()
        self.assertEqual(before, after)

        self.assertTrue(receipt["extended_candidates"]["available"], receipt["extended_candidates"])
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        candidates_dir = os.path.join(run_dir, "candidates")
        diffs_dir = os.path.join(run_dir, "diffs")
        expected_names = {
            "usercustomize_py310.py", "usercustomize_py313.py", "start_safe.py",
            "run_all.py", "avtoperedacha.py", "samokontrol.py", "crm_speed_runtime.py",
        }
        actual_names = set(os.listdir(candidates_dir))
        self.assertTrue(expected_names.issubset(actual_names))
        diff_names = set(os.listdir(diffs_dir))
        for name in expected_names:
            self.assertIn(name + ".diff", diff_names)

        self.assertEqual(
            set(receipt["extended_candidates"]["candidate_hashes"].keys()) - {"cars_ui.py"},
            expected_names - set(),
        )
        self.assertIn("crm_speed_runtime.py", receipt["extended_candidates"]["candidate_hashes"])
        self.assertIsNotNone(receipt["extended_candidates"]["support_module_sha256"])

    def test_phase80_uses_candidate_strings_not_original(self):
        seen_sources = []
        original_check = gate_a.check_usercustomize_inert

        def spy(source):
            seen_sources.append(source)
            return original_check(source)

        import unittest.mock as mock
        with mock.patch.object(gate_a, "check_usercustomize_inert", spy):
            gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertTrue(seen_sources)
        for s in seen_sources:
            self.assertNotIn("team_bot", s)
            self.assertNotIn("avtoperedacha", s)

    def test_no_candidate_module_ever_imported(self):
        gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        for name in ("usercustomize_py310", "usercustomize_py313", "start_safe", "run_all",
                     "avtoperedacha", "samokontrol", "crm_speed_runtime"):
            self.assertNotIn(name, sys.modules)


# ---------------------------------------------------------------------------
# Compile sanity for files touched by this task
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in (
            "canonical_modules.py", "candidate_transforms.py", "sqlite_ownership.py",
            "crm_speed_gate_a.py", "test_task_038_real_candidates.py",
        ):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()
