import hashlib
import json
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


class TestPythonLiteralContext(unittest.TestCase):
    def test_structural_html_literal_is_user_facing_without_source_relay(self):
        source = (
            "PAGE = '<div class=\"status-pill\">В море</div>'\n"
        )
        items = discover._inventory_python_literals(source, "stranica.py")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["classification"], "USER_FACING")
        self.assertEqual(item["assignment"], "PAGE")
        self.assertEqual(item["structural_changes"], 1)
        self.assertEqual(item["structural_ambiguous"], 0)
        self.assertNotIn(source, json.dumps(item, ensure_ascii=False))
        self.assertEqual(len(item["literal_sha256"]), 64)

    def test_ambiguous_dictionary_value_reports_bounded_ast_context(self):
        source = "MESSAGES = {'ru': 'В море'}\n"
        items = discover._inventory_python_literals(source, "yadro.py")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["classification"], "AMBIGUOUS")
        self.assertEqual(item["assignment"], "MESSAGES")
        self.assertEqual(item["role"], "DICT_VALUE")
        self.assertEqual(item["dict_key"], "ru")
        self.assertEqual(item["structural_changes"], 0)
        self.assertGreaterEqual(item["structural_ambiguous"], 1)

    def test_legacy_input_map_remains_preserved(self):
        source = "LEGACY_INPUT_MAP = {'В море': 'sea'}\n"
        items = discover._inventory_python_literals(source, "yadro.py")
        self.assertEqual(items[0]["classification"], "LEGACY_INPUT_ALIAS")
        self.assertEqual(items[0]["role"], "DICT_KEY")

    def test_live_ui_context_allowlists_are_user_facing(self):
        source = '''ETAP_KOROTKO = ["В море", "У морі"]
ETAPY_GLAVNOY = ["🌊 В море", "🌊 У морі"]
FILTRY = ["В море", "У морі"]
SROKI = ["Море: 30 дней"]
POTOK = ["Корея", "Море", "Грузия"]
def blok_pribytiya():
    return list(enumerate(("Корея", "Море", "Грузия", "Киев")))
def sobrat_katalog(c):
    c.append("<span title='Море'>этап</span>")
'''
        items = discover._inventory_python_literals(source, "yadro.py")
        self.assertGreaterEqual(len(items), 8)
        self.assertTrue(all(item["classification"] == "USER_FACING" for item in items))

    def test_python_transform_changes_only_approved_string_tokens(self):
        source = '''# formatting must stay exact
ETAP_KOROTKO = ["В море", 'У морі']
POTOK=("Корея","Море","Грузия","Киев")
def sobrat_katalog(c):
    c.append("<span title='Море'>этап</span>")
'''
        candidate, changes = discover.transform_python_source(source, "yadro.py")
        self.assertIn('# formatting must stay exact', candidate)
        self.assertIn('["На пароме", \'На поромі\']', candidate)
        self.assertIn('POTOK=("Корея","Паром","Грузия","Киев")', candidate)
        self.assertIn("title='Паром'", candidate)
        self.assertEqual(sum(item["replacements"] for item in changes), 4)
        second, second_changes = discover.transform_python_source(candidate, "yadro.py")
        self.assertEqual(second, candidate)
        self.assertEqual(second_changes, [])

    def test_python_transform_blocks_unapproved_literal(self):
        with self.assertRaises(discover.PythonTransformBlocked):
            discover.transform_python_source('x = "В море"\n', "yadro.py")

    def test_python_transform_handles_utf8_column_offsets(self):
        source = 'ETAP_KOROTKO = ["тест", "В море"]\n'
        candidate, changes = discover.transform_python_source(source, "yadro.py")
        self.assertEqual(candidate, 'ETAP_KOROTKO = ["тест", "На пароме"]\n')
        self.assertEqual(sum(item["replacements"] for item in changes), 1)

    def test_python_transform_preserves_multiline_token_layout(self):
        source = '''def sobrat_info(c):
    c.append("""<p>
Море: Корея → Грузия
</p>""")
'''
        candidate, changes = discover.transform_python_source(source, "stranica.py")
        self.assertEqual(candidate, source.replace("Море:", "Паром:"))
        self.assertEqual(sum(item["replacements"] for item in changes), 1)

    def test_python_transform_preserves_implicit_concatenation(self):
        source = '''def sobrat_katalog(c):
    c.append("<span>"  "Море"  "</span>")
'''
        candidate, changes = discover.transform_python_source(source, "stranica.py")
        self.assertEqual(candidate, source.replace('"Море"', '"Паром"'))
        self.assertEqual(sum(item["replacements"] for item in changes), 1)

    def test_python_transform_blocks_target_split_across_tokens(self):
        source = '''def sobrat_katalog(c):
    c.append("В " "море")
'''
        with self.assertRaisesRegex(
            discover.PythonTransformBlocked, "literal_target_crosses_tokens"
        ):
            discover.transform_python_source(source, "stranica.py")


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


class TestFerryPhase1Discovery(TempDirCase):
    def _make_real_db(self, duplicate=False):
        path = os.path.join(self.tmp, "crm.db")
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE cars (auto_number TEXT, sea_container TEXT, status TEXT)"
        )
        for i in range(1, 10):
            conn.execute(
                "INSERT INTO cars VALUES (?,?,?)",
                ("UA-%04d" % i, "CONT%03d" % i, "sea"),
            )
        if duplicate:
            conn.execute("INSERT INTO cars VALUES (?,?,?)", ("UA-0001", "DUP", "sea"))
        conn.commit()
        conn.close()
        return path

    def _make_full_root(self, ferry=True):
        for rel in discover.REGISTRY["video_pages"]:
            path = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            body = '<div class="status-pill">В море</div>' if ferry else '<p>ok</p>'
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("<html><body>%s</body></html>" % body)
        for rel in discover.REGISTRY["python_modules"]:
            path = os.path.join(self.tmp, rel)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("def f():\n    return 1\n")
        self._make_real_db()

    def test_real_cars_schema(self):
        path = self._make_real_db()
        result = discover.crm_readonly_summary(path)
        self.assertEqual(result["status"], "OK", result)
        self.assertEqual(result["table"], "cars")
        self.assertEqual(result["id_column"], "auto_number")
        self.assertEqual(result["container_column"], "sea_container")
        self.assertEqual(len(result["results"]), 9)

    def test_duplicate_real_id_blocks(self):
        path = self._make_real_db(duplicate=True)
        result = discover.crm_readonly_summary(path)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "DUPLICATE_IDS")

    def test_symlink_database_blocks(self):
        real_path = self._make_real_db()
        link_path = os.path.join(self.tmp, "linked.db")
        os.symlink(real_path, link_path)
        result = discover.crm_readonly_summary(link_path)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SYMLINK", result["reason"])

    def test_hardlinked_database_blocks(self):
        real_path = self._make_real_db()
        link_path = os.path.join(self.tmp, "hard.db")
        os.link(real_path, link_path)
        result = discover.crm_readonly_summary(real_path)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("HARDLINK", result["reason"])

    def test_fixed_production_root_not_environment_selected(self):
        self.assertEqual(discover.BASE_DIR, "/home/Carix")

    def test_strict_json_recursive_secret_redaction(self):
        serialized = discover.serialize_receipt(
            {"status": "OK", "nested": {"token": "abc123", "note": "password=hunter2"}}
        )
        parsed = json.loads(serialized)
        self.assertEqual(parsed["nested"]["token"], "[REDACTED]")
        self.assertNotIn("hunter2", serialized)
        self.assertFalse(discover.scan_for_secrets(serialized))

    def test_full_fixed_registry_discovery_ok(self):
        self._make_full_root(ferry=True)
        receipt = discover.run_discovery(self.tmp)
        self.assertEqual(receipt["status"], "OK", receipt)
        self.assertEqual(receipt["crm"]["status"], "OK")
        self.assertEqual(receipt["total_source_occurrences"], 13)
        self.assertNotIn("_raw_bytes", json.dumps(receipt, ensure_ascii=False))

    def test_missing_required_card_blocks(self):
        self._make_full_root(ferry=True)
        os.remove(os.path.join(self.tmp, "video", "UA-0009.html"))
        receipt = discover.run_discovery(self.tmp)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("MISSING_CORE_PAGES", receipt["reasons"])

    def test_ambiguous_required_card_blocks(self):
        self._make_full_root(ferry=True)
        path = os.path.join(self.tmp, "video", "UA-0009.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<html><body><span>Море</span></body></html>")
        receipt = discover.run_discovery(self.tmp)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("AMBIGUOUS_TARGET", receipt["reasons"])

    def test_zero_occurrence_blocks(self):
        self._make_full_root(ferry=False)
        receipt = discover.run_discovery(self.tmp)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ZERO_OCCURRENCES", receipt["reasons"])

    def test_optional_site_candidates_may_be_missing(self):
        self._make_full_root(ferry=True)
        receipt = discover.run_discovery(self.tmp)
        self.assertEqual(receipt["status"], "OK", receipt)
        self.assertEqual(receipt["html"]["site/index.html"]["status"], "MISSING")


class TestCompiles(unittest.TestCase):
    def test_module_compiles(self):
        import py_compile
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        py_compile.compile(os.path.join(here, "discover.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
