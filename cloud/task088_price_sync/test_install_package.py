"""Installer safety tests use TEST evidence and isolated temporary roots only."""
from datetime import datetime, timezone
import hashlib
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import install_package as I
import outbox


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="task088-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc).timestamp()
        self.at, self.expires = "2026-09-13T16:00:00Z", "2026-09-13T16:10:00Z"
        self.task = "TASK088-GE-PRICE-SITE-STAGE3-TEST-001"
        self.tx = "tx-stage3-test-001"
        self.db = sqlite3.connect(self.root / "crm.db")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,
                status TEXT,price_uah INTEGER,price_georgia INTEGER,title TEXT);
            INSERT INTO cars VALUES(7,'UA-0001',1,'ge_waiting',10000,8000,'Keep');
            INSERT INTO cars VALUES(8,'UA-0002',1,'ua_arrived',12000,NULL,'Keep2');
            CREATE TABLE audit(field TEXT,old_value TEXT,new_value TEXT);
            INSERT INTO audit VALUES('title','Before','Keep');
        """)
        self.snapshot = I.database_snapshot(self.db)
        self.schema_hash = I.sha(I.encoded(self.db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()))
        self.files = {}
        self.before = {}
        html = {f"{folder}/{code}.html" for folder in ("video", "site") for code in ("UA-0001", "UA-0002")}
        html |= {"video/katalog.html", "site/katalog.html", "video/index.html", "site/index.html"}
        for name in I.SOURCES | html:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            original = (("# original " if name.endswith(".py") else "original ") + name).encode()
            path.write_bytes(original)
            self.before[name] = I.sha(original)
            self.files[name] = (("# candidate " if name.endswith(".py") else "candidate ") + name).encode()
        for name in I.MODULES:
            self.files[name] = ("# candidate " + name).encode()
            self.before[name] = None
        self.dependencies = {}
        for name in I.DEPENDENCIES:
            content = ("# unchanged " + name).encode()
            (self.root / name).write_bytes(content)
            self.dependencies[name] = I.sha(content)
        # Unrelated source, photo and specification must be included in the full backup.
        (self.root / "other_live.py").write_bytes(b"# unrelated source\n")
        (self.root / "video/photo.jpg").write_bytes(b"untouched photo bytes")
        (self.root / "site/specification.html").write_bytes(b"untouched specification")
        self.bind()

    def bind(self, preview_overrides=None):
        manifest = I.candidate_manifest(self.files, self.before)
        payload_hash = I.sha(I.encoded(manifest))
        approved = I.encoded({"task_id": self.task, "install_files_sha256": payload_hash})
        writers = I.encoded({"task_id": self.task, "install_files_sha256": payload_hash,
            "publication_lock": str(self.root / ".ua_art_publish_transaction.lock"), "observed_at": self.at,
            "writers": [{"name": "TEST writer only", "fence": "VERIFIED"}], "uncovered_writers": []})
        inventory = I.system_inventory(self.root)
        schema_test = sqlite3.connect(":memory:")
        self.db.backup(schema_test)
        schema_test.execute("BEGIN IMMEDIATE")
        outbox.install(schema_test)
        candidate_schema = I.sha(I.encoded(schema_test.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()))
        schema_test.close()
        preview = I.encoded({"contract": "TASK088-FINAL-V5-PREVIEW-GATE-1", "task_id": self.task,
            "status": "PASS", "candidate_manifest_sha256": payload_hash,
            "database": self.snapshot, "schema_sha256": self.schema_hash,
            "system_inventory_sha256": I.sha(I.encoded(inventory)),
            "published_codes": self.snapshot["published_codes"], "evaluated_at": self.at,
            "checks": {name: "PASS" for name in I.PREVIEW_CHECKS}})
        if preview_overrides:
            altered = json.loads(preview)
            altered.update(preview_overrides)
            preview = I.encoded(altered)
        gate = I.encoded({"task_id": self.task, "manifest_sha256": I.sha(approved), "status": "PASS",
            "tests": "PASS", "unexpected_changes": 0, "backup_plan_ready": True,
            "preview_gate_sha256": I.sha(preview),
            "rollback_plan_ready": True, "writer_fence_report_sha256": I.sha(writers), "evaluated_at": self.at})
        request = {"task_id": self.task, "requested_min_class": "CRITICAL", "production_required": True,
            "critical": {"manifest_sha256": I.sha(approved), "gate_a_sha256": I.sha(gate),
                         "owner_approval_sha256": "0" * 64}}
        subject_hash = I.sha((json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
        owner = I.encoded({"schema_version": "UA-ART-PRODUCTION-AUTHORIZATION-1", "task_id": self.task,
            "owner": "Артём Бровинский / UA ART COMPANY LLC", "owner_authorized": True,
            "production_allowed": True, "authorized_environment": "production", "mode_epoch": "test-epoch",
            "manifest_sha256": I.sha(approved), "gate_a_sha256": I.sha(gate),
            "request_subject_sha256": subject_hash, "expires_at": self.expires,
            "authorization_id": "prod-auth-fixture-test-only-001"})
        request["critical"]["owner_approval_sha256"] = I.sha(owner)
        request_bytes = I.encoded(request)
        request_hash = I.sha(request_bytes)
        self.evidence = {"request": request_bytes, "manifest": approved, "gate_b": gate,
            "owner_approval": owner, "writers": writers, "preview_gate": preview,
            "claim": I.encoded({"identity": {"task_id": self.task, "task_sha256": request_hash, "run_id": "12345"},
                "task_execution_status": "RUNNING", "production_transaction_status": "OPEN",
                "production_transaction_id": self.tx, "mode_epoch": "test-epoch"}),
            "transaction": I.encoded({"task_id": self.task, "request_sha256": request_hash,
                "status": "OPEN", "transaction_id": self.tx, "run_id": "12345", "expires_at": self.expires,
                "mode_epoch": "test-epoch"}),
            "stage2": I.encoded({"task_id": "TASK088-GE-PRICE-CRM-STAGE2", "status": "FINISHED",
                "stage2_status": "PASS", "stage3_allowed": True, "stage1_prerequisite": "PASS", "independent_price_fields": "PASS",
                "original_values_restored": True, "installed_source_sha256": self.before["cars_ui.py"]}),
            "quota": I.encoded({"source": "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT", "account": "Carix",
                "observed_at": self.at, "used_bytes": 1000000, "limit_bytes": 1000000000})}
        self.plan = {"contract": I.CONTRACT, "environment": "TEST", "root": str(self.root),
            "task_id": self.task, "transaction_id": self.tx, "observed_at": self.at,
            "files": manifest, "manifest_sha256": payload_hash,
            "database": self.snapshot, "schema_sha256": self.schema_hash, "published_count": len(self.snapshot["published_codes"]),
            "candidate_schema_sha256": candidate_schema, "system_inventory": inventory,
            "runtime_journal_relative": ".uaart_price_sync_journal",
            "dependencies_sha256": self.dependencies,
            "evidence_sha256": {name: I.sha(content) for name, content in self.evidence.items()}}
        self.plan_hash = I.sha(I.encoded(self.plan))

    def call(self, **kwargs):
        return I.install(self.plan, self.files, self.evidence, expected_plan_sha256=self.plan_hash,
                         schema_installer=kwargs.pop("schema_installer", outbox.install), test_root=self.root,
                         now=self.now, **kwargs)

    def assert_no_candidate_files(self):
        for name, before in self.before.items():
            path = self.root / name
            if before is None:
                self.assertFalse(path.exists(), name)
            else:
                self.assertEqual(I.sha(path.read_bytes()), before, name)

    def assert_original_database(self):
        self.assertEqual(I.database_snapshot(self.db), self.snapshot)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name=?", (outbox.TABLE,)).fetchone())

    def test_success_has_verified_online_backup_and_preserves_crm(self):
        result = self.call()
        self.assertEqual(result["status"], "INSTALLED_PENDING_LIVE_ACCEPTANCE")
        self.assertFalse(result["bot_restarted"])
        self.assertEqual(result["live_public_acceptance"], "NOT_RUN")
        self.assertTrue((self.root / ".uaart_price_sync_journal").is_dir())
        self.assertEqual(I.database_snapshot(self.db), self.snapshot)
        self.assertEqual(result["independent_db_readback"], "PASS")
        for name, content in self.files.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        journal = pathlib.Path(result["journal"])
        backup = journal.parent / "crm.sqlite"
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        for name in ("video/photo.jpg", "site/specification.html", "other_live.py"):
            self.assertEqual((journal.parent / "full" / name).read_bytes(), (self.root / name).read_bytes())
        with backup.open("rb") as handle:
            self.assertEqual(hashlib.file_digest(handle, "sha256").hexdigest(), result["backup_database_sha256"])
        conn = sqlite3.connect(backup)
        try:
            self.assertEqual(I.database_snapshot(conn), self.snapshot)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name=?", (outbox.TABLE,)).fetchone())
        finally:
            conn.close()

    def test_manifest_mutation_rejected_before_target_writes(self):
        self.plan["published_count"] = 999
        with self.assertRaisesRegex(I.InstallError, "IMMUTABLE_PLAN"):
            self.call()
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_arbitrary_gate_boolean_is_not_accepted(self):
        self.evidence["gate_b"] = b'{"gate_b":true}'
        with self.assertRaisesRegex(I.InstallError, "EVIDENCE_HASH"):
            self.call()
        self.assert_no_candidate_files()

    def test_stale_or_cross_task_evidence_rejected(self):
        self.now += 1900
        with self.assertRaisesRegex(I.InstallError, "FRESH_OBSERVATION"):
            self.call()
        self.assert_no_candidate_files()

    def test_source_drift_is_not_overwritten(self):
        path = self.root / "cars_ui.py"
        path.write_bytes(b"another live change")
        with self.assertRaisesRegex(I.InstallError, "INVENTORY_DRIFT|PREIMAGE_DRIFT"):
            self.call()
        self.assertEqual(path.read_bytes(), b"another live change")
        self.assert_original_database()

    def test_existing_transaction_backup_evidence_is_never_overwritten(self):
        backup = self.root / "rezerv_publikacii/TASK088_STAGE3" / self.tx
        backup.mkdir(parents=True)
        original = b'{"status":"FINISHED","historical_evidence":"preserve"}'
        (backup / "result.json").write_bytes(original)
        with self.assertRaises(FileExistsError):
            self.call()
        self.assertEqual((backup / "result.json").read_bytes(), original)
        self.assertEqual(list(backup.iterdir()), [backup / "result.json"])
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_crm_price_drift_stops_before_schema_or_html_write(self):
        self.db.execute("UPDATE cars SET price_georgia=9000 WHERE id=7")
        self.db.commit()
        with self.assertRaisesRegex(I.InstallError, "CRM_SNAPSHOT_DRIFT"):
            self.call()
        self.assert_no_candidate_files()
        self.assertEqual(self.db.execute("SELECT price_georgia FROM cars WHERE id=7").fetchone()[0], 9000)

    def test_unexpected_dependency_drift_blocks_install(self):
        (self.root / "master_card.py").write_bytes(b"unreviewed writer")
        with self.assertRaisesRegex(I.InstallError, "DEPENDENCY_HASH"):
            self.call()
        self.assert_no_candidate_files()

    def test_stage_process_source_is_pinned_and_not_overwritten_after_drift(self):
        path = self.root / "ua_stage_catalog_sync.py"
        self.assertIn(path.name, I.SOURCES)
        path.write_bytes(b"unreviewed stage writer")
        with self.assertRaisesRegex(I.InstallError, "INVENTORY_DRIFT|PREIMAGE_DRIFT"):
            self.call()
        self.assertEqual(path.read_bytes(), b"unreviewed stage writer")
        self.assert_original_database()

    def test_missing_binding_bootstrap_blocks_install(self):
        self.files.pop("uaart_price_sync_binding.py")
        self.before.pop("uaart_price_sync_binding.py")
        self.bind()
        with self.assertRaisesRegex(I.InstallError, "INSTALL_FILE_SET"):
            self.call()
        self.assert_no_candidate_files()

    def test_missing_control_reader_blocks_even_rebound_candidate_manifest(self):
        self.files.pop("uaart_price_control_reader.py")
        self.before.pop("uaart_price_control_reader.py")
        self.bind()
        with self.assertRaisesRegex(I.InstallError, "INSTALL_FILE_SET"):
            self.call()
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_invalid_candidate_syntax_cannot_replace_working_crm(self):
        self.files["cars_ui.py"] = b"def broken(:\n"
        self.bind()
        with self.assertRaisesRegex(I.InstallError, "PYTHON_SYNTAX"):
            self.call()
        self.assert_no_candidate_files()

    def test_low_quota_blocks_even_when_os_disk_has_space(self):
        quota = json.loads(self.evidence["quota"])
        quota["limit_bytes"] = 1100000
        self.evidence["quota"] = I.encoded(quota)
        self.plan["evidence_sha256"]["quota"] = I.sha(self.evidence["quota"])
        self.plan_hash = I.sha(I.encoded(self.plan))
        with self.assertRaisesRegex(I.InstallError, "QUOTA_INSUFFICIENT"):
            self.call()
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_install_failure_restores_exact_files_and_rolls_back_schema(self):
        original = I._atomic
        def fail_source(path, content, mode=0o600):
            if path == self.root / "owner_policy.py" and content == self.files["owner_policy.py"]:
                raise OSError("simulated write failure")
            return original(path, content, mode)
        with patch.object(I, "_atomic", side_effect=fail_source):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.call()
        self.assert_no_candidate_files()
        self.assert_original_database()
        status = json.loads((self.root / "rezerv_publikacii/TASK088_STAGE3" / self.tx / "result.json").read_bytes())
        self.assertEqual(status["status"], "ROLLED_BACK")
        self.assertFalse((self.root / ".uaart_price_sync_journal").exists())

    def test_rollback_preserves_foreign_write_and_reports_conflict(self):
        original = I._atomic
        conflict = self.root / "catalog_design_guard.py"
        def collide(path, content, mode=0o600):
            if path == self.root / "owner_policy.py" and content == self.files["owner_policy.py"]:
                conflict.write_bytes(b"foreign writer version")
                raise OSError("concurrent external writer")
            return original(path, content, mode)
        with patch.object(I, "_atomic", side_effect=collide):
            with self.assertRaisesRegex(I.InstallError, "ROLLBACK_FOREIGN_WRITE_CONFLICT"):
                self.call()
        self.assertEqual(conflict.read_bytes(), b"foreign writer version")
        self.assert_original_database()

    def test_bad_schema_installer_cannot_mutate_existing_rows(self):
        def wrong(conn):
            outbox.install(conn)
            conn.execute("UPDATE cars SET title='unexpected'")
        with self.assertRaisesRegex(I.InstallError, "SCHEMA_INSTALLER_CHANGED_CRM"):
            self.call(schema_installer=wrong)
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_symlink_target_cannot_escape_root(self):
        path = self.root / "cars_ui.py"
        outside = self.root.parent / (self.root.name + "-outside")
        outside.write_bytes(b"outside")
        self.addCleanup(outside.unlink)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(I.InstallError, "SYMLINK"):
            self.call()
        self.assertEqual(outside.read_bytes(), b"outside")


    def test_rebound_generic_gate_pass_cannot_hide_missing_preview_check(self):
        checks = {name: "PASS" for name in I.PREVIEW_CHECKS}
        checks["mobile"] = "FAIL"
        self.bind(preview_overrides={"checks": checks})
        with self.assertRaisesRegex(I.InstallError, "FULL_BOUND_PREVIEW_GATE_REQUIRED"):
            self.call()
        self.assert_no_candidate_files()

    def test_missing_homepage_is_not_an_approved_full_scope(self):
        self.files.pop("video/index.html")
        self.before.pop("video/index.html")
        self.bind()
        with self.assertRaisesRegex(I.InstallError, "INSTALL_FILE_SET"):
            self.call()
        self.assert_no_candidate_files()

    def test_new_car_uses_current_published_set_instead_of_fixed_eighteen(self):
        self.db.execute("INSERT INTO cars VALUES(9,'UA-0003',1,'kr_ready',13000,NULL,'Keep3')")
        self.db.commit()
        self.snapshot = I.database_snapshot(self.db)
        for folder in ("video", "site"):
            name = folder + "/UA-0003.html"
            (self.root / name).write_bytes(b"original new card")
            self.before[name] = I.sha(b"original new card")
            self.files[name] = b"candidate new card"
        self.bind()
        self.assertEqual(self.call()["status"], "INSTALLED_PENDING_LIVE_ACCEPTANCE")

    def test_protected_photo_drift_blocks_without_overwriting_it(self):
        (self.root / "video/photo.jpg").write_bytes(b"new operator photograph")
        with self.assertRaisesRegex(I.InstallError, "FULL_SYSTEM_INVENTORY_DRIFT"):
            self.call()
        self.assertEqual((self.root / "video/photo.jpg").read_bytes(), b"new operator photograph")
        self.assert_no_candidate_files()

    def test_schema_candidate_must_match_exact_private_preflight(self):
        self.plan["candidate_schema_sha256"] = "1" * 64
        self.plan_hash = I.sha(I.encoded(self.plan))
        with self.assertRaisesRegex(I.InstallError, "CANDIDATE_SCHEMA_HASH_MISMATCH"):
            self.call()
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_new_unknown_schema_is_not_approved_by_generic_gate_pass(self):
        def unauthorized(conn):
            outbox.install(conn)
            conn.execute("CREATE TABLE unrelated_secret_table(value TEXT)")
        with self.assertRaisesRegex(I.InstallError, "UNAPPROVED_SCHEMA_OBJECT"):
            self.call(schema_installer=unauthorized)
        self.assert_no_candidate_files()
        self.assert_original_database()

    def test_symlink_nested_public_asset_is_rejected_before_backup(self):
        (self.root / "video/untrusted").symlink_to(self.root / "site", target_is_directory=True)
        with self.assertRaisesRegex(I.InstallError, "SYMLINK"):
            self.call()
        self.assert_no_candidate_files()

    def test_full_inventory_streams_assets_larger_than_source_size_limit(self):
        target = self.root / "video/large-media.bin"
        with target.open("wb") as handle:
            handle.seek(I.MAX_FILE + 1)
            handle.write(b"x")
        self.bind()
        result = self.call()
        copied = pathlib.Path(result["journal"]).parent / "full/video/large-media.bin"
        self.assertEqual(copied.stat().st_size, I.MAX_FILE + 2)
        self.assertEqual(I._stream_entry(copied)["sha256"], I._stream_entry(target)["sha256"])


if __name__ == "__main__":
    unittest.main()
