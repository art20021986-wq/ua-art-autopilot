import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from deletion_state import (
    DeletionError, DeletionStore, ImmediateTransaction,
    application_schema_sha256, install_additive_schema,
)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT UNIQUE, vin TEXT, published INTEGER, price REAL, photos BLOB, note TEXT)")
        self.conn.executemany("INSERT INTO cars VALUES (?,?,?,?,?,?,?)", [
            (8, "UA-0002", "wdd-1014", 1, 8500.0, b"\x00private\xff", None),
            (9, "UA-0003", "other0015", 1, 9500.0, b"neighbor", "untouched"),
        ])
        self.conn.commit()
        self.held = True
        self.verification_allowed = True
        self.verifications = []
        self.approved = application_schema_sha256(self.conn)
        self.store = DeletionStore(approved_application_schema_sha256=self.approved,
                                   verify_retirement=self.verify)
        with self.tx() as tx:
            install_additive_schema(tx, approved_application_schema_sha256=self.approved)
            tx.commit()
        self.original = self.rows()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def fence(self):
        if not self.held:
            raise DeletionError("FENCE_REQUIRED")

    def tx(self):
        return ImmediateTransaction(self.conn, self.fence)

    def verify(self, intent, proof):
        self.verifications.append((intent["operation_id"], proof))
        return self.verification_allowed

    def rows(self):
        return list(self.conn.execute("SELECT * FROM cars ORDER BY id"))

    def token(self):
        with self.tx() as tx:
            token = self.store.confirm(tx, car_id=8, actor_id=123)
            tx.commit()
        return token

    def plan(self, mode="PUBLIC_OR_RESIDUAL"):
        return {"mode": mode, "car_code": "UA-0002",
                "public_targets": ["https://www.uaart.com.ua/video/UA-0002.html"] if mode != "NEVER_PUBLISHED" else [],
                "list_surfaces": ["/home/Carix/site/index.html", "/home/Carix/video/catalog.html"],
                "media_targets": ["/home/Carix/private-media/exact-photo.jpg"]}

    def admit(self, token=None, plan=None):
        token = token or self.token()
        with self.tx() as tx:
            job = self.store.admit(tx, token=token, actor_id=123,
                                   plan=plan or self.plan(), backup_sha256="b" * 64)
            tx.commit()
        return job

    def proof(self, job):
        keys = ("operation_id", "car_id", "car_code", "vin", "snapshot_sha256", "expected_snapshot_sha256", "plan_sha256")
        proof = {k: job[k] for k in keys}
        plan = json.loads(job["plan"])
        proof.update({k: plan[k] for k in ("public_targets", "list_surfaces", "media_targets")})
        proof.update(all_absent=True, counters_match=True)
        return proof

    def test_install_is_explicit_additive_and_idempotent(self):
        with self.tx() as tx:
            install_additive_schema(tx, approved_application_schema_sha256=self.approved)
            tx.commit()
        self.assertEqual(self.original, self.rows())
        self.assertEqual(self.approved, application_schema_sha256(self.conn))

    def test_install_requires_approved_live_schema(self):
        with self.assertRaisesRegex(DeletionError, "NOT_APPROVED"), self.tx() as tx:
            install_additive_schema(tx, approved_application_schema_sha256="0" * 64)

    def test_atomic_admission_keeps_complete_original_snapshot(self):
        job = self.admit()
        self.assertEqual("PENDING", self.conn.execute("SELECT state FROM ua_delete_jobs").fetchone()[0])
        self.assertEqual(0, self.rows()[0][3])
        self.assertEqual(self.original[0][:3], self.rows()[0][:3])
        self.assertEqual(self.original[0][4:], self.rows()[0][4:])
        self.assertEqual(self.original[1], self.rows()[1])
        frozen = json.loads(job["snapshot"])
        self.assertEqual(["integer", "1"], frozen["published"])
        self.assertEqual(["blob", "AHByaXZhdGX/"], frozen["photos"])
        self.assertEqual(["null", None], frozen["note"])
        self.assertEqual("WDD1014", job["vin"])

    def test_interrupted_admission_rolls_back_intent_job_and_visibility(self):
        token = self.token()
        with self.assertRaises(KeyboardInterrupt):
            with self.tx() as tx:
                self.store.admit(tx, token=token, actor_id=123, plan=self.plan(), backup_sha256="b" * 64)
                raise KeyboardInterrupt("worker interrupted before commit")
        self.conn.close()
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.assertEqual(self.original, self.rows())
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM ua_delete_intents").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM ua_delete_jobs").fetchone()[0])
        self.assertIsNone(self.conn.execute("SELECT operation_id FROM ua_delete_confirmations").fetchone()[0])

    def test_failure_between_intent_and_job_is_atomic(self):
        token = self.token()
        self.conn.set_authorizer(lambda action, name, *_:
                                 sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and name == "ua_delete_jobs" else sqlite3.SQLITE_OK)
        try:
            with self.assertRaises(sqlite3.DatabaseError), self.tx() as tx:
                self.store.admit(tx, token=token, actor_id=123, plan=self.plan(), backup_sha256="b" * 64)
        finally:
            self.conn.set_authorizer(None)
        self.assertEqual(self.original, self.rows())
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM ua_delete_intents").fetchone()[0])

    def test_duplicate_click_and_two_confirmations_use_one_operation(self):
        first, second = self.token(), self.token()
        one = self.admit(first)
        self.assertEqual(one["operation_id"], self.admit(first)["operation_id"])
        self.assertEqual(one["operation_id"], self.admit(second)["operation_id"])
        self.assertEqual(1, self.conn.execute("SELECT count(*) FROM ua_delete_jobs").fetchone()[0])

    def test_old_confirmation_cannot_delete_reused_numeric_id(self):
        token = self.token()
        self.conn.execute("DELETE FROM cars WHERE id=8")
        self.conn.execute("INSERT INTO cars VALUES (8,'UA-0099','NEWVIN',1,12500,X'01','new identity')")
        self.conn.commit()
        before = self.rows()
        with self.assertRaisesRegex(DeletionError, "STALE_CALLBACK"):
            self.admit(token)
        self.assertEqual(before, self.rows())

    def test_confirmation_bound_to_actor(self):
        token = self.token()
        with self.assertRaisesRegex(DeletionError, "AUTHORIZED_CONFIRMATION"), self.tx() as tx:
            self.store.admit(tx, token=token, actor_id=999, plan=self.plan(), backup_sha256="b" * 64)

    def test_price_edit_before_admission_is_preserved(self):
        token = self.token()
        self.conn.execute("UPDATE cars SET price=8700 WHERE id=8")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "STALE_CALLBACK"):
            self.admit(token)
        self.assertEqual(8700, self.rows()[0][4])

    def test_price_edit_after_admission_refuses_finalization(self):
        job = self.admit()
        self.conn.execute("UPDATE cars SET price=8700 WHERE id=8")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "NEWER_CAR_IDENTITY"), self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
        self.assertEqual(8700, self.rows()[0][4])
        self.assertEqual("PENDING", self.conn.execute("SELECT state FROM ua_delete_jobs").fetchone()[0])

    def test_exact_proof_then_delete_and_complete_preserves_neighbor(self):
        job = self.admit()
        with self.tx() as tx:
            deleted = self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
            tx.commit()
        self.assertEqual("ROW_DELETED", deleted["state"])
        self.assertEqual([self.original[1]], self.rows())
        with self.tx() as tx:
            completed = self.store.complete(tx, operation_id=job["operation_id"], proof=self.proof(job))
            tx.commit()
        self.assertEqual("COMPLETE", completed["state"])
        self.assertEqual(2, len(self.verifications))

    def test_unbound_or_incomplete_proof_refused(self):
        job = self.admit()
        for key, value in [("operation_id", "c" * 64), ("public_targets", []), ("all_absent", False), ("counters_match", False)]:
            proof = dict(self.proof(job), **{key: value})
            with self.subTest(key=key), self.assertRaises(DeletionError), self.tx() as tx:
                self.store.finalize_row(tx, operation_id=job["operation_id"], proof=proof)
        self.assertEqual(2, len(self.rows()))

    def test_stale_external_evidence_does_not_delete_row(self):
        job = self.admit()
        self.verification_allowed = False
        with self.assertRaisesRegex(DeletionError, "FRESH_RETIREMENT"), self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
        self.assertEqual(2, len(self.rows()))

    def test_missing_row_without_original_job_never_admitted(self):
        token = self.token()
        self.conn.execute("DELETE FROM cars WHERE id=8")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "MISSING_NO_ORIGINAL_JOB"):
            self.admit(token)

    def test_missing_row_resumes_only_original_durable_job(self):
        token = self.token()
        job = self.admit(token)
        self.conn.execute("DELETE FROM cars WHERE id=8")
        self.conn.commit()
        self.assertEqual(job["operation_id"], self.admit(token)["operation_id"])
        with self.tx() as tx:
            result = self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
            tx.commit()
        self.assertEqual("ROW_DELETED", result["state"])
        self.assertEqual([self.original[1]], self.rows())

    def test_missing_job_is_not_recreated_from_intent(self):
        token = self.token()
        self.admit(token)
        self.conn.execute("DELETE FROM ua_delete_jobs")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "ORIGINAL_DURABLE"):
            self.admit(token)

    def test_never_published_plan_skips_public_targets_but_still_requires_proof(self):
        self.conn.execute("UPDATE cars SET published=0 WHERE id=8")
        self.conn.commit()
        job = self.admit(plan=self.plan("NEVER_PUBLISHED"))
        self.assertEqual([], json.loads(job["plan"])["public_targets"])
        with self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
            tx.commit()
        self.assertEqual(1, len(self.verifications))

    def test_published_row_cannot_use_draft_shortcut(self):
        with self.assertRaisesRegex(DeletionError, "NEVER_PUBLISHED_PLAN_CONFLICT"):
            self.admit(plan=self.plan("NEVER_PUBLISHED"))
        self.assertEqual(self.original, self.rows())

    def test_never_published_requires_explicit_nonempty_list_coverage(self):
        self.conn.execute("UPDATE cars SET published=0 WHERE id=8")
        self.conn.commit()
        before = self.rows()
        empty_coverage = dict(self.plan("NEVER_PUBLISHED"), list_surfaces=[])
        with self.assertRaisesRegex(DeletionError, "NEVER_PUBLISHED_PLAN_CONFLICT"):
            self.admit(plan=empty_coverage)
        self.assertEqual(before, self.rows())
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM ua_delete_jobs").fetchone()[0])
        self.assertEqual([], self.verifications)

    def test_tombstone_blocks_code_id_and_vin_reuse_but_not_neighbor(self):
        self.admit()
        for car_id, code, vin in [(8, "UA-0099", "new"), (999, "UA-0002", "new"), (999, "UA-0099", "wDd 1014")]:
            with self.subTest(identity=(car_id, code, vin)), self.assertRaisesRegex(DeletionError, "IDENTITY_RESERVED"), self.tx() as tx:
                self.store.require_writable(tx, car_id=car_id, car_code=code, vin=vin)
        with self.tx() as tx:
            self.store.require_writable(tx, car_id=9, car_code="UA-0003", vin="other0015")

    def test_reappeared_row_is_never_deleted_twice(self):
        token = self.token()
        job = self.admit(token)
        with self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
            tx.commit()
        self.conn.execute("INSERT INTO cars VALUES (8,'UA-0002','wdd-1014',0,8500,X'0070726976617465ff',NULL)")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "REAPPEARED"), self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
        with self.assertRaisesRegex(DeletionError, "REAPPEARED"):
            self.admit(token)
        self.assertEqual(2, len(self.rows()))

    def test_schema_drift_and_fence_absence_fail_closed(self):
        self.held = False
        with self.assertRaisesRegex(DeletionError, "FENCE_REQUIRED"):
            self.tx()
        self.held = True
        self.conn.execute("CREATE TABLE surprise (id INTEGER)")
        self.conn.commit()
        with self.assertRaisesRegex(DeletionError, "APPLICATION_SCHEMA_CHANGED"), self.tx() as tx:
            self.store.confirm(tx, car_id=8, actor_id=123)

    def test_admitted_schema_still_rejects_car_triggers(self):
        self.conn.execute("CREATE TRIGGER side_effect AFTER UPDATE ON cars BEGIN UPDATE cars SET note='changed' WHERE id=9; END")
        self.conn.commit()
        self.store.schema_sha = application_schema_sha256(self.conn)
        token = self.token()
        with self.assertRaisesRegex(DeletionError, "TRIGGERS_REQUIRE_SEPARATE_REVIEW"):
            self.admit(token)
        self.assertEqual(self.original, self.rows())

    def test_cascade_foreign_key_is_not_implicitly_authorized(self):
        self.conn.execute("CREATE TABLE related (id INTEGER, car_id INTEGER REFERENCES cars(id) ON DELETE CASCADE)")
        self.conn.commit()
        self.store.schema_sha = application_schema_sha256(self.conn)
        with self.assertRaisesRegex(DeletionError, "FK_SIDE_EFFECT"):
            self.admit()

    def test_finalize_interruption_rolls_back_row_and_job_state(self):
        job = self.admit()
        with self.assertRaises(KeyboardInterrupt), self.tx() as tx:
            self.store.finalize_row(tx, operation_id=job["operation_id"], proof=self.proof(job))
            raise KeyboardInterrupt("interrupted before commit")
        self.assertEqual(2, len(self.rows()))
        self.assertEqual("PENDING", self.conn.execute("SELECT state FROM ua_delete_jobs").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
