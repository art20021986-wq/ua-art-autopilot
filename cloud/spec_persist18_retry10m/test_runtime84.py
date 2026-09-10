"""Isolated actual-module integration checks; no live files or HTTP requests."""
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "task_111_vin_spec_10src")]
import vin_spec_service as legacy


def load_test_renderer():
    override = os.environ.get("UA_ART_SPEC_TEST_RENDERER")
    path = pathlib.Path(override) if override else HERE.parent / "task_099_site_crm_repair/ua_additional_spec.py"
    if not path.is_file():
        return None
    source = path.read_text(encoding="utf-8")
    if not override:
        # Compose only tracked public components. The integration tests need
        # separate CRM/spec connections, as provided by the public UA110 patch.
        patch_path = HERE.parent / "task_110_vin_spec_3src/integration_patcher.py"
        if not patch_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("_issue84_public_sidecar_patcher", patch_path)
        patcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patcher)
        source = patcher.patch_additional_spec(source)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("ua_additional_spec", loader=None))
    exec(compile(source, str(path), "exec"), module.__dict__)
    sys.modules["ua_additional_spec"] = module
    return module


renderer = load_test_renderer()
import ua_spec84_runtime as runtime
import spec84_collector as collector
from spec_retry84 import blank_outcomes

VIN = "WAUZZZ4G3GN081840"
FACT = {"field_key": "seats_count", "display_value": "5", "label_ru": "Количество мест",
        "category": "capacity", "unit": "", "source_domains": ["auto-data.net"],
        "source_urls": ["https://www.auto-data.net/en/example-audi"], "confidence": 0.9}
PAGE = b"<!doctype html><html><head><title>Kept</title></head><body><main><p>PRICE AND MEDIA STAY</p></main></body></html>"


def collected(facts=None):
    return {"facts": facts or [], "sources": blank_outcomes(runtime.DOMAIN_TO_SOURCE.values(), "EMPTY"),
            "collection_error": None, "elapsed_seconds": 0.01}


@unittest.skipIf(renderer is None, "Renderer unavailable; set UA_ART_SPEC_TEST_RENDERER to a local renderer file")
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.main = self.root / "crm.db"
        self.spec = self.root / "spec.db"
        with sqlite3.connect(self.main) as db:
            db.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,brand TEXT,model TEXT,year TEXT,engine TEXT)")
            db.execute("INSERT INTO cars VALUES(1,'UA-0017',?,1,'Audi','A6','2015','3.0 diesel')", (VIN,))
        for lock in runtime.WRITER_LOCKS:
            (self.root / lock).touch()
        for folder in ("video", "site"):
            (self.root / folder).mkdir()
            (self.root / folder / "UA-0017.html").write_bytes(PAGE)
        replacements = [(runtime, "ROOT", self.root), (runtime, "QUEUE_DB", self.root / "queue.db"),
                        (runtime, "_queue", None), (legacy, "MAIN_DB", self.main), (legacy, "SPEC_DB", self.spec),
                        (renderer, "DB_PATH", self.main), (renderer, "_UA110_MAIN_DB_PATH", self.main),
                        (renderer, "_UA110_SPEC_DB_PATH", self.spec)]
        for obj, attr, value in replacements:
            patch = mock.patch.object(obj, attr, value)
            patch.start()
            self.addCleanup(patch.stop)
        runtime._stop.clear()
        legacy.ensure_schema()
        with legacy.connect_spec(False) as db:
            db.execute("""INSERT INTO vin_spec_jobs(car_uid,vin,policy_version,status,requested_at)
                VALUES('UA-0017',?,'legacy','READY','2026-09-10T00:00:00Z')""", (VIN,))
            db.commit()
        self.before_main = hashlib.sha256(self.main.read_bytes()).hexdigest()

    def worker(self):
        queue = runtime._init_queue()
        worker = runtime._IntegratedRuntime(queue, read_card=runtime._card,
            collector="spec84_collector:collect_scheduled", connected_sources=runtime.DOMAIN_TO_SOURCE.values(),
            commit_guard=runtime._writer_guard, commit=lambda *args: None)
        self.addCleanup(worker.close)
        return worker

    def fact_count(self):
        with legacy.connect_spec(True) as db:
            return db.execute("SELECT count(*) FROM additional_specification").fetchone()[0]

    def test_success_atomic_fact_slot_receipt_and_two_narrow_pages(self):
        self.assertTrue(runtime.retry_card("UA-0017"))
        worker = self.worker()
        job = worker.queue.claim()
        with mock.patch.object(runtime, "collect_bounded", return_value=collected([FACT])):
            self.assertEqual(worker.execute(job), "DONE_SYNC_PENDING")
        self.assertEqual(self.fact_count(), 1)
        report = worker.queue.report()
        self.assertEqual(report["slots"][0]["state"], "DONE")
        self.assertEqual(len(report["sources"]), 10)
        runtime._sync_pending()
        for folder in ("video", "site"):
            text = (self.root / folder / "UA-0017.html").read_text()
            self.assertIn("Количество мест", text)
            self.assertIn("PRICE AND MEDIA STAY", text)
            self.assertEqual(text.count("data-ua-additional-spec='1'"), 1)
        self.assertEqual(hashlib.sha256(self.main.read_bytes()).hexdigest(), self.before_main)
        self.assertEqual(runtime.card_state("UA-0017")["site_sync_status"], "DONE")

    def test_merge_failure_rolls_back_facts_and_records_failed_logical_slot(self):
        runtime.retry_card("UA-0017")
        worker = self.worker()
        job = worker.queue.claim()
        original = collector.merge_in_transaction
        def fail_after_merge(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic merge interruption")
        with mock.patch.object(runtime, "collect_bounded", return_value=collected([FACT])), \
             mock.patch.object(collector, "merge_in_transaction", side_effect=fail_after_merge):
            self.assertEqual(worker.execute(job), "FAILED")
        self.assertEqual(self.fact_count(), 0)
        self.assertEqual(worker.queue.report()["slots"][0]["state"], "FAILED")
        self.assertEqual([s["state"] for s in worker.queue.report()["slots"]][1:], ["PENDING"] * 3)

    def test_changed_vin_during_collection_never_commits_old_results(self):
        runtime.retry_card("UA-0017")
        worker = self.worker()
        job = worker.queue.claim()
        def mutate(*args, **kwargs):
            with sqlite3.connect(self.main) as db:
                db.execute("UPDATE cars SET vin='WAUZZZ4G3GN081841' WHERE id=1")
            return collected([FACT])
        with mock.patch.object(runtime, "collect_bounded", side_effect=mutate):
            self.assertEqual(worker.execute(job), "STALE_OR_UNPUBLISHED")
        self.assertEqual(self.fact_count(), 0)
        self.assertFalse(runtime.fact_binding_matches("UA-0017"))

    def test_durable_sync_recovers_after_write_failure_without_recollecting(self):
        runtime.retry_card("UA-0017")
        worker = self.worker()
        job = worker.queue.claim()
        with mock.patch.object(runtime, "collect_bounded", return_value=collected([FACT])):
            worker.execute(job)
        with mock.patch.object(runtime, "_atomic_existing", side_effect=OSError("synthetic unavailable writer")):
            runtime._sync_pending()
        self.assertEqual(self.fact_count(), 1)
        with worker.queue.connect() as db:
            row = db.execute("SELECT * FROM spec84_sync").fetchone()
            self.assertEqual(row["state"], "PENDING")
            db.execute("UPDATE spec84_sync SET next_try=0")
        runtime._sync_pending()
        self.assertEqual(runtime.card_state("UA-0017")["site_sync_status"], "DONE")
        self.assertEqual(worker.queue.report()["slots"][0]["runs"], 1)

    def test_deleted_public_page_is_not_recreated(self):
        runtime.retry_card("UA-0017")
        (self.root / "video/UA-0017.html").unlink()
        runtime._sync_pending()
        self.assertFalse((self.root / "video/UA-0017.html").exists())

    def test_repeat_stage_event_keeps_exact_due_times_and_baseline_rows(self):
        runtime.retry_card("UA-0017")
        before = runtime._queue.report()
        self.assertTrue(runtime.retry_card("UA-0017"))
        after = runtime._queue.report()
        self.assertEqual([x["due_at"] for x in before["slots"]], [x["due_at"] for x in after["slots"]])
        self.assertEqual(len(after["cycles"]), 1)

    def test_heartbeat_is_durable_and_contains_no_vin(self):
        runtime._heartbeat("RUNNING", published_count=18)
        with runtime._queue.connect() as db:
            row = db.execute("SELECT * FROM spec84_runtime_state WHERE key='heartbeat'").fetchone()
        value = json.loads(row["value_json"])
        self.assertEqual(value["published_count"], 18)
        self.assertEqual(value["worker_pid"], os.getpid())
        self.assertNotIn(VIN, row["value_json"])

    def test_binding_and_queue_generation_roll_back_together(self):
        runtime.retry_card("UA-0017")
        with sqlite3.connect(self.main) as db:
            db.execute("UPDATE cars SET vin='WAUZZZ4G3GN081841'")
        original = collector.ensure_binding
        def interrupted_binding(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic interruption between binding and commit")
        with mock.patch.object(collector, "ensure_binding", side_effect=interrupted_binding):
            with self.assertRaises(RuntimeError):
                runtime.retry_card("UA-0017")
        with legacy.connect_spec(True) as db:
            self.assertEqual(tuple(db.execute("SELECT vin,generation FROM spec84_fact_bindings").fetchone()), (VIN, 1))
        self.assertEqual(runtime._queue.card_state("UA-0017")["cycle"]["vin"], VIN)
        with sqlite3.connect(self.main) as db:
            db.execute("UPDATE cars SET vin='WAUZZZ4G3GN081842'")
        self.assertTrue(runtime.retry_card("UA-0017"))
        self.assertEqual(runtime._queue.card_state("UA-0017")["cycle"]["generation"], 2)

    def test_startup_published_recovery_and_bounded_stop(self):
        self.addCleanup(runtime.stop_worker)
        with mock.patch.object(runtime, "collect_bounded", return_value=collected()):
            self.assertTrue(runtime.start_worker())
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if runtime._queue is not None:
                    with runtime._queue.connect() as db:
                        table = db.execute("SELECT 1 FROM sqlite_master WHERE name='spec84_runtime_state'").fetchone()
                        row = db.execute("SELECT value_json FROM spec84_runtime_state WHERE key='heartbeat'").fetchone() if table else None
                    if row and json.loads(row[0])["status"] == "RUNNING":
                        break
                time.sleep(0.01)
            else:
                self.fail("worker did not record RUNNING heartbeat")
            self.assertEqual(len(runtime._queue.report()["cycles"]), 1)
            started = time.monotonic()
            runtime.stop_worker(timeout=1)
            self.assertLess(time.monotonic() - started, 1.2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
