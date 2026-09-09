import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import copy
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "current_state_audit.py"
spec = importlib.util.spec_from_file_location("current_audit_fixture", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
VIN = "KNAGU416BKA324445"
HTML = """<html><head><title>Hidden VIN KNAGU416BKA324445</title></head><body>
<h1>Kia K5 2018</h1><div class="cena">11 700 $</div>
<table><tr><td>VIN</td><td>KNAGU416BKA324445</td></tr></table>
<div hidden>KNAGU416BKA324445</div><script>const vin='KNAGU416BKA324445';</script>
<a href="UA-0010-diag.html">Диагностика</a></body></html>"""


class CurrentAuditTests(unittest.TestCase):
    def fixture(self, root):
        with sqlite3.connect(root / "crm.db") as conn:
            conn.execute("CREATE TABLE cars (id INTEGER,auto_number TEXT,vin TEXT,brand TEXT,model TEXT,year TEXT,published INTEGER,price_uah INTEGER,photos TEXT)")
            conn.execute("INSERT INTO cars VALUES (10,'UA-0010',?,'Kia','K5','2018',1,11700,'photo')", (VIN,))
            conn.execute("INSERT INTO cars VALUES (17,'UA-0017','WAUZZZ4G9FN009684','Audi','A6','2015',0,23000,NULL)")
        for folder in ("video", "site"):
            (root / folder).mkdir()
            (root / folder / "UA-0010.html").write_text(HTML)
            (root / folder / "UA-0010-diag.html").write_text("<html>diagnosis</html>")
            (root / folder / "katalog.html").write_text('<a href="UA-0010.html">open</a><script>"UA-0017.html"</script>')
        (root / "cars_schema.py").write_text("FIELDS=[('photos','Фото','media',True,'list',''),('published','Публикация','service',True,'bool','')]\n" + audit.REQUIRED_RULE)

    def test_comparisons_redaction_and_draft_completeness_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = audit.audit(root)
            self.assertEqual(result["crm_rows"], 2)
            self.assertEqual(result["published_rows"], 1)
            card, draft = result["cards"]
            for page in card["roots"].values():
                self.assertEqual(page["year"]["comparison"], "MATCH")
                self.assertEqual(page["vin"]["expected_visible_count"], 1)
                self.assertEqual(page["price"]["numeric_comparison"], "MATCH")
                self.assertEqual(page["price"]["currency_comparison"], "UNVERIFIED")
                self.assertTrue(page["diagnostic_link_present"])
                self.assertTrue(page["linked_in_catalog"])
            self.assertFalse(draft["roots"]["video"]["linked_in_catalog"])
            self.assertFalse(draft["roots"]["video"]["page_present"])
            self.assertEqual(draft["required_check"]["missing"], [{"field": "photos", "label": "Фото"}])
            self.assertNotIn(VIN, json.dumps(result))
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_missing_or_changed_required_schema_is_unverified(self):
        self.assertIsNone(audit.required_rule(None))
        self.assertIsNone(audit.required_rule("FIELDS=[]\ndef missing_required(car): return ['everything']"))

    def test_unparseable_identity_price_remain_unverified(self):
        car = {"auto_number": "UA-0010", "vin": VIN, "brand": "Kia", "model": "K5", "year": "2018", "price_uah": 11700}
        page = audit.parse_page("<h1>Available car</h1><div class='cena'>Call for price</div>", car, {"Kia"})
        self.assertEqual(page["year"]["comparison"], "UNVERIFIED")
        self.assertEqual(page["brand"]["comparison"], "UNVERIFIED")
        self.assertEqual(page["price"]["numeric_comparison"], "UNVERIFIED")

    def test_duplicate_visible_vin_detected_but_hidden_script_excluded(self):
        car = {"auto_number": "UA-0010", "vin": VIN}
        page = audit.parse_page(HTML.replace("</body>", "<div>" + VIN + "</div></body>"), car, {"Kia"})
        self.assertEqual(page["vin"]["expected_visible_count"], 2)
        self.assertFalse(page["vin"]["one_expected_visible_vin"])

    def test_external_links_are_not_local_page_proof(self):
        self.assertIsNone(audit.local_link_name("https://example.com/UA-0010.html"))
        self.assertEqual(audit.local_link_name("https://www.uaart.com.ua/video/UA-0010.html?v=1"), "UA-0010.html")

    def test_symlinks_and_nonempty_wal_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "crm.db-wal").write_bytes(b"active WAL")
            with self.assertRaisesRegex(audit.AuditError, "STABLE_SNAPSHOT"):
                audit.audit(root)
            (root / "crm.db-wal").unlink()
            (root / "video/UA-0010.html").unlink()
            (root / "video/UA-0010.html").symlink_to(root / "site/UA-0010.html")
            with self.assertRaisesRegex(audit.AuditError, "SYMLINK_REFUSED"):
                audit.audit(root)

    def test_change_or_disappearance_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "page.html"
            p.write_text("before")
            reads = audit.Reads(root)
            reads.read(p)
            p.unlink()
            with self.assertRaisesRegex(audit.AuditError, "INPUT_CHANGED"):
                reads.verify()

    def test_selected_row_change_rejected_even_with_read_only_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            actual = audit.selected_crm
            calls = 0
            def changing(reads):
                nonlocal calls
                fields, rows = actual(reads)
                calls += 1
                if calls > 1:
                    rows = list(rows)
                    row = list(rows[0]); row[fields.index("year")] = "2020"; rows[0] = tuple(row)
                return fields, rows
            with patch.object(audit, "selected_crm", side_effect=changing):
                with self.assertRaisesRegex(audit.AuditError, "ROWS_CHANGED"):
                    audit.audit(root)

    def test_output_must_be_new_file_in_exact_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("sys.argv", ["audit", "--root", str(root), "--output", str(root / "bad.json")]):
                with self.assertRaisesRegex(audit.AuditError, "OUTPUT_MUST"):
                    audit.main()
            self.fixture(root)
            stage = root / audit.STAGE_NAME; stage.mkdir()
            output = stage / "report.json"
            with patch("sys.argv", ["audit", "--root", str(root), "--output", str(output)]):
                audit.main()
                with self.assertRaisesRegex(audit.AuditError, "OUTPUT_MUST"):
                    audit.main()
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_dotdot_cannot_escape_stage_or_read_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()
            stage = root / audit.STAGE_NAME
            stage.mkdir()
            output = stage / ".." / "escaped.json"
            with patch("sys.argv", ["audit", "--root", str(root), "--output", str(output)]):
                with self.assertRaisesRegex(audit.AuditError, "OUTPUT_MUST"):
                    audit.main()
            self.assertFalse((root / "escaped.json").exists())
            with self.assertRaisesRegex(audit.AuditError, "PATH_OUTSIDE_ROOT"):
                audit.Reads(root).safe(stage / ".." / ".." / "outside.db")

    def test_compact_terminal_handoff_is_sanitized_and_under_35_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            report = audit.audit(root)
            report["cards"] = [copy.deepcopy(report["cards"][0]) for _ in range(16)] + [copy.deepcopy(report["cards"][1]) for _ in range(2)]
            for index, card in enumerate(report["cards"], 1):
                card["uid"] = f"UA-{index:04d}"
            lines = audit.compact_lines(report)
            self.assertLessEqual(len(lines), 35)
            self.assertNotIn(VIN, "\n".join(lines))
            self.assertIn("reqPH", "\n".join(lines))
            self.assertIn("completed_at_utc", report)
            self.assertEqual(sum(line.startswith("UA-") for line in lines), 18)


if __name__ == "__main__":
    unittest.main()
