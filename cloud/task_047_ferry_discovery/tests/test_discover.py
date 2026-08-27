import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discover  # noqa: E402


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task047_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestSafeReadFile(TempDirCase):
    def test_missing_file_reported_missing(self):
        res = discover.safe_read_file(self.tmp, "does/not/exist.html")
        self.assertEqual(res["status"], "MISSING")

    def test_path_escape_relative_blocked(self):
        res = discover.safe_read_file(self.tmp, "../outside.txt")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("PATH_ESCAPE", res["reason"])

    def test_symlink_final_blocked(self):
        target = os.path.join(self.tmp, "real.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("hello")
        link = os.path.join(self.tmp, "link.txt")
        os.symlink(target, link)
        res = discover.safe_read_file(self.tmp, "link.txt")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "SYMLINK_FINAL")

    def test_symlink_parent_blocked(self):
        outside = tempfile.mkdtemp(prefix="task047_outside_")
        try:
            linked_dir = os.path.join(self.tmp, "sub")
            os.symlink(outside, linked_dir)
            with open(os.path.join(outside, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            res = discover.safe_read_file(self.tmp, "sub/f.txt")
            self.assertEqual(res["status"], "BLOCKED")
            self.assertEqual(res["reason"], "SYMLINK_PARENT")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_hardlink_blocked(self):
        target = os.path.join(self.tmp, "a.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("data")
        link = os.path.join(self.tmp, "b.txt")
        os.link(target, link)
        res = discover.safe_read_file(self.tmp, "a.txt")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "HARDLINK_DETECTED")

    def test_oversize_blocked(self):
        target = os.path.join(self.tmp, "big.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("x" * 1000)
        with mock.patch.object(discover, "MAX_SIZE", 10):
            res = discover.safe_read_file(self.tmp, "big.txt")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "OVERSIZE")

    def test_toctou_mismatch_blocked(self):
        target = os.path.join(self.tmp, "c.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("stable")
        real_lstat = os.lstat

        class FakeStat:
            def __init__(self, real):
                self.st_dev = real.st_dev
                self.st_ino = real.st_ino
                self.st_size = real.st_size + 1
                self.st_mtime_ns = real.st_mtime_ns
                self.st_mode = real.st_mode
                self.st_nlink = real.st_nlink

        def fake_lstat(path):
            real = real_lstat(path)
            if path == target:
                return FakeStat(real)
            return real

        with mock.patch.object(discover.os, "lstat", side_effect=fake_lstat):
            res = discover.safe_read_file(self.tmp, "c.txt")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "TOCTOU_MISMATCH")

    def test_non_utf8_blocked(self):
        target = os.path.join(self.tmp, "bad.bin")
        with open(target, "wb") as f:
            f.write(b"\xff\xfe\x00\x01")
        res = discover.safe_read_file(self.tmp, "bad.bin")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "NON_UTF8")

    def test_ok_file_sha256_and_identity(self):
        target = os.path.join(self.tmp, "ok.txt")
        content = b"hello ferry"
        with open(target, "wb") as f:
            f.write(content)
        res = discover.safe_read_file(self.tmp, "ok.txt")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(res["size"], len(content))


class TestRegistry(unittest.TestCase):
    def test_katalog_present_no_public_catalog(self):
        flat = [p for files in discover.REGISTRY.values() for p in files]
        self.assertIn("video/katalog.html", flat)
        self.assertNotIn("catalog.html", flat)
        self.assertFalse(any("video/public" in p for p in flat))

    def test_python_modules_present(self):
        flat = discover.REGISTRY["python_modules"]
        for name in ("stranica.py", "yadro.py", "master_card.py", "cars_ui.py",
                     "team_bot.py", "avtoperedacha.py", "db.py", "run_all.py",
                     "start_safe.py"):
            self.assertIn(name, flat)


class TestSecretRedaction(unittest.TestCase):
    def test_scan_detects_secret(self):
        s = '{"token": "abcdef123"}'
        self.assertTrue(discover.scan_for_secrets(s))

    def test_redact_removes_value(self):
        s = "api-key=SUPERSECRET1234"
        red = discover.redact_secrets(s)
        self.assertNotIn("SUPERSECRET1234", red)

    def test_normal_receipt_has_no_secret(self):
        s = '{"status": "OK", "sha256": "abc123"}'
        self.assertFalse(discover.scan_for_secrets(s))


class TestCLI(unittest.TestCase):
    def test_cli_emits_single_json_object(self):
        env = dict(os.environ)
        env["FERRY_DISCOVERY_BASE_DIR"] = tempfile.mkdtemp(prefix="task047_cli_")
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(here, "discover.py")],
                capture_output=True, text=True, env=env, timeout=30,
            )
            lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            import json
            obj = json.loads(lines[0])
            self.assertIn("status", obj)
        finally:
            shutil.rmtree(env["FERRY_DISCOVERY_BASE_DIR"], ignore_errors=True)


class TestCRM(TempDirCase):
    def _make_db(self, path, with_valid_table=True):
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        if with_valid_table:
            cur.execute("CREATE TABLE cars (ua_id TEXT, stage TEXT, container TEXT, tracking TEXT)")
            for i in range(1, 10):
                cur.execute("INSERT INTO cars VALUES (?,?,?,?)",
                            ("UA-%04d" % i, "sea", "CNT%d" % i, "TRK%d" % i))
        else:
            cur.execute("CREATE TABLE unrelated (x TEXT)")
            cur.execute("INSERT INTO unrelated VALUES ('nothing')")
        conn.commit()
        conn.close()

    def test_missing_db(self):
        res = discover.crm_readonly_summary(os.path.join(self.tmp, "nope.db"))
        self.assertEqual(res["status"], "MISSING")

    def test_exact_nine_and_quick_check(self):
        path = os.path.join(self.tmp, "crm.db")
        self._make_db(path, with_valid_table=True)
        res = discover.crm_readonly_summary(path)
        self.assertEqual(res["status"], "OK")
        self.assertTrue(res["quick_check"])
        self.assertEqual(len(res["results"]), 9)
        for ua in discover.UA_IDS:
            self.assertIn(ua, res["results"])
            self.assertIsNotNone(res["results"][ua])

    def test_ambiguous_schema_blocked(self):
        path = os.path.join(self.tmp, "crm.db")
        self._make_db(path, with_valid_table=False)
        res = discover.crm_readonly_summary(path)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("AMBIGUOUS_SCHEMA", res["reason"])

    def test_db_unchanged_after_read(self):
        path = os.path.join(self.tmp, "crm.db")
        self._make_db(path, with_valid_table=True)
        with open(path, "rb") as f:
            before = hashlib.sha256(f.read()).hexdigest()
        discover.crm_readonly_summary(path)
        with open(path, "rb") as f:
            after = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(before, after)


class TestCompiles(unittest.TestCase):
    def test_module_compiles(self):
        import py_compile
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        py_compile.compile(os.path.join(here, "discover.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
