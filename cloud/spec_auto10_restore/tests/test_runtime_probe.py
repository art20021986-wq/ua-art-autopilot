"""Probe guarantees: read-only observation, explicit limits, and narrow export."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


_SPEC = importlib.util.spec_from_file_location(
    "spec_restore_runtime_probe", Path(__file__).resolve().parents[1] / "runtime_probe.py"
)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)


class RuntimeProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "runtime"
        self.root.mkdir()

    def database(self, name="crm.db"):
        path = self.root / name
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE cars(auto_number TEXT, vin TEXT, published INTEGER,
                                  brand TEXT, model TEXT, year INTEGER, fuel TEXT,
                                  price INTEGER, client_phone TEXT, bot_token TEXT);
                INSERT INTO cars VALUES('UA-0001','KMHE341DBKA544289',1,'Hyundai','Sonata',2019,
                    'LPG',12345,'+380501234567','UNIQUE_PRIVATE_BOT_TOKEN');
                CREATE TABLE additional_specification(car_uid TEXT, field_key TEXT,
                    field_value TEXT, normalized_value TEXT, source TEXT, source_url TEXT,
                    confidence REAL, is_price_field INTEGER, created_at TEXT);
                INSERT INTO additional_specification VALUES('UA-0001','wheelbase_mm','2805',
                    '2805','CURATED','https://example.com?token=UNIQUE_SOURCE_SECRET',1,0,'2026-09-09');
                CREATE TABLE additional_specification_meta(car_uid TEXT, field_key TEXT,
                    label_ru TEXT, category TEXT, unit TEXT, evidence_count INTEGER,
                    source_domains_json TEXT, source_urls_json TEXT, verification_status TEXT,
                    model_match_score REAL, is_manual INTEGER, is_visible INTEGER, updated_at TEXT);
                INSERT INTO additional_specification_meta VALUES('UA-0001','wheelbase_mm',
                    'Колёсная база','dimensions','мм',2,'["auto-data.net","evil.example"]',
                    '["https://example.com/SECRET_URL"]','MANUAL',1,1,1,'2026-09-09');
                CREATE TABLE vin_spec_jobs(car_uid TEXT, vin TEXT, status TEXT,
                    attempts INTEGER, facts_count INTEGER, site_sync_status TEXT, last_error TEXT);
                INSERT INTO vin_spec_jobs VALUES('UA-0001','KMHE341DBKA544289','READY',1,1,
                    'FAIL','PRIVATE_ERROR_WITH_CONTACT');
                CREATE TABLE contacts(secret TEXT);
                INSERT INTO contacts VALUES('DO_NOT_EXPORT_CONTACTS_TABLE');
            """)
        return path

    def test_exports_only_allowed_data_and_keeps_manual_metadata(self):
        path = self.database()
        record = probe.probe_database(path)
        self.assertEqual(record["status"], "READ_OBSERVATION_NOT_ATOMIC_SNAPSHOT")
        self.assertTrue(record["query_only"])
        self.assertEqual(record["database_changes"], 0)
        self.assertFalse(record["consistent_snapshot"])
        self.assertEqual(record["cards"][0]["vin_sha256"], hashlib.sha256(b"KMHE341DBKA544289").hexdigest())
        self.assertEqual(record["cards"][0]["model"], "Sonata")
        self.assertEqual(record["cards"][0]["year"], "2019")
        self.assertTrue(record["cards"][0]["published"])
        self.assertEqual(record["facts"][0]["field_value"], "2805")
        self.assertTrue(record["metadata"][0]["is_manual"])
        self.assertEqual(record["metadata"][0]["source_domains"], ["auto-data.net"])
        self.assertEqual(record["jobs"][0]["site_sync_status"], "FAIL")
        exported = json.dumps(record)
        for private in ["KMHE341DBKA544289", "+380501234567", "UNIQUE_PRIVATE_BOT_TOKEN",
                        "UNIQUE_SOURCE_SECRET", "SECRET_URL", "PRIVATE_ERROR_WITH_CONTACT",
                        "DO_NOT_EXPORT_CONTACTS_TABLE", '"price"', '"client_phone"', '"bot_token"']:
            self.assertNotIn(private, exported)

    def test_snapshot_does_not_modify_files_or_create_sqlite_sidecars(self):
        self.database()
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        report = probe.build_report(self.root)
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(report["runtime_verified"])
        self.assertFalse(report["consistent_snapshot"])

    def test_application_modules_are_parsed_never_imported(self):
        marker = self.base / "MUST_NOT_EXIST"
        (self.root / "cars_ui.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\nimport vin_spec_service\n",
            encoding="utf-8",
        )
        (self.root / "vin_spec_service.py").write_text(
            "import source_policy\nraise RuntimeError('worker must not start')\n", encoding="utf-8"
        )
        report = probe.build_report(self.root)
        self.assertFalse(marker.exists())
        module = next(m for m in report["modules"] if Path(m["path"]).name == "cars_ui.py")
        self.assertEqual(module["relevant_static_imports"], ["vin_spec_service"])
        self.assertEqual(module["binding_evidence"], "STATIC_CANDIDATE_ONLY_NOT_PROCESS_BOUND")

    def test_active_wal_is_not_ignored_or_modified(self):
        path = self.database()
        wal = Path(str(path) + "-wal")
        wal.write_bytes(b"pending WAL frames")
        record = probe.probe_database(path)
        self.assertEqual(record["status"], "JOURNAL_PRESENT_OR_INACCESSIBLE_READ_SKIPPED")
        self.assertNotIn("facts", record)
        self.assertEqual(wal.read_bytes(), b"pending WAL frames")
        self.assertFalse(Path(str(path) + "-shm").exists())

    def test_active_rollback_journal_is_not_read(self):
        path = self.database()
        Path(str(path) + "-journal").write_bytes(b"rollback")
        self.assertEqual(probe.probe_database(path)["status"], "JOURNAL_PRESENT_OR_INACCESSIBLE_READ_SKIPPED")

    def test_distinguishes_missing_and_invalid_databases(self):
        self.assertEqual(probe.probe_database(self.root / "crm.db")["status"], "MISSING")
        path = self.root / "crm.db"
        path.write_bytes(b"not a database PRIVATE_SECRET")
        record = probe.probe_database(path)
        self.assertEqual(record["status"], "READ_FAILED")
        self.assertEqual(record["reason"], "DatabaseError")
        self.assertNotIn("PRIVATE_SECRET", json.dumps(record))

    def test_same_inode_aliases_are_explicit(self):
        path = self.database()
        alias = self.root / "vin_specs.db"
        alias.hardlink_to(path)
        report = probe.build_report(self.root)
        record = next(d for d in report["databases"] if d["path"] == str(alias))
        self.assertEqual(record["status"], "SAME_FILE_ALIAS")
        self.assertEqual(record["same_file_as"], str(path))

    def test_explicit_spec_db_outside_root_is_inspected_readonly(self):
        explicit = self.base / "separate-spec.db"
        with sqlite3.connect(explicit) as conn:
            conn.execute("CREATE TABLE unrelated(x)")
        report = probe.build_report(self.root, (explicit,))
        record = next(d for d in report["databases"] if d["path"] == str(explicit))
        self.assertEqual(record["status"], "READ_OBSERVATION_NOT_ATOMIC_SNAPSHOT")
        self.assertEqual(record["schema"]["cars"]["status"], "MISSING")

    def test_database_conflicts_are_reported_without_choosing_or_merging(self):
        self.database()
        sidecar = self.database("vin_specs_task111_v3.db")
        with sqlite3.connect(sidecar) as conn:
            conn.execute("UPDATE additional_specification SET field_value='2900'")
        report = probe.build_report(self.root)
        comparison = report["database_comparison"][0]
        self.assertEqual(comparison["car_uid"], "UA-0001")
        self.assertEqual(len(comparison["observations"]), 2)
        self.assertEqual(comparison["conflicting_field_keys"], ["wheelbase_mm"])
        self.assertFalse(comparison["canonical_database_determined"])

    def test_public_html_inventory_counts_without_exporting_html(self):
        directory = self.root / "video"
        directory.mkdir()
        (directory / "UA-0001.html").write_text(
            '<html><script>const SECRET_HTML="do not export"</script>'
            '<details class="blok ua-additional-spec" data-ua-additional-spec="1">'
            '<div class="ua-addspec-row"></div></details></html>', encoding="utf-8"
        )
        report = probe.build_report(self.root)
        self.assertEqual(report["public_page_count"], 1)
        self.assertEqual(report["public_pages"][0]["specification_blocks"], 1)
        self.assertEqual(report["public_pages"][0]["specification_rows"], 1)
        self.assertNotIn("SECRET_HTML", json.dumps(report))

    def test_sensitive_or_primary_facts_are_omitted(self):
        for key, value in [("price", "10000"), ("contact_phone", "+380501234567"),
                           ("vin", "KMHE341DBKA544289"), ("seat_type", "<script>attack()</script>"),
                           ("trim", "owner@example.com"), ("trim", "github_pat_PRIVATE_TOKEN")]:
            with self.subTest(key=key, value=value):
                self.assertIsNone(probe._fact_or_meta({"car_uid": "UA-0001", "field_key": key, "field_value": value}, False))

    def test_changed_database_export_is_discarded(self):
        path = self.database()
        original_metadata = probe._metadata
        calls = 0
        def changed_metadata(candidate):
            nonlocal calls
            result = original_metadata(candidate)
            if candidate == path:
                calls += 1
                if calls == 2:
                    result["sha256"] = "changed"
            return result
        with patch.object(probe, "_metadata", side_effect=changed_metadata):
            record = probe.probe_database(path)
        self.assertEqual(record["status"], "CHANGED_DURING_READ_EXPORT_DISCARDED")
        self.assertNotIn("facts", record)
        self.assertNotIn("cards", record)

    def test_output_must_be_outside_root_including_symlink_parent(self):
        symlink = self.base / "alias"
        symlink.symlink_to(self.root, target_is_directory=True)
        for output in (self.root / "report.json", symlink / "report.json"):
            with self.subTest(output=output), self.assertRaises(SystemExit):
                probe.main(["--root", str(self.root), "--output", str(output)])
            self.assertFalse(output.exists())

    def test_cli_writes_private_report_and_refuses_overwrite(self):
        self.database()
        output = self.base / "report.json"
        self.assertEqual(probe.main(["--root", str(self.root), "--output", str(output)]), 0)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertTrue(json.loads(output.read_text())["read_only"])
        before = output.read_bytes()
        with self.assertRaises(SystemExit):
            probe.main(["--root", str(self.root), "--output", str(output)])
        self.assertEqual(before, output.read_bytes())

    def test_unknown_fields_are_never_selected_and_column_names_are_quoted(self):
        path = self.root / "crm.db"
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE cars("AUTO_NUMBER" TEXT, "VIN" TEXT, "published" TEXT, "secret""column" TEXT)')
            conn.execute('INSERT INTO cars VALUES (?,?,?,?)', ("UA-0002", "ABC", "unexpected", "SECRET_UNRECOGNIZED_COLUMN"))
        record = probe.probe_database(path)
        self.assertEqual(record["cards"][0]["car_uid"], "UA-0002")
        self.assertIsNone(record["cards"][0]["published"])
        self.assertEqual(record["schema"]["cars"]["column_count"], 4)
        self.assertNotIn("SECRET_UNRECOGNIZED_COLUMN", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
