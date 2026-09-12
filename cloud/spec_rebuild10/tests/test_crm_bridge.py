"""Actual bridge + actual temporary SQLite store; no Telegram/network/site IO."""
from dataclasses import replace
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import tempfile
import unittest

from cloud.spec_rebuild10 import crm_bridge as module
from cloud.spec_rebuild10.crm_bridge import BridgeError, CrmBridge, RuntimeBindings, clear_editor_state, identity_from_crm
from cloud.spec_rebuild10.store import SpecStore
from cloud.spec_rebuild10.store import StoreError
from cloud.spec_rebuild10.prepare_crm_bridge import patch_sources


def row(uid="UA-0017", **changes):
    value = {"id": 37, "auto_number": uid, "brand": "Kia", "model": "K5",
             "year": "2017", "vin": "A" * 17, "fuel": "LPI",
             "engine_cc": "2000", "published": 0}
    value.update(changes)
    return value


def gate(request):
    return {**request, "plan_id": "SYNTHETIC-ONLY", "gate_b": "PASS", "route": "PASS",
            "external_writers": "PASS", "owner_action": "PASS", "fresh": "PASS"}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SpecStore(str(Path(self.temp.name) / "spec.sqlite"))
        self.bridge = CrmBridge(self.store)
        self.before_runtime = module._runtime
        self.before_factory = module._runtime_factory
        module._runtime = None
        module._runtime_factory = None

    def tearDown(self):
        module._runtime = self.before_runtime
        module._runtime_factory = self.before_factory
        self.store.close()
        self.temp.cleanup()

    def seed(self):
        self.bridge.saved(row())
        self.store.set_manual_fact("UA-0017", {"key": "length", "value": "4855", "unit": "mm"})

    def receipt(self, ticket):
        return {"receipt_id": "synthetic-readback-1", "route_id": "synthetic-route",
                "uid": ticket.uid, "revision": ticket.revision,
                "action": ticket.action, "plan_id": ticket.plan_id,
                "identity_hash": ticket.identity_hash, "facts_digest": ticket.facts_digest,
                "status": "PASS", "specification_visible": True, "single_vin": True,
                "shell_preserved": True, "verified_at": "2026-09-09T00:00:00Z",
                "page_url": "https://www.uaart.com.ua/video/UA-0017.html"}

    def test_saved_rows_queue_once_without_publication(self):
        for _ in range(3):
            self.bridge.saved(row(published=1))
        self.assertEqual(len(self.store.get_jobs("UA-0017")), 1)
        self.assertFalse(self.store.get_vehicle("UA-0017")["published"])

    def test_price_photos_do_not_reidentify(self):
        self.seed()
        self.bridge.saved(row(price_total=18000, photos='["new-photo"]', published=1))
        self.assertEqual(self.store.get_vehicle("UA-0017")["revision"], 1)
        self.assertEqual(len(self.store.get_jobs("UA-0017")), 1)
        self.assertEqual(len(self.store.get_facts("UA-0017")), 1)

    def test_duplicate_uids_do_not_partially_import_from_scan(self):
        result = self.bridge.reconcile_saved_rows([row(id=37), row(id=38, year="2018")])
        self.assertEqual(result["tracked"], [])
        self.assertEqual(len(result["needs_input"]), 2)
        self.assertEqual(self.store.get_jobs(), [])

    def test_identity_change_isolates_old_facts(self):
        self.seed()
        self.bridge.saved(row(year="2018"))
        self.assertEqual(self.store.get_vehicle("UA-0017")["revision"], 2)
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        self.assertEqual(self.store.get_jobs("UA-0017")[0]["state"], "cancelled")

    def test_model_identity_normalization(self):
        first = identity_from_crm(row())[1]
        second = identity_from_crm(row(brand=" KIA ", engine_cc="2.0", fuel="газ"))[1]
        self.assertEqual(first, second)
        with self.assertRaises(BridgeError):
            identity_from_crm(row(auto_number="", id=17))

    def test_cancel_removes_stale_editor_only(self):
        state = {"ua099_spec_edit": {"key": "length"}, "car_wait": {"field": "year"}, "auth": 1}
        self.assertEqual(clear_editor_state(state), 2)
        self.assertEqual(state, {"auth": 1})
        self.assertEqual(clear_editor_state(state), 0)

    def test_no_initial_publication_without_facts_or_owner(self):
        self.bridge.saved(row())
        with self.assertRaisesRegex(BridgeError, "ACCEPTED_SPEC_REQUIRED"):
            self.bridge.prepare("publish", row(), 1, gate)
        self.seed()
        with self.assertRaisesRegex(BridgeError, "OWNER_ACTION_REQUIRED"):
            self.bridge.prepare("publish", row(), 0, gate)

    def test_gate_and_scope_required(self):
        self.seed()
        for key in ("gate_b", "route", "external_writers", "owner_action", "fresh"):
            with self.assertRaisesRegex(BridgeError, "READINESS_REQUIRED"):
                self.bridge.prepare("publish", row(), 1, lambda r: {**gate(r), key: "FAIL"})
        with self.assertRaisesRegex(BridgeError, "READINESS_SCOPE_MISMATCH"):
            self.bridge.prepare("publish", row(), 1, lambda r: {**gate(r), "uid": "UA-0018"})

    def test_public_flag_requires_actual_readback_verifier(self):
        self.seed()
        ticket = self.bridge.prepare("publish", row(), 1, gate)
        with self.assertRaisesRegex(BridgeError, "ACTUAL_SITE_READBACK_REQUIRED"):
            self.bridge.observed(ticket, self.receipt(ticket), lambda *args: False)
        self.assertFalse(self.store.get_vehicle("UA-0017")["published"])
        self.bridge.observed(ticket, self.receipt(ticket), lambda *args: True)
        self.assertTrue(self.store.get_vehicle("UA-0017")["published"])
        self.assertIsNotNone(self.store.get_publication_snapshot("UA-0017"))
        self.assertIn("стан сайту: перевірено", self.bridge.summary(row()))

    def test_fact_change_during_publish_cannot_be_marked_success(self):
        self.seed()
        ticket = self.bridge.prepare("publish", row(), 1, gate)
        self.store.set_manual_fact("UA-0017", {"key": "length", "value": "4900"})
        with self.assertRaisesRegex(BridgeError, "SPEC_CHANGED_DURING_OPERATION"):
            self.bridge.observed(ticket, self.receipt(ticket), lambda *args: True)

    def test_hide_then_delete_preserve_archived_facts(self):
        self.seed()
        ticket = self.bridge.prepare("hide", row(), 1, gate)
        self.bridge.observed(ticket, self.receipt(ticket), lambda *args: True)
        self.assertEqual(len(self.store.get_facts("UA-0017")), 1)
        ticket = self.bridge.prepare("delete", row(), 1, gate)
        self.bridge.observed(ticket, {**self.receipt(ticket), "receipt_id": "synthetic-delete-2"}, lambda *args: True)
        self.assertTrue(self.store.get_vehicle("UA-0017")["tombstoned"])
        count = self.store.db.execute("SELECT count(*) FROM facts WHERE uid='UA-0017'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_old_delete_receipt_cannot_delete_identity_changed_during_readback(self):
        self.seed()
        ticket = self.bridge.prepare("delete", row(), 1, gate)
        def concurrent_change(_ticket, _receipt):
            with SpecStore(str(Path(self.temp.name) / "spec.sqlite")) as concurrent:
                CrmBridge(concurrent).saved(row(year="2018"))
            return True
        with self.assertRaises(StoreError):
            self.bridge.observed(ticket, self.receipt(ticket), concurrent_change)
        latest = self.store.get_vehicle("UA-0017")
        self.assertEqual(latest["revision"], 2)
        self.assertFalse(latest["tombstoned"])
        self.assertEqual(self.store.get_jobs("UA-0017")[-1]["state"], "ready")

    def test_unconfigured_runtime_does_not_start_or_publish(self):
        self.assertFalse(module.start_configured_worker()["started"])
        self.assertFalse(module.runtime_transition("publish", row(), 1)[0])
        self.assertEqual(module.saved_after_commit(row())["status"], "RUNTIME_UNCONFIGURED")
        with self.assertRaisesRegex(BridgeError, "AUTHORIZED_FULL_CARD_MANIFEST_REQUIRED"):
            module.validate_runtime_page_change("before", "after", "UA-0017", [])

    def test_public_composer_reads_new_store_and_checks_current_identity(self):
        self.seed()
        current = row()
        bindings = RuntimeBindings(self.bridge, gate, lambda *args: None, lambda *args: False,
                                   lambda: {"started": False}, lambda uid: current)
        module.configure_runtime(bindings)
        self.assertEqual(module.runtime_public_facts("UA-0017")[0]["value"], "4855")
        current["year"] = "2018"
        with self.assertRaisesRegex(BridgeError, "CRM_SPEC_IDENTITY_MISMATCH"):
            module.runtime_public_facts("UA-0017")

    def test_source_preparer_rejects_unpinned_runtime(self):
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_RUNTIME_SOURCE"):
            patch_sources({})

    def test_factory_owns_connection_in_callback_thread(self):
        path = str(Path(self.temp.name) / "threaded.sqlite")
        module.configure_runtime_factory(path, read_current_row=lambda uid: row(),
            verify_readiness=gate, execute_lifecycle=lambda *args: {},
            verify_readback=lambda *args: False, start_worker=lambda: {"started": False})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: module.saved_after_commit(row()), range(4)))
        self.assertTrue(all(result["status"] == "TRACKED" for result in results))
        with SpecStore(path) as store:
            self.assertEqual(len(store.get_jobs("UA-0017")), 1)

    def test_delayed_save_tracks_current_crm_identity(self):
        self.bridge.saved(row(year="2018"))
        bindings = RuntimeBindings(self.bridge, gate, lambda *args: None, lambda *args: False,
                                   lambda: {"started": False}, lambda uid: row(year="2018"))
        module.configure_runtime(bindings)
        module.saved_after_commit(row(year="2017"))
        self.assertEqual(self.store.get_vehicle("UA-0017")["revision"], 1)
        self.assertEqual(self.store.get_vehicle("UA-0017")["identity"]["year"], 2018)

    def test_synthetic_sqlite_html_edit_hide_republish_delete_cycle(self):
        from cloud.spec_rebuild10 import render
        from cloud.spec_rebuild10.tests.test_render import page
        uid = "UA-9999"
        crm_path = Path(self.temp.name) / "crm.sqlite"
        page_path = Path(self.temp.name) / (uid + ".html")
        store_path = str(Path(self.temp.name) / "cycle-spec.sqlite")
        with sqlite3.connect(crm_path) as db:
            db.execute("CREATE TABLE cars(uid TEXT PRIMARY KEY, payload TEXT)")
            db.execute("INSERT INTO cars VALUES(?,?)", (uid, json.dumps(row(uid, price_total=10000))))
        def current(_uid):
            with sqlite3.connect(crm_path) as db:
                result = db.execute("SELECT payload FROM cars WHERE uid=?", (_uid,)).fetchone()
            return json.loads(result[0]) if result else None
        def save_row(value):
            with sqlite3.connect(crm_path) as db:
                db.execute("UPDATE cars SET payload=? WHERE uid=?", (json.dumps(value), uid))
        def template(value):
            return page(False).replace("Original description", "Price " + str(value["price_total"]))
        operations = []
        def execute(ticket, submitted):
            operations.append(ticket.action)
            value = current(uid)
            if ticket.action == "publish":
                facts = module.runtime_public_facts(uid)
                candidate = render.compose_page(template(value), uid, facts)
                if page_path.exists() and page_path.read_text() != candidate:
                    module.validate_runtime_page_change(page_path.read_text(), candidate, uid, facts)
                page_path.write_text(candidate)
                value["published"] = 1
                save_row(value)
                receipt = {"receipt_id": "synthetic-%d" % len(operations), "route_id": "local-fixture",
                    "uid": uid, "revision": ticket.revision, "identity_hash": ticket.identity_hash,
                    "action": ticket.action, "plan_id": ticket.plan_id,
                    "facts_digest": ticket.facts_digest, "status": "PASS", "specification_visible": True,
                    "single_vin": True, "shell_preserved": True, "verified_at": "2026-09-09T00:00:00Z",
                    "page_url": "https://www.uaart.com.ua/video/UA-9999.html",
                    "html_sha256": hashlib.sha256(page_path.read_bytes()).hexdigest()}
            else:
                page_path.unlink()
                if ticket.action == "delete":
                    with sqlite3.connect(crm_path) as db:
                        db.execute("DELETE FROM cars WHERE uid=?", (uid,))
                else:
                    value["published"] = 0
                    save_row(value)
                receipt = {"receipt_id": "synthetic-%d" % len(operations), "route_id": "local-fixture",
                    "uid": uid, "action": ticket.action, "plan_id": ticket.plan_id,
                    "revision": ticket.revision, "identity_hash": ticket.identity_hash,
                    "facts_digest": ticket.facts_digest, "status": "PASS",
                    "verified_at": "2026-09-09T00:00:00Z", "absent": True}
            return {"ok": True, "detail": "Synthetic local operation", "receipt": receipt}
        def readback(ticket, receipt):
            if ticket.action == "publish":
                if not page_path.is_file() or hashlib.sha256(page_path.read_bytes()).hexdigest() != receipt["html_sha256"]:
                    return False
                with SpecStore(store_path) as store:
                    facts = store.get_facts(uid)
                render.validate_page(page_path.read_text(), uid, facts, previous=template(current(uid)))
                return current(uid)["published"] == 1
            return not page_path.exists() and (current(uid) is None if ticket.action == "delete" else current(uid)["published"] == 0)
        module.configure_runtime_factory(store_path, read_current_row=current, verify_readiness=gate,
            execute_lifecycle=execute, verify_readback=readback, start_worker=lambda: {"started": False},
            verify_page_change=lambda request: {**request, "authorization": "PASS"})
        module.saved_after_commit(current(uid))
        with SpecStore(store_path) as store:
            store.set_manual_fact(uid, {"key": "length", "value": "4900", "unit": "mm"})
        self.assertFalse(page_path.exists())
        self.assertTrue(module.runtime_transition("publish", current(uid), 1)[0])
        changed = current(uid)
        changed["price_total"] = 11000
        save_row(changed)
        module.saved_after_commit(changed)
        self.assertTrue(module.runtime_transition("publish", current(uid), 1)[0])
        self.assertIn("Price 11000", page_path.read_text())
        self.assertEqual(page_path.read_text().count("A" * 17), 1)
        self.assertTrue(module.runtime_transition("hide", current(uid), 1)[0])
        self.assertFalse(page_path.exists())
        self.assertTrue(module.runtime_transition("publish", current(uid), 1)[0])
        self.assertTrue(module.runtime_transition("delete", current(uid), 1)[0])
        self.assertIsNone(current(uid))
        self.assertFalse(page_path.exists())
        with SpecStore(store_path) as store:
            self.assertTrue(store.get_vehicle(uid)["tombstoned"])
            self.assertEqual(store.db.execute("SELECT count(*) FROM facts").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
