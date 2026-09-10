"""Behavioral tests with synthetic cars only; no real CRM or site access."""

from pathlib import Path
import sys
import tempfile
import time
import unittest
import sqlite3
import hashlib
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import SpecStore, StoreError, StaleJobError


def fact(key="length_mm", value=4900, **kwargs):
    return {"key": key, "value": value, "unit": "mm", "source_url": "https://example.org/catalog/test-car",
            "verification": "verified", **kwargs}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "spec.sqlite"
        self.store = SpecStore(self.path, max_attempts=2)
        self.uid = "TEST-0001"
        self.identity = {"vin": "TESTVIN0000000001", "brand": "Test", "model": "Synthetic", "year": 2017}
        self.vehicle = self.store.upsert_vehicle(self.uid, self.identity)
        self.now = time.time() + 1

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def claim(self):
        return self.store.claim_job("worker", now=self.now)

    def finish(self, job, facts):
        return self.store.approve_candidates(job["id"], job["lease_token"], facts, now=self.now + 1)

    def receipt(self, **changes):
        receipt = {
            "receipt_id": "synthetic-readback-1", "route_id": "synthetic-test-only",
            "uid": self.uid, "revision": 1, "identity_hash": self.vehicle["identity_hash"],
            "facts_digest": self.store.facts_digest(self.uid), "status": "PASS",
            "specification_visible": True, "single_vin": True, "shell_preserved": True,
            "verified_at": "2026-09-09T00:00:00Z", "page_url": "https://example.org/car/test-1",
        }
        receipt.update(changes)
        return receipt

    def test_duplicate_and_price_photo_events_do_not_duplicate_queue(self):
        same = self.store.upsert_vehicle(self.uid, {**self.identity, "vin": " testvin0000000001 ", "year": "2017",
                                                   "price": 13000, "photos": ["changed.jpg"], "description": "edited"})
        self.assertFalse(same["queued"])
        self.assertEqual(1, same["revision"])
        self.assertEqual(1, len(self.store.get_jobs()))
        lease = self.claim()
        self.assertIsNone(self.store.claim_job("worker-2", now=self.now))
        self.finish(lease, [fact()])
        self.assertFalse(self.store.upsert_vehicle(self.uid, self.identity)["queued"])
        self.assertEqual(1, len(self.store.get_jobs()))

    def test_lease_survives_restart_and_old_result_is_rejected(self):
        lease = self.store.claim_job("first", lease_seconds=5, now=self.now)
        self.store.close()
        self.store = SpecStore(self.path, max_attempts=2)
        self.assertIsNone(self.store.claim_job("second", now=self.now + 4))
        second = self.store.claim_job("second", now=self.now + 6)
        self.assertEqual(lease["id"], second["id"])
        self.assertNotEqual(lease["lease_token"], second["lease_token"])
        self.assertEqual(2, second["attempts"])
        with self.assertRaises(StaleJobError):
            self.store.approve_candidates(lease["id"], lease["lease_token"], [fact()], now=self.now + 7)
        self.store.approve_candidates(second["id"], second["lease_token"], [fact()], now=self.now + 7)
        self.assertEqual(1, len(self.store.get_facts(self.uid)))

    def test_expired_max_attempts_stop_without_losing_existing_facts(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        self.store.claim_job("first", lease_seconds=1, now=self.now)
        self.store.claim_job("second", lease_seconds=1, now=self.now + 2)
        self.assertIsNone(self.store.claim_job("third", now=self.now + 4))
        self.assertEqual("exhausted", self.store.get_jobs()[0]["state"])
        self.assertEqual(4900, self.store.get_facts(self.uid)[0]["value"])

    def test_failure_has_bounded_backoff_and_preserves_last_facts(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        first = self.claim()
        self.store.fail_job(first["id"], first["lease_token"], "source unavailable", retry_after=20, now=self.now + 1)
        self.assertIsNone(self.store.claim_job("second", now=self.now + 20))
        second = self.store.claim_job("second", now=self.now + 21)
        result = self.store.fail_job(second["id"], second["lease_token"], "source unavailable", now=self.now + 22)
        self.assertEqual("exhausted", result["state"])
        self.assertEqual(4900, self.store.get_facts(self.uid)[0]["value"])

    def test_partial_acceptance_and_retry_are_atomic_and_never_reset_budget(self):
        self.store.set_manual_fact(self.uid, fact("height_mm", 1500, hidden=True))
        first = self.claim()
        result = self.store.approve_candidates(first["id"], first["lease_token"], [fact()],
            now=self.now + 1, retry_error="danawa:SOURCE_HTTP_ERROR", retry_after=20)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["state"], "retry")
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 1)
        self.assertEqual(self.store.get_facts(self.uid)[0]["value"], 4900)
        self.assertIsNone(self.store.claim_job("second", now=self.now + 20))
        with self.assertRaises(StaleJobError):
            self.store.approve_candidates(first["id"], first["lease_token"], [fact(value=5000)],
                now=self.now + 21, retry_error="SOURCE_HTTP_ERROR")
        second = self.store.claim_job("second", now=self.now + 21)
        result = self.store.approve_candidates(second["id"], second["lease_token"], [fact("width_mm", 1860)],
            now=self.now + 22, retry_error="danawa:SOURCE_HTTP_ERROR", retry_after=0)
        self.assertEqual(result["state"], "exhausted")
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 2)
        self.assertIsNone(self.store.claim_job("third", now=self.now + 23))
        self.assertEqual(len(self.store.get_facts(self.uid)), 2)
        hidden = next(row for row in self.store.get_facts(self.uid, include_hidden=True) if row["key"] == "height_mm")
        self.assertTrue(hidden["manual"])
        self.assertTrue(hidden["hidden"])

    def test_partial_write_failure_rolls_back_facts_candidates_and_job_transition(self):
        job = self.claim()
        save = self.store._save_fact
        def fail_after_write(*args):
            save(*args)
            raise StoreError("synthetic disk error")
        with patch.object(self.store, "_save_fact", side_effect=fail_after_write):
            with self.assertRaises(StoreError):
                self.store.approve_candidates(job["id"], job["lease_token"], [fact()],
                    now=self.now + 1, retry_error="SOURCE_HTTP_ERROR")
        self.assertEqual(self.store.get_facts(self.uid), [])
        self.assertEqual(self.store.get_candidates(self.uid), [])
        self.assertEqual(self.store.get_jobs()[0]["state"], "leased")
        self.assertEqual(self.store.get_jobs()[0]["lease_token"], job["lease_token"])

    def test_partial_approval_rejects_expired_or_changed_identity_without_new_facts(self):
        first = self.store.claim_job("first", lease_seconds=1, now=self.now)
        with self.assertRaises(StaleJobError):
            self.store.approve_candidates(first["id"], first["lease_token"], [fact()],
                now=self.now + 2, retry_error="SOURCE_HTTP_ERROR")
        self.store.upsert_vehicle(self.uid, {**self.identity, "year": 2018})
        with self.assertRaises(StaleJobError):
            self.store.approve_candidates(first["id"], first["lease_token"], [fact()],
                now=self.now + 2, retry_error="SOURCE_HTTP_ERROR")
        self.assertEqual(self.store.get_facts(self.uid), [])

    def test_identity_change_isolates_old_facts_and_rejects_late_completion(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        lease = self.claim()
        changed = self.store.upsert_vehicle(self.uid, {**self.identity, "year": 2018})
        self.assertEqual(2, changed["revision"])
        self.assertEqual([], self.store.get_facts(self.uid))
        with self.assertRaises(StaleJobError):
            self.finish(lease, [fact(value=5000)])
        self.assertEqual(["cancelled", "ready"], [j["state"] for j in self.store.get_jobs()])
        with self.assertRaises(StoreError):
            self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM facts WHERE revision=1").fetchone()[0])

    def test_tombstone_cancels_and_cannot_be_implicitly_reused(self):
        lease = self.claim()
        self.store.delete_vehicle(self.uid)
        self.store.delete_vehicle(self.uid)
        with self.assertRaises(StaleJobError):
            self.finish(lease, [fact()])
        self.assertIsNone(self.store.claim_job("worker", now=self.now + 300))
        with self.assertRaises(StoreError):
            self.store.upsert_vehicle(self.uid, self.identity)
        with self.assertRaises(StoreError):
            self.store.get_facts(self.uid)

    def test_legacy_metadata_manual_and_hidden_statuses_are_preserved(self):
        raw = {"field_key": "length_mm", "field_value": "4900 мм", "is_manual": 1, "is_visible": 0,
               "verification_status": "VERIFIED_10SRC", "source": "old-database",
               "source_url": "https://example.org/historical", "source_domains_json": '["example.org"]',
               "source_urls_json": '["https://example.org/historical"]', "created_at": "2025-01-01"}
        result = self.store.import_legacy(self.uid, [raw], "snapshot-1")
        self.assertEqual(1, result["imported"])
        self.assertEqual([], self.store.get_facts(self.uid))
        loaded = self.store.get_facts(self.uid, include_hidden=True)[0]
        for key, value in raw.items():
            self.assertEqual(value, loaded[key])
        self.assertTrue(loaded["manual"])
        self.assertTrue(loaded["hidden"])
        self.assertFalse(loaded["legacy_import"]["fresh_verification"])
        self.assertEqual("VERIFIED_10SRC", loaded["verification"])
        self.assertTrue(self.store.import_legacy(self.uid, [raw], "snapshot-1")["idempotent"])
        with self.assertRaises(StoreError):
            self.store.import_legacy(self.uid, [{**raw, "field_value": "5100 мм"}], "snapshot-1")

    def test_manual_override_is_not_overwritten_and_missing_value_cannot_erase(self):
        self.store.set_manual_fact(self.uid, fact(value=4950, hidden=True))
        result = self.finish(self.claim(), [fact(value=4900), fact("width_mm", 0), fact("height_mm", None)])
        self.assertEqual(1, result["review"])
        self.assertEqual(2, result["rejected"])
        loaded = self.store.get_facts(self.uid, include_hidden=True)
        self.assertEqual(4950, loaded[0]["value"])
        self.assertTrue(loaded[0]["manual"])
        self.assertTrue(loaded[0]["hidden"])
        self.store.set_manual_fact(self.uid, fact(value=5000))
        self.assertTrue(self.store.get_facts(self.uid, include_hidden=True)[0]["hidden"])
        self.store.set_hidden(self.uid, "length_mm", False)
        self.assertEqual(5000, self.store.get_facts(self.uid)[0]["value"])

    def test_same_value_refresh_preserves_hidden_and_original_source(self):
        self.store.import_legacy(self.uid, [fact(hidden=True, source_url="https://example.org/old")], "snapshot-1")
        result = self.finish(self.claim(), [fact(source_url="https://example.org/new")])
        self.assertEqual(1, result["accepted"])
        loaded = self.store.get_facts(self.uid, include_hidden=True)[0]
        self.assertTrue(loaded["hidden"])
        self.assertEqual("https://example.org/old", loaded["source_url"])
        self.assertEqual("https://example.org/new", loaded["evidence"][0]["source_url"])

    def test_disagreeing_sources_are_all_reviewed_not_first_wins(self):
        result = self.finish(self.claim(), [fact(value=4900), fact(value=5000), fact("width_mm", 1860)])
        self.assertEqual(2, result["review"])
        self.assertEqual(1, result["accepted"])
        self.assertEqual(["width_mm"], [item["key"] for item in self.store.get_facts(self.uid)])

    def test_unverified_unsupported_and_cross_identity_facts_are_not_accepted(self):
        result = self.finish(self.claim(), [
            fact(verification="VERIFIED_10SRC"),
            fact("width_mm", 1860, source_url=""),
            fact("height_mm", 1500, identity_hash="wrong"),
            fact("wheelbase_mm", 2800, manual=True),
        ])
        self.assertEqual(3, result["review"])
        self.assertEqual(1, result["rejected"])
        self.assertEqual([], self.store.get_facts(self.uid))

    def test_valid_zero_is_retained_but_placeholder_zero_is_not(self):
        result = self.finish(self.claim(), [
            fact("tailpipe_co2_g_km", 0, unit="g/km"),
            fact("doors", 0, unit=None),
            fact("unknown_dimension", 0, placeholder=True),
        ])
        self.assertEqual(1, result["accepted"])
        self.assertEqual(2, result["rejected"])
        self.assertEqual(0, self.store.get_facts(self.uid)[0]["value"])

    def test_publication_requires_exact_explicit_receipt_and_does_not_publish_from_collection(self):
        self.finish(self.claim(), [fact()])
        self.assertFalse(self.store.get_vehicle(self.uid)["published"])
        self.assertIsNone(self.store.get_publication_snapshot(self.uid))
        for receipt in ({}, self.receipt(shell_preserved=False), self.receipt(facts_digest="wrong")):
            with self.assertRaises(StoreError):
                self.store.mark_publication_verified(self.uid, 1, receipt)
            self.assertFalse(self.store.get_vehicle(self.uid)["published"])
        snapshot = self.store.mark_publication_verified(self.uid, 1, self.receipt())
        self.assertTrue(self.store.get_vehicle(self.uid)["published"])
        self.assertEqual(snapshot, self.store.mark_publication_verified(self.uid, 1, self.receipt()))
        self.store.set_manual_fact(self.uid, fact(value=4950))
        self.assertEqual(4900, self.store.get_publication_snapshot(self.uid)["facts"][0]["value"])
        self.assertEqual(4950, self.store.get_facts(self.uid)[0]["value"])
        self.store.set_published(self.uid, False)
        self.assertEqual(4950, self.store.get_facts(self.uid)[0]["value"])

    def test_exact_empty_publication_receipt_allows_later_specification_sync(self):
        receipt = self.receipt()
        for changes in ({"facts_digest": "wrong"}, {"shell_preserved": False},
                        {"identity_hash": "wrong"}, {"specification_visible": False}):
            with self.assertRaises(StoreError):
                self.store.mark_publication_verified(self.uid, 1, {**receipt, **changes})
        snapshot = self.store.mark_publication_verified(self.uid, 1, receipt)
        self.assertEqual(snapshot["facts"], [])
        self.assertTrue(self.store.get_vehicle(self.uid)["published"])
        self.finish(self.claim(), [fact()])
        self.assertNotEqual(self.store.facts_digest(self.uid), receipt["facts_digest"])
        self.assertEqual(self.store.get_publication_snapshot(self.uid)["facts"], [])
        updated = self.store.mark_publication_verified(self.uid, 1,
            self.receipt(receipt_id="synthetic-spec-sync-2"))
        self.assertEqual(updated["facts"][0]["value"], 4900)

    def test_old_publication_snapshot_cannot_be_used_for_changed_identity(self):
        self.finish(self.claim(), [fact()])
        old_receipt = self.receipt()
        self.store.mark_publication_verified(self.uid, 1, old_receipt)
        self.store.upsert_vehicle(self.uid, {**self.identity, "vin": "TESTVIN0000000002"}, published=True)
        self.assertIsNone(self.store.get_publication_snapshot(self.uid))
        with self.assertRaises(StoreError):
            self.store.mark_publication_verified(self.uid, 1, old_receipt)
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM publication_snapshots").fetchone()[0])

    def test_separate_connections_cannot_claim_same_live_job(self):
        with SpecStore(self.path) as second:
            first_job = self.claim()
            self.assertIsNone(second.claim_job("other-worker", now=self.now))
            self.assertEqual(first_job["lease_token"], second.get_jobs()[0]["lease_token"])

    def test_unrelated_crm_database_is_rejected_without_modification(self):
        unrelated_path = Path(self.temp.name) / "synthetic-crm.sqlite"
        with sqlite3.connect(unrelated_path) as database:
            database.execute("CREATE TABLE cars(uid TEXT)")
            database.execute("INSERT INTO cars VALUES('SYNTHETIC')")
        before = hashlib.sha256(unrelated_path.read_bytes()).hexdigest()
        with self.assertRaises(StoreError):
            SpecStore(unrelated_path)
        self.assertEqual(before, hashlib.sha256(unrelated_path.read_bytes()).hexdigest())
        self.assertFalse(Path(str(unrelated_path) + "-wal").exists())

    def test_target_compatible_delete_journal_without_wal_sidecars(self):
        self.assertEqual("delete", self.store.db.execute("PRAGMA journal_mode").fetchone()[0])
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        self.assertFalse(Path(str(self.path) + "-wal").exists())
        self.assertFalse(Path(str(self.path) + "-shm").exists())

    def test_replayed_receipt_does_not_reverse_unpublish(self):
        self.finish(self.claim(), [fact()])
        receipt = self.receipt()
        self.store.mark_publication_verified(self.uid, 1, receipt)
        self.store.set_published(self.uid, False)
        with self.assertRaises(StoreError):
            self.store.mark_publication_verified(self.uid, 1, receipt)
        self.assertFalse(self.store.get_vehicle(self.uid)["published"])

    def test_source_policy_acceptance_is_bound_to_exact_evidence_and_identity(self):
        job = self.claim()

        def approved(raw):
            raw = {**raw, "verification_status": "MODEL_VERIFIED"}
            digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            raw["policy_acceptance"] = {
                "policy_id": "UA-ART-SPEC-REBUILD-10-001:v1", "decision": "ACCEPTED",
                "uid": self.uid, "revision": job["revision"], "identity_hash": job["identity_hash"],
                "source_ids": ["synthetic_source"], "evidence_sha256": digest,
            }
            return raw

        valid = approved(fact())
        changed_value = approved(fact("width_mm", 1800))
        changed_value["value"] = 1900
        changed_identity = approved(fact("height_mm", 1500))
        changed_identity["policy_acceptance"]["identity_hash"] = "wrong"
        missing_receipt = fact("wheelbase_mm", 2800, verification_status="VEHICLE_VERIFIED")
        disguised_legacy = approved(fact("power_hp", 180))
        disguised_legacy["verification_status"] = "VERIFIED_10SRC"
        pending = fact("torque_nm", 250, verification_status="DOCUMENT_CANDIDATE")
        result = self.finish(job, [valid, changed_value, changed_identity, missing_receipt, disguised_legacy, pending])
        self.assertEqual(1, result["accepted"])
        self.assertEqual(5, result["review"])
        saved = self.store.get_facts(self.uid)[0]
        self.assertEqual("MODEL_VERIFIED", saved["verification_status"])
        self.assertEqual("verified", saved["verification"])
        self.assertEqual(valid["policy_acceptance"], saved["policy_acceptance"])

    def test_explicit_refresh_is_idempotent_and_never_replaces_active_work(self):
        with self.assertRaises(StoreError):
            self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")
        old = self.claim()
        with self.assertRaises(StoreError):
            self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")
        self.finish(old, [fact()])
        refreshed = self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")
        self.assertTrue(refreshed["queued"])
        replay = self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")
        self.assertTrue(replay["idempotent"])
        self.assertEqual(1, len(self.store.get_jobs()))
        self.assertEqual(0, self.store.get_jobs()[0]["attempts"])
        job = self.store.claim_job("new-worker", now=self.now + 2)
        self.assertNotEqual(old["lease_token"], job["lease_token"])
        with self.assertRaises(StaleJobError):
            self.store.approve_candidates(old["id"], old["lease_token"], [fact(value=5000)], now=self.now + 3)
        self.store.approve_candidates(job["id"], job["lease_token"], [fact("width_mm", 1800)], now=self.now + 3)
        self.assertEqual(2, len(self.store.get_facts(self.uid)))
        self.assertTrue(self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")["idempotent"])
        self.assertEqual("succeeded", self.store.get_jobs()[0]["state"])
        with self.assertRaises(StoreError):
            self.store.request_refresh(self.uid, "different reason", "refresh-1")
        self.store.upsert_vehicle(self.uid, {**self.identity, "year": 2018})
        with self.assertRaises(StoreError):
            self.store.request_refresh(self.uid, "approved source enabled", "refresh-1")

    def lifecycle_receipt(self, action="delete", receipt_id="synthetic-lifecycle-1"):
        vehicle = self.store.get_vehicle(self.uid)
        return {"uid": self.uid, "action": action, "revision": vehicle["revision"],
                "identity_hash": vehicle["identity_hash"], "facts_digest": self.store.facts_digest(self.uid),
                "status": "PASS", "receipt_id": receipt_id, "route_id": "synthetic-route",
                "verified_at": "2026-09-09T00:00:00Z", "plan_id": "synthetic-plan"}

    def apply_lifecycle(self, receipt):
        return self.store.mark_lifecycle_verified(self.uid, receipt["action"], receipt["revision"],
            receipt["identity_hash"], receipt["facts_digest"], receipt)

    def test_lifecycle_readback_rejects_identity_changed_on_other_connection(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        old = self.lifecycle_receipt()
        with SpecStore(self.path) as other:
            other.upsert_vehicle(self.uid, {**self.identity, "year": 2018}, published=True)
            other.set_manual_fact(self.uid, fact(value=5100))
        with self.assertRaisesRegex(StoreError, "identity changed"):
            self.apply_lifecycle(old)
        self.assertFalse(self.store.get_vehicle(self.uid)["tombstoned"])
        self.assertTrue(self.store.get_vehicle(self.uid)["published"])
        self.assertEqual(5100, self.store.get_facts(self.uid)[0]["value"])
        self.assertEqual("ready", self.store.get_jobs()[-1]["state"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM lifecycle_receipts").fetchone()[0])

    def test_lifecycle_readback_rejects_facts_changed_on_other_connection(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        self.store.set_published(self.uid, True)
        old = self.lifecycle_receipt("hide")
        with SpecStore(self.path) as other:
            other.set_manual_fact(self.uid, fact(value=5050))
        with self.assertRaisesRegex(StoreError, "facts changed"):
            self.apply_lifecycle(old)
        self.assertTrue(self.store.get_vehicle(self.uid)["published"])
        self.assertEqual(5050, self.store.get_facts(self.uid)[0]["value"])

    def test_current_lifecycle_receipt_applies_once_and_preserves_facts(self):
        self.store.import_legacy(self.uid, [fact()], "snapshot-1")
        hide = self.lifecycle_receipt("hide")
        self.assertFalse(self.apply_lifecycle(hide)["idempotent"])
        self.assertTrue(self.apply_lifecycle(hide)["idempotent"])
        self.assertEqual(4900, self.store.get_facts(self.uid)[0]["value"])
        self.store.set_published(self.uid, True)
        with self.assertRaisesRegex(StoreError, "newer operation"):
            self.apply_lifecycle(hide)
        delete = self.lifecycle_receipt("delete", "synthetic-lifecycle-delete")
        self.assertFalse(self.apply_lifecycle(delete)["idempotent"])
        self.assertTrue(self.apply_lifecycle(delete)["idempotent"])
        self.assertTrue(self.store.get_vehicle(self.uid)["tombstoned"])
        self.assertEqual("cancelled", self.store.get_jobs()[0]["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
