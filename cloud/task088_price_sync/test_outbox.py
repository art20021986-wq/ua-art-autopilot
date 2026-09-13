import hashlib
from dataclasses import replace
import pathlib
import sqlite3
import tempfile
import unittest

import outbox as O


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "fixture.sqlite"
        self.db = self.connect()
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY,price_uah INTEGER,price_georgia INTEGER)")
        self.db.execute("INSERT INTO cars VALUES(10,10000,8000)")
        self.db.execute("CREATE TABLE audit(value TEXT)")
        O.install(self.db)
        self.db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        self.addCleanup(db.close)
        return db

    def pending(self, key="edit1", car=10, ua="10000.00", ge="8200.00", stamp=1000):
        return O.enqueue(self.db, event_key=digest(key), car_id=car, ukraine_usd=ua,
                         georgia_usd=ge, now_ms=stamp)

    def begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def seeded_claim(self):
        self.begin()
        self.pending()
        self.db.commit()
        self.begin()
        result = O.claim(self.db, event_key=digest("edit1"), nonce=digest("claim1"), now_ms=1100)
        self.db.commit()
        return result

    def recovery_evidence(self, **overrides):
        values = dict(recovery_key=digest("recovery1"), event_key=digest("edit1"),
                      claim_nonce=digest("claim1"), current_revision=1, outcome="NO_EFFECT",
                      reason="TRANSPORT_REPAIRED_UNCHANGED_PUBLIC_FILES", cause_resolved=True,
                      preflight_verified=True, public_state_verified=True, prices_match_current=False,
                      cause_fix_sha256=digest("verified transport fix"),
                      preflight_sha256=digest("fresh independent preflight"), preflight_ms=1250,
                      observed_ms=1270, card_sha256=digest("actual public card bytes"),
                      catalog_sha256=digest("actual public catalog bytes"),
                      evidence_sha256=digest("bound signed recovery evidence"))
        values.update(overrides)
        return O.RecoveryEvidence(**values)

    def recover(self, evidence=None, now_ms=1300):
        return O.reconcile_verified(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                    evidence=evidence or self.recovery_evidence(), now_ms=now_ms)

    def test_schema_install_does_not_commit_or_change_cars_schema(self):
        empty = self.connect()
        empty.execute("BEGIN IMMEDIATE")
        O.install(empty)
        empty.execute("INSERT INTO audit VALUES('not committed')")
        self.assertTrue(empty.in_transaction)
        empty.rollback()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
        self.assertEqual([r[1] for r in self.db.execute("PRAGMA table_info(cars)")],
                         ["id", "price_uah", "price_georgia"])

    def test_first_install_is_transactional(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(db.close)
        db.execute("BEGIN IMMEDIATE")
        O.install(db)
        db.rollback()
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name=?", (O.TABLE,)).fetchone())

    def test_install_refuses_unknown_schema(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(db.close)
        db.execute("BEGIN IMMEDIATE")
        db.execute(f"CREATE TABLE {O.TABLE} (event_key TEXT)")
        with self.assertRaisesRegex(O.OutboxError, "SCHEMA_MISMATCH"):
            O.install(db)
        self.assertTrue(db.in_transaction)

    def test_no_api_silently_starts_or_commits_transaction(self):
        with self.assertRaisesRegex(O.OutboxError, "CALLER_TRANSACTION"):
            O.install(self.db)
        with self.assertRaisesRegex(O.OutboxError, "CALLER_TRANSACTION"):
            self.pending()
        self.assertFalse(self.db.in_transaction)

    def test_crm_audit_and_event_rollback_as_one_unit(self):
        self.begin()
        self.db.execute("UPDATE cars SET price_georgia=8200 WHERE id=10")
        self.db.execute("INSERT INTO audit VALUES('GE 8200')")
        self.pending()
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT price_georgia FROM cars").fetchone()[0], 8000)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
        self.assertIsNone(O.get(self.db, digest("edit1")))

    def test_other_connection_sees_only_committed_price_and_event(self):
        observer = self.connect()
        self.begin()
        self.db.execute("UPDATE cars SET price_georgia=8200 WHERE id=10")
        self.pending()
        self.assertIsNone(O.get(observer, digest("edit1")))
        self.assertEqual(observer.execute("SELECT price_georgia FROM cars").fetchone()[0], 8000)
        self.db.commit()
        self.assertEqual(observer.execute("SELECT price_georgia FROM cars").fetchone()[0], 8200)
        self.assertEqual(O.get(observer, digest("edit1"))["georgia_usd"], "8200.00")

    def test_duplicate_intent_is_idempotent_but_conflicting_payload_rolls_back(self):
        self.begin()
        original = self.pending()
        self.db.commit()
        self.begin()
        self.assertEqual(self.pending(stamp=2000), original)
        self.db.execute("UPDATE cars SET price_georgia=9000 WHERE id=10")
        with self.assertRaisesRegex(O.OutboxError, "PAYLOAD_CONFLICT"):
            self.pending(ge="9000.00")
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT price_georgia FROM cars").fetchone()[0], 8000)
        self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {O.TABLE}").fetchone()[0], 1)

    def test_latest_edit_supersedes_pending_and_revision_tracks_serial_commit_order(self):
        self.begin()
        self.pending()
        self.db.commit()
        self.begin()
        latest = self.pending("edit2", ge="8500.00", stamp=900)
        other = self.pending("other", car=11)
        self.db.commit()
        self.assertEqual(latest["revision"], 2)
        self.assertEqual(other["revision"], 1)
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "SUPERSEDED")
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "ALREADY_SUPERSEDED"):
            self.pending()
        self.db.rollback()

    def test_rolled_back_revision_is_not_observable_or_reserved(self):
        self.begin()
        self.pending()
        self.db.rollback()
        self.begin()
        self.assertEqual(self.pending("edit2")["revision"], 1)
        self.db.commit()

    def test_two_connections_cannot_claim_same_event(self):
        self.begin()
        self.pending()
        self.db.commit()
        second = self.connect()
        self.begin()
        O.claim(self.db, event_key=digest("edit1"), nonce=digest("claim1"), now_ms=1100)
        second.execute("BEGIN")
        with self.assertRaises(sqlite3.OperationalError):
            O.claim(second, event_key=digest("edit1"), nonce=digest("claim2"), now_ms=1100)
        second.rollback()
        self.db.commit()
        second.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(O.OutboxError, "NOT_PENDING"):
            O.claim(second, event_key=digest("edit1"), nonce=digest("claim2"), now_ms=1200)
        second.rollback()

    def test_new_revision_cannot_bypass_inflight_claim_or_allow_old_ack(self):
        self.seeded_claim()
        self.begin()
        self.pending("edit2", ge="9000.00", stamp=1200)
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "RECONCILIATION"):
            O.claim(self.db, event_key=digest("edit2"), nonce=digest("claim2"), now_ms=1300)
        with self.assertRaisesRegex(O.OutboxError, "NEVER_REPLAY"):
            O.record_verified_publication(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                          receipt_sha256=digest("receipt"), now_ms=1300)
        self.db.rollback()
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "CLAIMED")

    def test_failure_is_durable_and_cannot_be_reset_by_ack_or_new_edit(self):
        self.seeded_claim()
        self.begin()
        O.stop(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
               reason="PUBLIC_READBACK_FAILED", now_ms=1200)
        self.db.commit()
        reopened = self.connect()
        self.assertEqual(O.get(reopened, digest("edit1"))["state"], "STOPPED")
        self.begin()
        self.pending("edit2", ge="9000.00", stamp=1300)
        self.pending("independent", car=11, stamp=1300)
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "RECONCILIATION"):
            O.claim(self.db, event_key=digest("edit2"), nonce=digest("claim2"), now_ms=1400)
        with self.assertRaisesRegex(O.OutboxError, "CURRENT_CLAIM"):
            O.record_verified_publication(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                          receipt_sha256=digest("receipt"), now_ms=1400)
        self.assertEqual(O.claim(self.db, event_key=digest("independent"),
                                 nonce=digest("claim-other"), now_ms=1400)["state"], "CLAIMED")
        self.db.commit()

    def test_stale_claim_nonce_cannot_stop_or_ack(self):
        self.seeded_claim()
        self.begin()
        for operation in (lambda: O.stop(self.db, event_key=digest("edit1"), nonce=digest("wrong"),
                                        reason="FAILED", now_ms=1200),
                          lambda: O.record_verified_publication(self.db, event_key=digest("edit1"),
                                        nonce=digest("wrong"), receipt_sha256=digest("receipt"), now_ms=1200)):
            with self.assertRaisesRegex(O.OutboxError, "CURRENT_CLAIM"):
                operation()
        self.db.rollback()

    def test_current_verified_ack_persists_and_never_reclaims(self):
        self.seeded_claim()
        self.begin()
        O.record_verified_publication(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                      receipt_sha256=digest("receipt"), now_ms=1500)
        self.assertTrue(self.db.in_transaction)
        self.db.commit()
        self.assertEqual(O.get(self.connect(), digest("edit1"))["state"], "PUBLISHED")
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "NOT_PENDING"):
            O.claim(self.db, event_key=digest("edit1"), nonce=digest("claim2"), now_ms=1800)
        self.db.rollback()

    def test_input_shape_and_timing_are_fail_closed(self):
        self.begin()
        for kwargs in ({"car": True}, {"ua": "10e3"}, {"ge": 8200}, {"stamp": True}):
            with self.assertRaises(O.OutboxError):
                self.pending(**kwargs)
        self.pending()
        with self.assertRaisesRegex(O.OutboxError, "BEFORE_EVENT"):
            O.claim(self.db, event_key=digest("edit1"), nonce=digest("claim1"), now_ms=999)
        self.db.rollback()

    def test_recovery_closes_attempt_without_requeue_or_erasing_failure_history(self):
        self.seeded_claim()
        self.begin()
        O.stop(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
               reason="CONNECTION_UNCERTAIN", now_ms=1200)
        self.pending("edit2", ge="9000.00", stamp=1210)
        self.db.commit()
        self.begin()
        event = self.recover(self.recovery_evidence(current_revision=2))
        self.assertEqual(event["state"], "RECONCILED")
        self.assertEqual(event["reason"], "CONNECTION_UNCERTAIN")
        self.assertEqual(event["claim_nonce"], digest("claim1"))
        record = O.get_recovery(self.db, digest("recovery1"))
        self.assertEqual((record["prior_state"], record["prior_reason"], record["prior_finished_ms"]),
                         ("STOPPED", "CONNECTION_UNCERTAIN", 1200))
        self.assertEqual(record["outcome"], "NO_EFFECT")
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "NOT_PENDING"):
            O.claim(self.db, event_key=digest("edit1"), nonce=digest("replay"), now_ms=1400)
        self.assertEqual(O.claim(self.db, event_key=digest("edit2"), nonce=digest("claim2"),
                                 now_ms=1400)["state"], "CLAIMED")
        self.db.commit()

    def test_recovery_record_and_terminal_transition_rollback_together(self):
        self.seeded_claim()
        self.begin()
        self.recover()
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "RECONCILED")
        self.db.rollback()
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "CLAIMED")
        self.assertIsNone(O.get_recovery(self.db, digest("recovery1")))

    def test_partial_recovery_storage_failure_cannot_commit_event_transition(self):
        self.seeded_claim()
        self.begin()
        self.db.execute(f"CREATE TRIGGER reject_recovery BEFORE UPDATE ON {O.TABLE} "
                        "WHEN NEW.state='RECONCILED' BEGIN SELECT RAISE(ABORT,'TEST_ABORT'); END")
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "TEST_ABORT"):
            self.recover()
        self.db.rollback()
        self.assertIsNone(O.get_recovery(self.db, digest("recovery1")))
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "CLAIMED")

    def test_recovery_rejects_missing_false_stale_or_wrong_attempt_proof(self):
        self.seeded_claim()
        self.begin()
        bad_values = (
            {"event_key": digest("another event")}, {"claim_nonce": digest("another claim")},
            {"cause_resolved": False}, {"preflight_verified": False}, {"public_state_verified": False},
            {"cause_resolved": 1}, {"card_sha256": "HTTP200"}, {"catalog_sha256": None},
            {"current_revision": 2}, {"current_revision": True}, {"preflight_ms": 1000},
            {"observed_ms": 1301}, {"outcome": "RETRY"}, {"reason": "unsanitized user text"},
        )
        for overrides in bad_values:
            with self.subTest(overrides=overrides), self.assertRaises(O.OutboxError):
                self.recover(self.recovery_evidence(**overrides))
        with self.assertRaisesRegex(O.OutboxError, "PREFLIGHT_STALE"):
            self.recover(now_ms=31251)
        with self.assertRaisesRegex(O.OutboxError, "EXACT_RECOVERY_EVIDENCE"):
            O.reconcile_verified(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                  evidence={"verified": True}, now_ms=1300)
        self.assertIsNone(O.get_recovery(self.db, digest("recovery1")))
        self.db.rollback()

    def test_recovery_preflight_must_follow_durable_stop(self):
        self.seeded_claim()
        self.begin()
        O.stop(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
               reason="CONNECTION_UNCERTAIN", now_ms=1280)
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "ATTEMPT_WINDOW"):
            self.recover()
        self.db.rollback()

    def test_same_recovery_proof_is_idempotent_after_time_and_newer_crm_edit(self):
        self.seeded_claim()
        self.begin()
        original = self.recover()
        record = O.get_recovery(self.db, digest("recovery1"))
        self.db.commit()
        self.begin()
        self.pending("edit2", ge="9000.00", stamp=1400)
        self.db.commit()
        self.begin()
        self.assertEqual(self.recover(now_ms=100000), original)
        self.assertEqual(O.get_recovery(self.db, digest("recovery1")), record)
        self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {O.RECOVERY_TABLE}").fetchone()[0], 1)
        self.assertEqual(O.get(self.db, digest("edit2"))["state"], "PENDING")
        with self.assertRaisesRegex(O.OutboxError, "EVIDENCE_CONFLICT"):
            self.recover(self.recovery_evidence(evidence_sha256=digest("different proof")))
        with self.assertRaisesRegex(O.OutboxError, "UNCERTAIN_ATTEMPT"):
            self.recover(self.recovery_evidence(recovery_key=digest("different recovery")))
        self.db.rollback()

    def test_recovery_audit_ledger_is_append_only(self):
        self.seeded_claim()
        self.begin()
        self.recover()
        self.db.commit()
        self.begin()
        for sql in (f"UPDATE {O.RECOVERY_TABLE} SET prior_reason='HIDDEN'",
                    f"DELETE FROM {O.RECOVERY_TABLE}"):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "APPEND_ONLY"):
                self.db.execute(sql)
        self.db.rollback()
        self.assertIsNotNone(O.get_recovery(self.db, digest("recovery1")))

    def test_stopped_attempt_can_close_as_actual_published_only_with_receipt(self):
        self.seeded_claim()
        self.begin()
        O.stop(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
               reason="POST_SWITCH_READBACK_TIMEOUT", now_ms=1200)
        self.db.commit()
        self.begin()
        evidence = self.recovery_evidence(outcome="PUBLISHED", prices_match_current=True,
                    publication_receipt_sha256=digest("real recovered publication receipt"),
                    reason="PUBLICATION_FOUND_COMPLETE_AND_VERIFIED")
        for bad in (replace(evidence, publication_receipt_sha256=None),
                    replace(evidence, prices_match_current=False)):
            with self.assertRaises(O.OutboxError):
                self.recover(bad)
        result = self.recover(evidence)
        self.assertEqual(result["state"], "PUBLISHED")
        self.assertEqual(result["receipt_sha256"], evidence.publication_receipt_sha256)
        self.assertEqual(result["reason"], "POST_SWITCH_READBACK_TIMEOUT")
        self.db.commit()

    def test_old_revision_cannot_be_acknowledged_by_recovery(self):
        self.seeded_claim()
        self.begin()
        self.pending("edit2", ge="9000.00", stamp=1200)
        self.db.commit()
        self.begin()
        evidence = self.recovery_evidence(outcome="PUBLISHED", prices_match_current=True,
                    publication_receipt_sha256=digest("receipt"))
        with self.assertRaisesRegex(O.OutboxError, "CURRENT_REVISION_CHANGED"):
            self.recover(evidence)
        with self.assertRaisesRegex(O.OutboxError, "OLD_REVISION_CANNOT"):
            self.recover(replace(evidence, current_revision=2))
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "CLAIMED")
        self.assertIsNone(O.get_recovery(self.db, digest("recovery1")))
        self.db.rollback()

    def test_restored_attempt_is_not_misreported_as_published(self):
        self.seeded_claim()
        self.begin()
        evidence = self.recovery_evidence(outcome="RESTORED", reason="BASELINE_FILES_RESTORED")
        with self.assertRaisesRegex(O.OutboxError, "CANNOT_HAVE_PUBLICATION_RECEIPT"):
            self.recover(replace(evidence, publication_receipt_sha256=digest("fake receipt")))
        restored = self.recover(evidence)
        self.assertEqual(restored["state"], "RECONCILED")
        self.assertIsNone(restored["receipt_sha256"])
        self.db.commit()
        self.begin()
        with self.assertRaisesRegex(O.OutboxError, "CURRENT_CLAIM"):
            O.record_verified_publication(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                          receipt_sha256=digest("later HTTP success"), now_ms=1400)
        self.db.rollback()

    def test_recovery_requires_explicit_caller_transaction(self):
        self.seeded_claim()
        with self.assertRaisesRegex(O.OutboxError, "CALLER_TRANSACTION"):
            self.recover()

    def test_install_recovery_schema_and_append_only_triggers_is_transactional(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(db.close)
        db.execute("BEGIN IMMEDIATE")
        O.install(db)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0], 2)
        db.rollback()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','trigger')").fetchone()[0], 0)
        self.begin()
        self.db.execute(f"DROP TRIGGER {O.RECOVERY_TABLE}_no_delete")
        self.db.execute(f"CREATE TRIGGER {O.RECOVERY_TABLE}_no_delete BEFORE DELETE ON {O.RECOVERY_TABLE} BEGIN SELECT 1; END")
        with self.assertRaisesRegex(O.OutboxError, "TRIGGER_MISMATCH"):
            O.install(self.db)
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
