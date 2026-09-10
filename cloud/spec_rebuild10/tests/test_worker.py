import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sources as s
from store import SpecStore, StoreError
from worker import CollectorBinding, CollectedDocument, SpecWorker, bind_worker, source_identity, vpic_collector

IDENTITY = {"vin": "KNAGU416BKA900010", "brand": "Kia", "model": "K5", "year": 2019,
            "market": "KR", "fuel": "LPG", "transmission": "automatic", "engine_cc": 1999}
URLS = {"kia_kr": "https://www.kia.com/kr/vehicles/k5/specification",
        "danawa": "https://auto.danawa.com/auto/?Model=3260&Tab=spec&Work=model",
        "carisyou": "https://www.carisyou.com/car/5217/Spec/52976"}
DOC_SHA = "c" * 64


def fixture_collector(source="kia_kr", *, change=None, action=None, value=4855):
    def collect(request):
        if action:
            action(request)
        identity = dict(request.identity)
        if change:
            identity.update(change)
        return CollectedDocument(source, {
            "schema": "ua-art.normalized-source.v1", "source_id": source, "identity": identity,
            "document": {"url": URLS[source], "sha256": DOC_SHA,
                "evidence_kind": "manufacturer_document" if source == "kia_kr" else "catalog_record"},
            "facts": [{"key": "length_mm", "value": value, "unit": "mm",
                       "label_uk": "Довжина", "label_ru": "Длина", "category": "technical"}]},
            authorization=s.ImportAuthorization(source, "TEST-NORMALIZER", DOC_SHA))
    return CollectorBinding(source, collect, s.AccessGrant(source, True, True, True, "TEST-RIGHTS"))


class Clock:
    def __init__(self):
        self.wall = time.time() + 1
        self.elapsed = 0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.elapsed

    def advance(self, seconds):
        self.wall += seconds
        self.elapsed += seconds


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "spec.sqlite")
        self.store = SpecStore(self.path, max_attempts=2)
        self.store.upsert_vehicle("UA-0017", IDENTITY)
        self.clock = Clock()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def worker(self, collectors=None, **options):
        return SpecWorker(self.store, collectors, clock=self.clock.time,
                          monotonic=self.clock.monotonic, **options)

    def test_unconfigured_does_not_consume_queue_attempt(self):
        result = self.worker().run_once()
        self.assertEqual(result["status"], "BLOCKED_NO_PROVISIONED_COLLECTORS")
        self.assertEqual(sum(x["state"] == "NOT_PROVISIONED" for x in result["sources"].values()), 9)
        self.assertEqual(result["sources"]["vpic"]["state"], "TRANSPORT_NOT_CONFIGURED")
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 0)

    def test_real_queue_collector_policy_store_chain_and_no_publish(self):
        result = self.worker({"kia_kr": fixture_collector()}).run_once()
        self.assertEqual(result["status"], "COLLECTED")
        self.assertEqual(result["accepted"], 1)
        fact = self.store.get_facts("UA-0017")[0]
        self.assertEqual(fact["verification_status"], "MODEL_VERIFIED")
        self.assertEqual(fact["policy_acceptance"]["uid"], "UA-0017")
        self.assertEqual(fact["value"], 4855)
        self.assertFalse(self.store.get_vehicle("UA-0017")["published"])
        self.assertIsNone(self.store.get_publication_snapshot("UA-0017"))
        self.assertFalse(result["publication_performed"])
        self.assertFalse(result["all_ten_live_acceptance"])
        self.assertEqual(result["configured"], 1)

    def test_duplicate_run_does_not_duplicate_writes(self):
        worker = self.worker({"kia_kr": fixture_collector()})
        worker.run_once()
        before = self.store.get_candidates("UA-0017")
        self.assertEqual(worker.run_once()["status"], "IDLE")
        self.assertEqual(self.store.get_candidates("UA-0017"), before)

    def test_catalog_needs_second_independent_origin(self):
        result = self.worker({"danawa": fixture_collector("danawa")}).run_once()
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_two_catalogs_accept_one_fact(self):
        result = self.worker({name: fixture_collector(name) for name in ("danawa", "carisyou")}).run_once()
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(self.store.get_facts("UA-0017")[0]["provenance"]["corroborating_sources"],
                         ["carisyou", "danawa"])

    def test_vpic_does_not_create_technical_acceptance(self):
        def collect(request):
            return CollectedDocument("vpic", {"Results": [{"VIN": request.identity["vin"],
                "Make": "KIA", "Model": "K5", "ModelYear": "2019", "ErrorCode": "0"}]})
        result = self.worker({"vpic": CollectorBinding("vpic", collect)}).run_once()
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["review"], 3)
        self.assertEqual(sum(x["state"] == "NOT_PROVISIONED" for x in result["sources"].values()), 9)
        self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_actual_vpic_collector_uses_bounded_transport_and_parser(self):
        calls = []
        def transport(request):
            calls.append(request)
            return s.Response(200, json.dumps({"Results": [{"VIN": IDENTITY["vin"],
                "Make": "KIA", "Model": "K5", "ModelYear": "2019", "ErrorCode": "0"}]}).encode())
        result = self.worker({"vpic": vpic_collector(transport)}).run_once()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].url.endswith("?format=json&modelyear=2019"))
        self.assertLessEqual(calls[0].timeout_seconds, 15)
        self.assertEqual(calls[0].max_bytes, s.MAX_RESPONSE_BYTES)
        self.assertEqual(result["review"], 3)
        self.assertEqual(result["accepted"], 0)

    def test_explicit_refresh_after_new_source_provisioning(self):
        self.worker({"danawa": fixture_collector("danawa")}).run_once()
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        self.store.request_refresh("UA-0017", "Second supplier provisioned", "refresh-1")
        result = self.worker({name: fixture_collector(name) for name in ("danawa", "carisyou")}).run_once()
        self.assertEqual(result["accepted"], 1)
        self.store.request_refresh("UA-0017", "Second supplier provisioned", "refresh-1")
        self.assertEqual(self.worker({"kia_kr": fixture_collector()}).run_once()["status"], "IDLE")

    def test_failed_refresh_keeps_existing_facts(self):
        self.store.import_legacy("UA-0017", [{"key": "length_mm", "value": 4855,
            "unit": "mm", "verification_status": "VERIFIED_10SRC"}], "legacy-test")
        before = self.store.facts_digest("UA-0017")
        def failure(request):
            raise RuntimeError("api_key=SECRET bad supplier response")
        result = self.worker({"kia_kr": CollectorBinding("kia_kr", failure,
            fixture_collector().access)}).run_once()
        self.assertEqual(result["status"], "RETRY_SCHEDULED")
        self.assertEqual(self.store.facts_digest("UA-0017"), before)
        self.assertNotIn("SECRET", json.dumps(result) + json.dumps(self.store.get_jobs()))

    def test_source_failure_keeps_verified_batch_and_collects_remaining_sources(self):
        called = []
        def failure(request):
            called.append("failure")
            raise RuntimeError("fail")
        collectors = {"kia_kr": fixture_collector(action=lambda _: called.append("first")),
            "danawa": CollectorBinding("danawa", failure, fixture_collector("danawa").access),
            "carisyou": fixture_collector("carisyou", action=lambda _: called.append("last"))}
        result = self.worker(collectors).run_once()
        self.assertEqual(result["status"], "PARTIAL_COLLECTED_RETRY_SCHEDULED")
        self.assertEqual(called, ["first", "failure", "last"])
        self.assertEqual(self.store.get_facts("UA-0017")[0]["value"], 4855)
        self.assertEqual(result["source_errors"], {"danawa": "COLLECTOR_FAILED"})
        self.assertEqual(result["sources"]["carisyou"]["state"], "PARSED_CONTROL_CASE")
        self.assertEqual(self.store.get_jobs()[0]["state"], "retry")
        self.assertFalse(self.store.get_vehicle("UA-0017")["published"])

    def test_failed_first_source_does_not_prevent_later_verified_facts(self):
        def failure(request):
            raise s.SourceError("SOURCE_HTTP_ERROR")
        worker = self.worker({
            "danawa": CollectorBinding("danawa", failure, fixture_collector("danawa").access),
            "kia_kr": fixture_collector()}, retry_after=0)
        first = worker.run_once()
        self.assertEqual(first["status"], "PARTIAL_COLLECTED_RETRY_SCHEDULED")
        self.assertEqual(first["accepted"], 1)
        second = worker.run_once()
        self.assertEqual(second["status"], "PARTIAL_COLLECTED_EXHAUSTED")
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 2)
        self.assertEqual(self.store.get_jobs()[0]["error"], "danawa:SOURCE_HTTP_ERROR")
        self.assertEqual(worker.run_once()["status"], "IDLE")
        self.assertEqual(len(self.store.get_facts("UA-0017")), 1)
        self.assertFalse(self.store.upsert_vehicle("UA-0017", IDENTITY)["queued"])
        self.assertEqual(worker.run_once()["status"], "IDLE")

    def test_partial_retry_can_recover_and_clear_failure_without_resetting_attempts(self):
        attempts = []
        good = fixture_collector("danawa")
        def once_unavailable(request):
            attempts.append(request)
            return CollectedDocument("danawa", outcome="UNAVAILABLE") if len(attempts) == 1 else good.collect(request)
        worker = self.worker({"kia_kr": fixture_collector(),
            "danawa": CollectorBinding("danawa", once_unavailable, good.access)}, retry_after=0)
        self.assertEqual(worker.run_once()["status"], "PARTIAL_COLLECTED_RETRY_SCHEDULED")
        self.assertEqual(worker.run_once()["status"], "COLLECTED")
        job = self.store.get_jobs()[0]
        self.assertEqual(job["attempts"], 2)
        self.assertEqual(job["state"], "succeeded")
        self.assertIsNone(job["error"])

    def test_partial_failure_keeps_manual_hidden_and_conflicting_values(self):
        self.store.set_manual_fact("UA-0017", {"key": "length_mm", "value": 4900,
            "unit": "mm", "hidden": True})
        failed = CollectorBinding("danawa", lambda _: CollectedDocument("danawa", outcome="UNAVAILABLE"),
                                  fixture_collector("danawa").access)
        result = self.worker({"danawa": failed, "kia_kr": fixture_collector()}).run_once()
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["review"], 1)
        stored = self.store.get_facts("UA-0017", include_hidden=True)[0]
        self.assertEqual(stored["value"], 4900)
        self.assertTrue(stored["manual"])
        self.assertTrue(stored["hidden"])

    def test_unsafe_source_or_store_errors_discard_other_sources_batch(self):
        for error, code in ((s.SourceError("SOURCE_NOT_APPROVED"), "SOURCE_NOT_APPROVED"),
                            (s.SourceError("UNRECOGNIZED_FAILURE"), "UNRECOGNIZED_FAILURE"),
                            (StoreError("database failure"), "STORE_REJECTED_OPERATION")):
            with self.subTest(error=error):
                def failure(request):
                    raise error
                worker = self.worker({"kia_kr": fixture_collector(),
                    "danawa": CollectorBinding("danawa", failure, fixture_collector("danawa").access)}, retry_after=0)
                result = worker.run_once()
                self.assertIn(result["status"], ("RETRY_SCHEDULED", "EXHAUSTED"))
                self.assertEqual(result["error"], code)
                self.assertEqual(self.store.get_facts("UA-0017"), [])
                if result["status"] == "EXHAUSTED":
                    self.store.request_refresh("UA-0017", "New independent test case", "test-refresh")

    def test_retry_budget_exhausts_without_infinite_loop(self):
        def failure(request):
            raise RuntimeError("fail")
        worker = self.worker({"kia_kr": CollectorBinding("kia_kr", failure,
            fixture_collector().access)}, retry_after=0)
        self.assertEqual(worker.run_once()["status"], "RETRY_SCHEDULED")
        self.assertEqual(worker.run_once()["status"], "EXHAUSTED")
        self.assertEqual(worker.run_once()["status"], "IDLE")
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 2)

    def test_competing_worker_cannot_claim_same_job(self):
        with SpecStore(self.path) as other:
            second = SpecWorker(other, {"kia_kr": fixture_collector()}, clock=self.clock.time,
                monotonic=self.clock.monotonic, worker_id="second")
            outcomes = []
            first = self.worker({"kia_kr": fixture_collector(action=lambda _: outcomes.append(second.run_once()))})
            self.assertEqual(first.run_once()["accepted"], 1)
            self.assertEqual(outcomes[0]["status"], "IDLE")

    def test_identity_change_discards_old_result(self):
        collector = fixture_collector(action=lambda _: self.store.upsert_vehicle("UA-0017", dict(IDENTITY, year=2020)))
        result = self.worker({"kia_kr": collector}).run_once()
        self.assertEqual(result["status"], "STALE_RESULT_DISCARDED")
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        self.assertEqual(self.store.get_vehicle("UA-0017")["revision"], 2)
        self.assertEqual(sum(x["state"] == "ready" for x in self.store.get_jobs()), 1)

    def test_delete_during_collection_discards_result(self):
        result = self.worker({"kia_kr": fixture_collector(action=lambda _: self.store.delete_vehicle("UA-0017"))}).run_once()
        self.assertEqual(result["status"], "STALE_RESULT_DISCARDED")
        self.assertTrue(self.store.get_vehicle("UA-0017")["tombstoned"])
        self.assertEqual(self.store.get_jobs()[0]["state"], "cancelled")

    def test_expired_lease_cannot_commit_and_can_recover(self):
        first = self.worker({"kia_kr": fixture_collector(action=lambda _: self.clock.advance(130))})
        self.assertEqual(first.run_once()["status"], "STALE_RESULT_DISCARDED")
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        second = self.worker({"kia_kr": fixture_collector()})
        self.assertEqual(second.run_once()["accepted"], 1)

    def test_time_budget_stops_before_commit(self):
        result = self.worker({"kia_kr": fixture_collector(action=lambda _: self.clock.advance(95))}).run_once()
        self.assertEqual(result["status"], "RETRY_SCHEDULED")
        self.assertEqual(result["error"], "WORKER_TIME_BUDGET_EXHAUSTED")
        self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_deadline_discards_late_source_only_and_skips_unstarted_sources(self):
        calls = []
        collectors = {"kia_kr": fixture_collector(),
            "danawa": fixture_collector("danawa", action=lambda _: self.clock.advance(95)),
            "carisyou": fixture_collector("carisyou", action=lambda _: calls.append("late"))}
        result = self.worker(collectors).run_once()
        self.assertEqual(result["status"], "PARTIAL_COLLECTED_RETRY_SCHEDULED")
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(calls, [])
        self.assertEqual(result["sources"]["danawa"]["state"], "ERROR")
        self.assertEqual(result["sources"]["carisyou"]["state"], "SKIPPED_TIME_BUDGET")
        self.assertEqual(self.store.get_facts("UA-0017")[0]["provenance"]["corroborating_sources"], ["kia_kr"])

    def test_manual_hidden_fact_is_not_unhidden(self):
        self.store.set_manual_fact("UA-0017", {"key": "length_mm", "value": 4855, "unit": "mm", "hidden": True})
        self.worker({"kia_kr": fixture_collector()}).run_once()
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        fact = self.store.get_facts("UA-0017", include_hidden=True)[0]
        self.assertTrue(fact["manual"])
        self.assertTrue(fact["hidden"])

    def test_existing_different_value_stays_review(self):
        self.store.set_manual_fact("UA-0017", {"key": "length_mm", "value": 4900, "unit": "mm"})
        result = self.worker({"kia_kr": fixture_collector()}).run_once()
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.store.get_facts("UA-0017")[0]["value"], 4900)

    def test_wrong_market_and_engine_rejected(self):
        for changed in ({"market": "US"}, {"engine_cc": 1600}):
            with self.subTest(changed=changed):
                result = self.worker({"kia_kr": fixture_collector(change=changed)}, retry_after=0).run_once()
                self.assertEqual(result["error"], "IDENTITY_MISMATCH")
                self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_aliases_are_explicit_and_conflicts_rejected(self):
        value = source_identity(IDENTITY)
        self.assertEqual(value["make"], "Kia")
        self.assertEqual(value["gearbox"], "automatic")
        with self.assertRaises(s.SourceError):
            source_identity(dict(IDENTITY, make="Hyundai"))

    def test_impostor_collector_result_rejected(self):
        binding = CollectorBinding("kia_kr", lambda _: CollectedDocument("danawa"), fixture_collector().access)
        result = self.worker({"kia_kr": binding}).run_once()
        self.assertEqual(result["error"], "COLLECTOR_SOURCE_IMPERSONATION")
        self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_impostor_after_verified_document_discards_the_uncommitted_batch(self):
        binding = CollectorBinding("danawa", lambda _: CollectedDocument("unknown_source"),
                                   fixture_collector("danawa").access)
        result = self.worker({"kia_kr": fixture_collector(), "danawa": binding}).run_once()
        self.assertEqual(result["error"], "COLLECTOR_SOURCE_IMPERSONATION")
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        self.assertEqual(self.store.get_candidates("UA-0017"), [])

    def test_no_match_is_completed_without_fabricated_facts(self):
        binding = CollectorBinding("kia_kr", lambda _: CollectedDocument("kia_kr", outcome="NO_MATCH"), fixture_collector().access)
        result = self.worker({"kia_kr": binding}).run_once()
        self.assertEqual(result["status"], "NO_NEW_CONFIRMED_FACTS")
        self.assertEqual(result["sources"]["kia_kr"]["state"], "NO_MATCH")
        self.assertEqual(self.store.get_facts("UA-0017"), [])

    def test_handoff_requires_authenticating_verifier_and_does_not_start(self):
        receipt = {"module": "spec_rebuild10", "old_workers_stopped": True,
                   "exclusive_owner": True, "receipt_id": "SYNTHETIC-TEST"}
        with self.assertRaises(s.SourceError):
            bind_worker(self.store, {}, installation_receipt=receipt, verify_installation=lambda _: False)
        worker = bind_worker(self.store, {}, installation_receipt=receipt, verify_installation=lambda _: True)
        self.assertIsInstance(worker, SpecWorker)
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 0)

    def test_acceptance_scope_only_wraps_durable_acceptance_not_collection(self):
        events = []
        entered = False
        @contextmanager
        def scope():
            nonlocal entered
            entered = True
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")
                entered = False
        def collecting(request):
            self.assertFalse(entered)
            events.append("collect")
        approve = self.store.approve_candidates
        def accepting(*args, **kwargs):
            self.assertTrue(entered)
            events.append("approve")
            return approve(*args, **kwargs)
        with patch.object(self.store, "approve_candidates", side_effect=accepting):
            result = self.worker({"kia_kr": fixture_collector(action=collecting)},
                                 acceptance_scope=scope).run_once()
        self.assertEqual(result["status"], "COLLECTED")
        self.assertEqual(events, ["collect", "enter", "approve", "exit"])
        self.assertFalse(entered)

    def test_identity_is_rechecked_after_acceptance_scope_acquisition(self):
        @contextmanager
        def scope():
            self.store.upsert_vehicle("UA-0017", dict(IDENTITY, year=2020))
            yield
        with patch.object(self.store, "approve_candidates") as approve:
            result = self.worker({"kia_kr": fixture_collector()}, acceptance_scope=scope).run_once()
        self.assertEqual(result["status"], "STALE_RESULT_DISCARDED")
        approve.assert_not_called()
        self.assertEqual(self.store.get_facts("UA-0017"), [])
        self.assertEqual(self.store.get_vehicle("UA-0017")["revision"], 2)

    def test_acceptance_scope_factory_must_be_callable(self):
        with self.assertRaisesRegex(s.SourceError, "ACCEPTANCE_SCOPE_INVALID"):
            self.worker({"kia_kr": fixture_collector()}, acceptance_scope=object())
        self.assertEqual(self.store.get_jobs()[0]["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
