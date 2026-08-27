import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import discover

RU_STATUS = "\u0412 \u043c\u043e\u0440\u0435"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_valid_root(root: Path, ferry_text=True):
    for rel in discover.HTML_CORE_PAGES:
        _write(root / rel, "<html><body><p>ok</p></body></html>")
    for i, rel in enumerate(discover.UA_CARD_PAGES, start=1):
        body = f'<div class="chip">{RU_STATUS}</div>' if ferry_text else "<p>ok</p>"
        _write(root / rel, f"<html><body>{body}</body></html>")
    for rel in discover.PY_MODULES:
        _write(root / rel, "def f():\n    return 1\n")
    _build_valid_db(root / discover.DB_FILE_NAME)


def _build_valid_db(db_path: Path, n_ids=9):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE cars (auto_number TEXT, sea_container TEXT)")
    for i in range(1, n_ids + 1):
        conn.execute(
            "INSERT INTO cars (auto_number, sea_container) VALUES (?, ?)",
            (f"UA-{i:04d}", f"CONT{i:03d}"),
        )
    conn.commit()
    conn.close()


class DiscoverTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="task052_")
        self.root = Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_missing_root_blocks(self):
        receipt = discover.run_discovery(self.root / "does_not_exist")
        self.assertEqual(receipt["status"], "BLOCKED")

    def test_missing_core_page_blocks(self):
        _build_valid_root(self.root)
        os.remove(self.root / "video/index.html")
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("MISSING_CORE_PAGES", receipt["reasons"])

    def test_full_registry_ok(self):
        _build_valid_root(self.root)
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["status"], "OK", receipt)
        self.assertGreater(receipt["total_source_occurrences"], 0)
        self.assertEqual(receipt["crm"]["status"], "PASS")

    def test_zero_occurrences_blocks(self):
        _build_valid_root(self.root, ferry_text=False)
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ZERO_OCCURRENCES", receipt["reasons"])

    def test_ambiguous_target_blocks(self):
        _build_valid_root(self.root)
        _write(self.root / "video/UA-0001.html", "<html><body><div><span>\u041c\u043e\u0440\u0435</span></div></body></html>")
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("AMBIGUOUS_TARGET", receipt["reasons"])

    def test_missing_ua_ids_in_crm_blocks(self):
        _build_valid_root(self.root)
        _build_valid_db(self.root / discover.DB_FILE_NAME, n_ids=8)
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertEqual(receipt["crm"]["reason"], "MISSING_IDS")

    def test_crm_schema_mismatch_blocks(self):
        _build_valid_root(self.root)
        db_path = self.root / discover.DB_FILE_NAME
        os.remove(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE cars (id TEXT)")
        conn.commit()
        conn.close()
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["crm"]["reason"], "SCHEMA_MISMATCH")

    def test_python_syntax_error_blocks_module(self):
        _build_valid_root(self.root)
        _write(self.root / "db.py", "def broken(:\n")
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["python"]["db.py"]["status"], "BLOCKED")

    def test_safe_read_rejects_hardlink_nlink(self):
        _build_valid_root(self.root)
        target = self.root / "video/index.html"
        extra_link = self.root / "video/index_link.html"
        try:
            os.link(target, extra_link)
        except OSError:
            self.skipTest("hardlinks not supported on this filesystem")
            return
        meta, data = discover.safe_read_file(target, self.root)
        self.assertEqual(meta["status"], "BLOCKED")
        self.assertEqual(meta["reason"], "NLINK_NOT_ONE")

    def test_safe_read_rejects_symlink_target(self):
        _build_valid_root(self.root)
        real_file = self.root / "video/index.html"
        link_path = self.root / "video/link.html"
        try:
            os.symlink(real_file, link_path)
        except OSError:
            self.skipTest("symlinks not supported on this filesystem")
            return
        meta, data = discover.safe_read_file(link_path, self.root)
        self.assertEqual(meta["status"], "BLOCKED")

    def test_safe_read_rejects_oversize(self):
        _build_valid_root(self.root)
        big = self.root / "video/big.html"
        _write(big, "x" * 1000)
        meta, data = discover.safe_read_file(big, self.root, max_bytes=10)
        self.assertEqual(meta["status"], "BLOCKED")
        self.assertEqual(meta["reason"], "OVERSIZE")

    def test_safe_read_missing_file(self):
        _build_valid_root(self.root)
        meta, data = discover.safe_read_file(self.root / "video/absent.html", self.root)
        self.assertEqual(meta["status"], "BLOCKED")
        self.assertEqual(meta["reason"], "MISSING")

    def test_receipt_is_strict_json(self):
        import json
        _build_valid_root(self.root)
        receipt = discover.run_discovery(self.root)
        s = discover.serialize_receipt(receipt)
        parsed = json.loads(s)
        self.assertEqual(parsed["status"], receipt["status"])

    def test_secret_redaction_blocks_final_receipt(self):
        fake_receipt = {"status": "OK", "note": "password: hunter2"}
        s = discover.serialize_receipt(fake_receipt)
        self.assertNotIn("hunter2", s)

    def test_redact_obj_recursive(self):
        obj = {"a": ["token: abc123", {"b": "secret: xyz"}]}
        red = discover.redact_obj(obj)
        self.assertNotIn("abc123", str(red))
        self.assertNotIn("xyz", str(red))

    def test_markers_present_and_no(self):
        _build_valid_root(self.root)
        receipt = discover.run_discovery(self.root)
        m = receipt["markers"]
        self.assertEqual(m["PRODUCTION_TOUCHED"], "NO")
        self.assertEqual(m["CRM_DB_WRITTEN"], "NO")
        self.assertEqual(m["GATE_B_EXECUTED"], "NO")
        self.assertEqual(m["UA_0009_PUBLISHED"], "NO")

    def test_run_twice_deterministic(self):
        _build_valid_root(self.root)
        r1 = discover.run_discovery(self.root)
        r2 = discover.run_discovery(self.root)
        self.assertEqual(discover.serialize_receipt(r1), discover.serialize_receipt(r2))

    def test_db_missing_blocks_crm(self):
        _build_valid_root(self.root)
        os.remove(self.root / discover.DB_FILE_NAME)
        receipt = discover.run_discovery(self.root)
        self.assertEqual(receipt["crm"]["reason"], "DB_MISSING")


if __name__ == "__main__":
    unittest.main()
