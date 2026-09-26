"""Synthetic evidence tests exercise rejection only; they are not live receipts."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import verify_preview as V

G = V.G


class PreviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="price-proof-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in G.SOURCE_ROOTS:
            directory = self.root / relative
            directory.mkdir(parents=True)
            (directory / "fixture_source.py").write_text("# TEST FIXTURE ONLY\n")
        for relative in G.WORKFLOWS + G.CANONICAL_SOURCES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# TEST FIXTURE ONLY\n")
        source = G.ROOT / "cloud/task088_price_sync/install_package.py"
        (self.root / "cloud/task088_price_sync/install_package.py").write_bytes(source.read_bytes())
        self.task = "TEST-ONLY-PRICE-PROTECTION"
        self.now = 1789380000
        self.preview = {
            "contract": "TASK088-FINAL-V5-PREVIEW-GATE-1", "task_id": self.task, "status": "PASS",
            "candidate_manifest_sha256": G.digest(b"TEST fixture candidate"),
            "database": {"cars_sha256": G.digest(b"TEST cars"), "audit_sha256": G.digest(b"TEST audit"),
                         "published_sha256": G.digest(b"TEST published"), "published_codes": ["UA-0001", "UA-0019"]},
            "schema_sha256": G.digest(b"TEST schema"), "system_inventory_sha256": G.digest(b"TEST inventory"),
            "published_codes": ["UA-0001", "UA-0019"],
            "evaluated_at": V.datetime.fromtimestamp(self.now, V.timezone.utc).isoformat(),
            "checks": {name: "PASS" for name in V.preview_checks(self.root)},
            "source_files_sha256": G.source_inventory(self.root),
        }
        self.bind()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = G.encoded(value)
        path.write_bytes(payload)
        return G.digest(payload)

    def bind(self, changed_paths=None):
        preview_hash = self.write("evidence/preview.json", self.preview)
        manifest_hash = self.write("evidence/manifest.json", {
            "task_id": self.task, "install_files_sha256": self.preview["candidate_manifest_sha256"]})
        gate_hash = self.write("evidence/gate-a.json", {
            "task_id": self.task, "status": "PASS", "manifest_sha256": manifest_hash,
            "price_protection_preview_path": "evidence/preview.json", "preview_gate_sha256": preview_hash})
        self.request = {"task_id": self.task, "production_required": True,
                        "changed_paths": changed_paths or ["yadro.py"],
                        "critical": {"manifest_path": "evidence/manifest.json", "manifest_sha256": manifest_hash,
                                     "gate_a_path": "evidence/gate-a.json", "gate_a_sha256": gate_hash}}
        self.request_hash = self.write("tasks/requests/test-only.json", self.request)

    def verify(self, **kwargs):
        return V.verify(self.root, "tasks/requests/test-only.json", self.request_hash, now=kwargs.pop("now", self.now), **kwargs)

    def test_binding_reports_no_observations_and_grants_no_production_authority(self):
        result = self.verify()
        self.assertEqual(result["evidence_binding"], "PASS")
        self.assertEqual(result["published_count"], 2)
        self.assertFalse(result["observations_generated"])
        self.assertFalse(result["production_authorized"])

    def test_each_missing_or_failed_preview_check_blocks_even_when_rehashed(self):
        original = deepcopy(self.preview)
        for name in V.preview_checks(self.root):
            for operation in ("remove", "FAIL", "NOT_RUN", True):
                with self.subTest(check=name, operation=operation):
                    self.preview = deepcopy(original)
                    if operation == "remove":
                        del self.preview["checks"][name]
                    else:
                        self.preview["checks"][name] = operation
                    self.bind()
                    with self.assertRaisesRegex(G.ProtectionError, "NOT_100_PERCENT"):
                        self.verify()

    def test_freshness_rejects_stale_future_and_ambiguous_timezone(self):
        for now in (self.now + 1801, self.now - 1):
            with self.assertRaisesRegex(G.ProtectionError, "STALE_OR_FUTURE"):
                self.verify(now=now)
        self.preview["evaluated_at"] = "2026-09-14T10:00:00"
        self.bind()
        with self.assertRaisesRegex(G.ProtectionError, "TIMESTAMP"):
            self.verify()

    def test_rebinding_old_snapshot_cannot_hide_current_source_change(self):
        (self.root / G.SOURCE_ROOTS[0] / "fixture_source.py").write_text("# changed after preview\n")
        self.bind()
        with self.assertRaisesRegex(G.ProtectionError, "CURRENT_SOURCE_BINDING"):
            self.verify()

    def test_missing_database_hash_or_mismatched_published_inventory_blocks(self):
        self.preview["database"]["cars_sha256"] = "PASS"
        self.bind()
        with self.assertRaisesRegex(G.ProtectionError, "DATABASE_INVENTORY_BINDING"):
            self.verify()
        self.preview["database"]["cars_sha256"] = G.digest(b"TEST cars")
        self.preview["published_codes"] = ["UA-0001"]
        self.bind()
        with self.assertRaisesRegex(G.ProtectionError, "PUBLISHED_SET_BINDING"):
            self.verify()

    def test_edited_receipt_bytes_fail_without_canonical_rebinding(self):
        self.preview["checks"]["mobile"] = "FAIL"
        self.write("evidence/preview.json", self.preview)
        with self.assertRaisesRegex(G.ProtectionError, "HASH_TASK_CANDIDATE_BINDING"):
            self.verify()

    def test_unrelated_scope_does_not_acquire_new_price_preview_requirement(self):
        self.bind(changed_paths=["info/contact.txt"])
        (self.root / "evidence/preview.json").unlink()
        self.assertEqual(self.verify()["evidence_binding"], "NOT_APPLICABLE")

    def test_all_named_production_components_are_in_scope(self):
        for path in ("cars_ui.py", "db.py", "crm.db", "production/crm.db/schema", "yadro.py", "video/UA-0019.html",
                     "site/katalog.html", "video/index.html", "automation/execution_contract.py",
                     ".github/workflows/uaart_critical.yml", "cloud/new_release/publish_helper.py",
                     "assets/ua-site-languages.js", "cloud/task088_price_sync/outbox.py"):
            with self.subTest(path=path):
                self.assertTrue(V.relevant([path]))


if __name__ == "__main__":
    unittest.main()
