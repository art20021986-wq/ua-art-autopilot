"""Exercise actual patched guard functions against independent SQLite clients."""
import ast
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import outbox as O
from patch_guard import patch_source


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class GuardFenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = pathlib.Path(os.environ.get("TASK088_PUBLISH_GUARD_SOURCE", str(
            pathlib.Path(__file__).resolve().parents[2] / "live_source_private" / "publish_transaction_guard.py")))
        cls.source = source_path.read_text()
        cls.candidate = patch_source(cls.source)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.path = self.root / "crm.db"
        self.db = self.connect()
        self.db.executescript("""
            CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER,
                              price_uah INTEGER, price_georgia INTEGER);
            INSERT INTO cars VALUES(10,'UA-0010',1,10000,8000);
            INSERT INTO cars VALUES(29,'UA-0029',1,20000,NULL);
        """)
        self.db.execute("BEGIN IMMEDIATE")
        O.install(self.db)
        self.db.commit()
        self.stage = []
        self.before_switch = None
        self.file = self.root / "catalog.html"
        self.file.write_text("original catalog")
        owner = self

        class Snapshot:
            def __init__(self, codes):
                owner.stage.append("snapshot")
                self.root = owner.root / "backup"
                self.before = owner.file.read_bytes()

            def restore(self):
                owner.stage.append("restore")
                owner.file.write_bytes(self.before)
                return {"status": "RESTORED"}

        names = {"_task088_price_quiescence", "_publish_locked", "rebuild_catalog",
                 "publish_batch", "publish_one", "_exclusive_lock", "_code", "_call_base"}
        tree = ast.parse(self.candidate)
        nodes = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "__future__"]
        nodes += [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                  and (node.name in names or node.name == "PublishError")]
        self.ns = dict(contextlib=contextlib, fcntl=fcntl, time=time, sqlite3=sqlite3,
                       DB=self.path, LOCK=self.root / "publish.lock", WAIT_SECONDS=1,
                       ID_RE=re.compile(r"^UA-[0-9]{4,}$"), Snapshot=Snapshot,
                       CONTRACT_ID="TEST_EXISTING_PUBLICATION_CONTRACT", _row_map=self.row_map,
                       _protected_pages=lambda codes: {}, _stage_diags=self.stage_diags,
                       _build_catalog=self.build_catalog, _validate_catalog=lambda source, rows: {},
                       _install_catalog=self.install_catalog, _verify_bundle=lambda codes: {"status": "PASS"},
                       _append_log=lambda message: None)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<actual-patched-guard>", "exec"), self.ns)
        self.module_patch = patch.dict(sys.modules, {"uaart_price_sync_outbox": O})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        self.addCleanup(conn.close)
        return conn

    def row_map(self):
        reader = self.connect()
        reader.row_factory = sqlite3.Row
        rows = [dict(row) for row in reader.execute("SELECT * FROM cars WHERE published=1 ORDER BY id")]
        reader.close()
        return {row["auto_number"]: row for row in rows}, digest(repr(rows))

    def stage_diags(self, codes):
        self.stage.append("diagnostics")
        return {}

    def build_catalog(self):
        rows, _ = self.row_map()
        self.stage.append("render")
        return repr(rows), list(rows.values())

    def install_catalog(self, source, code):
        if self.before_switch:
            self.before_switch()
        self.stage.append("switch")
        self.file.write_text(source)
        return {"status": "PASS"}

    def base(self, code, proba=False):
        self.stage.append("base")
        return True, "tested base publisher"

    def enqueue(self, key="edit1", ge="8500.00"):
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("UPDATE cars SET price_georgia=? WHERE id=10", (int(ge.split(".")[0]),))
        result = O.enqueue(self.db, event_key=digest(key), car_id=10, ukraine_usd="10000.00",
                           georgia_usd=ge, now_ms=1000)
        self.db.commit()
        return result

    def claim(self):
        self.db.execute("BEGIN IMMEDIATE")
        O.claim(self.db, event_key=digest("edit1"), nonce=digest("claim1"), now_ms=1100)
        self.db.commit()

    def published(self):
        self.enqueue()
        self.claim()
        self.db.execute("BEGIN IMMEDIATE")
        O.record_verified_publication(self.db, event_key=digest("edit1"), nonce=digest("claim1"),
                                      receipt_sha256=digest("fixture receipt"), now_ms=1200)
        self.db.commit()

    def submit_v5(self, key="v5_edit1", value="8700.00", field="price_georgia"):
        self.db.execute("BEGIN IMMEDIATE")
        event = O.submit(self.db, event_key=digest(key), car_id=10, field=field,
            value=value, actor_id=700, chat_id=700, now_ms=2000,
            provenance={"source": "SYNTHETIC_TEST"})
        self.db.commit()
        return event

    def advance_v5(self, event, stop="COMPLETED"):
        # Fixture executes the actual durable state transitions; it proves
        # guard behavior only, never Production completion.
        key = event["event_key"]
        self.db.execute("BEGIN IMMEDIATE")
        event = O.claim_operation(self.db, event_key=key, nonce=digest("claim_" + key), now_ms=2100)
        if stop == "CLAIMED":
            self.db.commit()
            return event
        before = self.row_map()[0]["UA-0010"]
        stored = None if event["value"] is None else int(event["value"].split(".")[0])
        self.db.execute("UPDATE cars SET " + event["field"] + "=? WHERE id=10", (stored,))
        cursor = self.db.execute("SELECT * FROM cars WHERE id=10")
        after = dict(zip((item[0] for item in cursor.description), cursor.fetchone()))
        ua = "%d.00" % after["price_uah"]
        ge = None if after["price_georgia"] is None else "%d.00" % after["price_georgia"]
        event = O.transition_operation(self.db,event_key=key,nonce=event["claim_nonce"],
            expected_state="CLAIMED",new_state="DB_COMMITTED",now_ms=2200,
            ukraine_usd=ua,georgia_usd=ge,before_json=O.v5_json(before),after_json=O.v5_json(after),db_committed_ms=2200)
        O.audit_operation(self.db,key,"DB_COMMITTED",{"before":before,"after":after},2200)
        O.audit_operation(self.db,key,"DB_READBACK",{"separate_connection":True,"ua":ua,"ge":ge},2210)
        if stop == "DB_COMMITTED":
            self.db.commit()
            return event
        event = O.transition_operation(self.db,event_key=key,nonce=event["claim_nonce"],
            expected_state="DB_COMMITTED",new_state="SITE_PUBLISHED",now_ms=2300)
        if stop == "SITE_PUBLISHED":
            self.db.commit()
            return event
        proof = dict(operation_id=key,claim_nonce=event["claim_nonce"],car_id=10,car_code="UA-0010",vin="",
            actor_id=700,chat_id=700,market=event["field"],new_value=event["value"],ua=ua,ge=ge,
            db_readback="PASS",protected_data="PASS",verification="PASS",verified_ms=2400)
        receipt = digest(O.v5_json(proof))
        event = O.transition_operation(self.db,event_key=key,nonce=event["claim_nonce"],
            expected_state="SITE_PUBLISHED",new_state="VERIFIED",now_ms=2400,
            verified_ms=2400,receipt_sha256=receipt)
        O.audit_operation(self.db,key,"VERIFIED",proof,2400)
        if stop == "VERIFIED":
            self.db.commit()
            return event
        event = O.transition_operation(self.db,event_key=key,nonce=event["claim_nonce"],
            expected_state="VERIFIED",new_state="COMPLETED",now_ms=2500,completed_ms=2500)
        O.audit_operation(self.db,key,"COMPLETED",{"receipt_sha256":receipt,"operator_chat_id":700},2500)
        self.db.commit()
        return event

    def assert_blocked(self, reason="UNVERIFIED_PRICE_INTENTS"):
        for call in (lambda: self.ns["publish_one"](self.base, "UA-0029"), self.ns["rebuild_catalog"]):
            self.stage.clear()
            with self.assertRaisesRegex(self.ns["PublishError"], reason):
                call()
            self.assertEqual(self.stage, [])
            self.assertEqual(self.file.read_text(), "original catalog")

    def test_source_is_pinned_and_other_guard_functions_unchanged(self):
        for changed in (self.source + "\n", self.candidate, self.source.replace("WAIT_SECONDS = 90", "WAIT_SECONDS = 91")):
            with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
                patch_source(changed)
        old = [node for node in ast.parse(self.source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        new = [node for node in ast.parse(self.candidate).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
               and node.name != "_task088_price_quiescence"]
        self.assertEqual(len(old), len(new))
        for before, after in zip(old, new):
            self.assertEqual(before.name, after.name)
            if before.name not in {"_publish_locked", "rebuild_catalog"}:
                self.assertEqual(ast.dump(before), ast.dump(after))

    def test_pending_other_car_blocks_before_backup_render_or_write(self):
        self.enqueue()
        self.assert_blocked()

    def test_claimed_other_car_blocks_without_releasing_nonce(self):
        self.enqueue()
        self.claim()
        self.assert_blocked()
        self.assertEqual(O.get(self.db, digest("edit1"))["claim_nonce"], digest("claim1"))

    def test_stopped_other_car_blocks_without_erasing_stop(self):
        self.enqueue()
        self.claim()
        self.db.execute("BEGIN IMMEDIATE")
        O.stop(self.db, event_key=digest("edit1"), nonce=digest("claim1"), reason="UNKNOWN_WRITE", now_ms=1200)
        self.db.commit()
        self.assert_blocked()
        self.assertEqual(O.get(self.db, digest("edit1"))["state"], "STOPPED")

    def test_latest_reconciled_does_not_mean_its_crm_price_was_published(self):
        self.enqueue()
        self.claim()
        self.db.execute("BEGIN IMMEDIATE")
        evidence = O.RecoveryEvidence(digest("recovery"), digest("edit1"), digest("claim1"), 1,
            "NO_EFFECT", "CONFIRMED_NO_WRITE", True, True, True, False, digest("cause fixed"),
            digest("preflight"), 1200, 1220, digest("original card"), digest("original catalog"), digest("proof"))
        O.reconcile_verified(self.db, event_key=digest("edit1"), nonce=digest("claim1"), evidence=evidence, now_ms=1250)
        self.db.commit()
        self.assert_blocked()

    def test_normal_manual_first_publish_remains_allowed_when_no_unresolved_prices(self):
        ok, message = self.ns["publish_one"](self.base, "UA-0029")
        self.assertTrue(ok, message)
        self.assertIn("base", self.stage)
        self.assertIn("UA-0029", self.file.read_text())

    def test_verified_price_event_allows_ordinary_publish_and_rebuild(self):
        self.published()
        self.assertTrue(self.ns["publish_one"](self.base, "UA-0029")[0])
        self.assertTrue(self.ns["rebuild_catalog"]()[0])

    def test_untracked_crm_price_edit_after_receipt_is_not_published(self):
        self.published()
        self.db.execute("UPDATE cars SET price_georgia=9999 WHERE id=10")
        self.assert_blocked("UNTRACKED_CRM_PRICE_CHANGE")

    def test_crm_writer_cannot_commit_between_preflight_and_catalog_switch(self):
        competing = self.connect()
        observations = []

        def concurrent_edit():
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                competing.execute("BEGIN IMMEDIATE")
            observations.append(competing.execute("SELECT price_georgia FROM cars WHERE id=10").fetchone()[0])
            self.assertFalse(competing.in_transaction)

        self.before_switch = concurrent_edit
        self.assertTrue(self.ns["publish_one"](self.base, "UA-0029")[0])
        self.assertTrue(self.ns["rebuild_catalog"]()[0])
        self.assertEqual(observations, [8000, 8000])
        competing.execute("BEGIN IMMEDIATE")
        competing.execute("UPDATE cars SET price_georgia=8500 WHERE id=10")
        O.enqueue(competing, event_key=digest("after publication"), car_id=10, ukraine_usd="10000.00",
                  georgia_usd="8500.00", now_ms=1500)
        competing.commit()
        self.assertEqual(O.get(competing, digest("after publication"))["state"], "PENDING")

    def test_active_crm_transaction_fails_before_any_publication_work(self):
        self.db.execute("BEGIN IMMEDIATE")
        self.assert_blocked("FENCE_UNAVAILABLE")
        self.db.rollback()
        self.assertTrue(self.ns["publish_one"](self.base, "UA-0029")[0])

    def test_unknown_missing_outbox_or_database_fails_closed(self):
        self.db.execute(f"DROP TABLE {O.RECOVERY_TABLE}")
        self.db.execute(f"DROP TABLE {O.TABLE}")
        self.assert_blocked("OUTBOX_SCHEMA_REQUIRED")
        self.db.execute(f"CREATE TABLE {O.TABLE} (event_key TEXT)")
        self.assert_blocked("OUTBOX_SCHEMA_REQUIRED")
        self.ns["DB"] = self.root / "missing.sqlite"
        self.assert_blocked("DATABASE_FILE_REQUIRED")
        self.assertFalse(self.ns["DB"].exists())

    def test_failure_rolls_back_publication_and_releases_database_fence(self):
        def fail_after_write(source, code):
            self.file.write_text("partial candidate")
            raise RuntimeError("injected publication failure")

        self.ns["_install_catalog"] = fail_after_write
        ok, message = self.ns["publish_one"](self.base, "UA-0029")
        self.assertFalse(ok)
        self.assertIn("injected publication failure", message)
        self.assertEqual(self.file.read_text(), "original catalog")
        self.assertIn("restore", self.stage)
        self.db.execute("BEGIN IMMEDIATE")
        self.db.rollback()

    def test_v5_accepted_intent_blocks_before_any_price_mutation_or_generation(self):
        self.submit_v5()
        self.assertEqual(self.db.execute("SELECT price_georgia FROM cars WHERE id=10").fetchone()[0],8000)
        self.assert_blocked("V5_UNVERIFIED_PRICE_INTENTS")

    def test_every_unfinished_v5_checkpoint_blocks_whole_generator(self):
        event = self.submit_v5()
        event = self.advance_v5(event,"CLAIMED")
        self.assert_blocked("V5_UNVERIFIED_PRICE_INTENTS")
        # Each persisted checkpoint is still unfinished; no last-known green
        # event may authorize the current whole-site publisher.
        for state in ("DB_COMMITTED","SITE_PUBLISHED","VERIFIED"):
            self.db.execute(f"UPDATE {O.V5_TABLE} SET state=? WHERE event_key=?", (state,event["event_key"]))
            self.assert_blocked("V5_UNVERIFIED_PRICE_INTENTS")

    def test_v5_completed_current_pair_allows_publish_and_rebuild(self):
        event = self.advance_v5(self.submit_v5())
        self.assertEqual(event["state"],"COMPLETED")
        self.assertTrue(self.ns["publish_one"](self.base,"UA-0029")[0])
        self.assertTrue(self.ns["rebuild_catalog"]()[0])

    def test_new_v5_queued_intent_blocks_even_after_completed_event(self):
        self.advance_v5(self.submit_v5())
        self.submit_v5("v5_edit2", "8800.00")
        self.assert_blocked("V5_UNVERIFIED_PRICE_INTENTS")

    def test_latest_v5_pair_supersedes_old_published_v1_snapshot(self):
        self.published()
        self.advance_v5(self.submit_v5())
        self.assertTrue(self.ns["rebuild_catalog"]()[0])

    def test_v5_does_not_hide_uncertain_legacy_intents(self):
        self.enqueue()
        self.advance_v5(self.submit_v5())
        self.assert_blocked("UNVERIFIED_PRICE_INTENTS")

    def test_v5_receipt_does_not_authorize_untracked_other_market_price(self):
        self.advance_v5(self.submit_v5())
        self.db.execute("UPDATE cars SET price_uah=11000 WHERE id=10")
        self.assert_blocked("V5_UNTRACKED_CRM_PRICE_CHANGE")

    def test_legitimate_later_nonprice_change_does_not_invalidate_current_prices(self):
        self.advance_v5(self.submit_v5())
        self.db.execute("ALTER TABLE cars ADD COLUMN status TEXT")
        self.db.execute("UPDATE cars SET status='kyiv' WHERE id=10")
        self.assertTrue(self.ns["rebuild_catalog"]()[0])

    def test_v5_completed_label_without_actual_completion_proof_blocks(self):
        event = self.submit_v5()
        self.db.execute(f"UPDATE {O.V5_TABLE} SET state='COMPLETED',claim_nonce=?,ukraine_usd='10000.00',georgia_usd='8000.00' WHERE event_key=?",
                        (digest("fake"), event["event_key"]))
        self.assert_blocked("V5_SELECTED_PRICE_SNAPSHOT_MISMATCH")

    def test_v5_corrupted_receipt_checksum_blocks(self):
        event = self.advance_v5(self.submit_v5())
        self.db.execute(f"UPDATE {O.V5_TABLE} SET receipt_sha256=? WHERE event_key=?",(digest("wrong"),event["event_key"]))
        self.assert_blocked("V5_COMPLETION_PROOF_MISMATCH")

    def test_v5_immutable_audit_trigger_and_schema_are_required(self):
        self.db.execute(f"DROP TRIGGER {O.V5_AUDIT}_no_update")
        self.assert_blocked("V5_PRICE_PROTECTION_TRIGGER_REQUIRED")

    def test_v5_nullable_ge_completed_snapshot_is_supported(self):
        self.advance_v5(self.submit_v5(value=None))
        self.assertTrue(self.ns["rebuild_catalog"]()[0])


if __name__ == "__main__":
    unittest.main()
