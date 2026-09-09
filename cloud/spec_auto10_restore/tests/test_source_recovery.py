"""Synthetic offline contracts. No fixture is a claim about live site markup."""
import dataclasses
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import source_policy as policy


CAR = {"vin": "KNAXX0000J0000001", "brand": "Kia", "model": "K5",
       "year": "2018", "fuel": "LPI", "engine_cc": 1999}
URL = "https://www.auto-data.net/en/offline-fixture"
HTML = b"""<html><h1>Kia K5 2018 1999 LPI</h1><table>
<tr><th>Length</th><td>4855 mm</td></tr>
<tr><th>Width</th><td>1860 mm</td></tr>
<tr><th>Wheelbase</th><td>2805 mm</td></tr>
<tr><th>Seats</th><td>5</td></tr>
<tr><th>Power</th><td>151 hp</td></tr>
</table></html>"""


class Response(io.BytesIO):
    status = 200

    def __init__(self, body=HTML, url=URL):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class FetchRecoveryTest(unittest.TestCase):
    def setUp(self):
        policy.clear_fetch_caches()
        self.clock = mock.patch.object(policy.time, "monotonic", return_value=100.0)
        self.now = self.clock.start()
        self.builder = mock.patch.object(policy.urllib.request, "build_opener")
        self.fetch = self.builder.start().return_value.open

    def tearDown(self):
        self.builder.stop()
        self.clock.stop()
        policy.clear_fetch_caches()

    def test_failure_recovers_after_ttl_without_restart(self):
        self.fetch.side_effect = [urllib.error.URLError("fixture timeout"), Response()]
        with self.assertRaisesRegex(policy.SourcePolicyError, "NETWORK_URLError"):
            policy._open_bytes(URL)
        with self.assertRaisesRegex(policy.SourcePolicyError, "RETRY_DEFERRED"):
            policy._open_bytes(URL)
        self.assertEqual(self.fetch.call_count, 1)
        self.now.return_value = 131.0
        result = policy._open_bytes(URL)
        self.assertEqual(result, HTML)
        self.assertEqual(result.evidence_origin, "fresh_page")
        self.assertNotIn(URL, policy._FETCH_FAILURE_CACHE)

    def test_backoff_grows_and_stays_bounded(self):
        self.fetch.side_effect = urllib.error.URLError("fixture timeout")
        expected = [30, 60, 120, 240, 480, 900, 900]
        for delay in expected:
            now = self.now.return_value
            with self.assertRaises(policy.SourcePolicyError):
                policy._open_bytes(URL)
            failure = policy._FETCH_FAILURE_CACHE[URL]
            self.assertEqual(failure.retry_at - now, delay)
            self.now.return_value = failure.retry_at + 1

    def test_http_429_respects_retry_after(self):
        self.fetch.side_effect = urllib.error.HTTPError(URL, 429, "rate limited", {"Retry-After": "1800"}, None)
        with self.assertRaisesRegex(policy.SourcePolicyError, "HTTP_429"):
            policy._open_bytes(URL)
        self.now.return_value = 1000.0
        with self.assertRaisesRegex(policy.SourcePolicyError, "RETRY_DEFERRED"):
            policy._open_bytes(URL)
        self.assertEqual(self.fetch.call_count, 1)
        self.assertEqual(policy._FETCH_FAILURE_CACHE[URL].retry_at, 1900)

    def test_body_cache_expires_and_reports_actual_origin(self):
        self.fetch.side_effect = [Response(), Response(b"new body")]
        first = policy._open_bytes(URL)
        second = policy._open_bytes(URL)
        self.assertEqual(second.evidence_origin, "cached_page")
        self.assertEqual(second.retrieved_at, first.retrieved_at)
        self.now.return_value += policy.BODY_CACHE_TTL_SECONDS + 1
        third = policy._open_bytes(URL)
        self.assertEqual(third, b"new body")
        self.assertEqual(third.evidence_origin, "fresh_page")
        self.assertEqual(self.fetch.call_count, 2)

    def test_failure_cache_is_bounded(self):
        self.fetch.side_effect = urllib.error.URLError("offline")
        for index in range(policy.CACHE_MAX_ENTRIES + 5):
            with self.assertRaises(policy.SourcePolicyError):
                policy._open_bytes(URL + str(index))
        self.assertEqual(len(policy._FETCH_FAILURE_CACHE), policy.CACHE_MAX_ENTRIES)

    def test_oversized_response_is_not_cached_as_success(self):
        with mock.patch.object(policy, "MAX_RESPONSE_BYTES", 10):
            self.fetch.return_value = Response(b"x" * 11)
            with self.assertRaisesRegex(policy.SourcePolicyError, "RESPONSE_TOO_LARGE"):
                policy._open_bytes(URL)
        self.assertNotIn(URL, policy._BODY_CACHE)

    def test_external_redirect_rejected_before_follow(self):
        request = urllib.request.Request(URL)
        with self.assertRaisesRegex(policy.SourcePolicyError, "REDIRECT_DOMAIN_FORBIDDEN"):
            policy._AllowedRedirect().redirect_request(
                request, None, 302, "redirect", {}, "https://ads.example.org/vin"
            )
        self.fetch.assert_not_called()


class AdapterContractsTest(unittest.TestCase):
    def test_original_ten_sources_unchanged(self):
        self.assertEqual(policy.SOURCE_DOMAINS, (
            "vpic.nhtsa.dot.gov", "auto-data.net", "carwiki.co.kr", "auto.danawa.com",
            "carisyou.com", "ultimatespecs.com", "automobile-catalog.com",
            "cars-data.com", "carfolio.com", "encycarpedia.com",
        ))

    def test_http_200_challenge_is_not_a_working_adapter(self):
        report = policy.audit_sources(
            network=True, opener=lambda request, **kwargs: Response(b"<html>Please verify you are human</html>", request.full_url)
        )
        self.assertEqual(report["pass_count"], 0)
        self.assertEqual(report["sources"]["auto-data.net"]["status"], "FAIL_CONTENT_OR_IDENTITY")
        self.assertEqual(report["sources"]["carisyou.com"]["status"], "NOT_RUN")

    def test_offline_audit_has_ten_not_run_and_performs_no_request(self):
        opener = mock.Mock(side_effect=AssertionError("network forbidden in fixture"))
        report = policy.audit_sources(opener=opener)
        self.assertEqual(report["source_count"], 10)
        self.assertEqual(report["not_run_count"], 10)
        self.assertEqual(report["pass_count"], 0)
        self.assertFalse(report["vin_sent"])
        opener.assert_not_called()

    def test_network_unavailable_is_not_evidence_of_broken_source(self):
        opener = mock.Mock(side_effect=urllib.error.URLError("sandbox denied"))
        report = policy.audit_sources(network=True, opener=opener)
        self.assertEqual(report["not_run_count"], 10)
        self.assertEqual(report["pass_count"], 0)

    def test_vpic_generic_schema_does_not_claim_vin_decoder_pass(self):
        payload = json.dumps({"Results": [{"Make_Name": "KIA", "Model_Name": "K5"}]}).encode()
        requests = []
        def opener(request, **kwargs):
            requests.append(request.full_url)
            return Response(payload if "vpic" in request.full_url else b"unmatched", request.full_url)
        report = policy.audit_sources(network=True, opener=opener)
        self.assertEqual(report["sources"]["vpic.nhtsa.dot.gov"]["status"], "API_SCHEMA_ONLY")
        self.assertEqual(report["pass_count"], 0)
        self.assertTrue(all("DecodeVin" not in url for url in requests))

    def test_synthetic_parser_rejects_wrong_identity_prices_primary_fields(self):
        score, facts = policy.extract_page_facts(CAR, URL, HTML)
        self.assertGreater(score, 0.64)
        self.assertGreaterEqual(len(facts), 4)
        wrong = HTML.replace(b"Kia K5 2018 1999 LPI", b"Ford Fiesta 2011 diesel")
        self.assertEqual(policy.extract_page_facts(CAR, URL, wrong)[1], [])
        same_make_wrong_model = HTML.replace(b"K5", b"Sportage")
        self.assertEqual(policy.extract_page_facts(CAR, URL, same_make_wrong_model)[1], [])
        hostile = HTML.replace(b"151 hp", b"$1000 dealer price") + b"<table><tr><td>VIN</td><td>replaced</td></tr></table>"
        clean = policy.extract_page_facts(CAR, URL, hostile)[1]
        self.assertNotIn("maximum_power", {fact.field_key for fact in clean})
        self.assertFalse({fact.field_key for fact in clean} & policy.BLOCKED_PRIMARY_KEYS)

    def test_carwiki_engine_facts_require_exact_fuel_displacement_segment(self):
        body = ("<h1>Kia K5 2018 1999 LPI</h1><div>제원</div><div>연료</div><div>diesel</div>"
                "<div>배기량</div><div>1685</div><div>최고출력</div><div>141 hp</div>"
                "<div>기본사양</div><div>전장</div><div>4855 mm</div>").encode()
        facts = policy.extract_page_facts(CAR, "https://www.carwiki.co.kr/model/fixture", body)[1]
        self.assertNotIn("maximum_power", {fact.field_key for fact in facts})
        self.assertIn("length", {fact.field_key for fact in facts})

    def test_curated_facts_are_labeled_historical_and_not_counted_fresh(self):
        known = dict(CAR, vin="KNAGS416BLA375484", year="2019")
        result = policy.enrich(known, opener=mock.Mock(side_effect=urllib.error.URLError("offline")))
        self.assertTrue(result["facts"])
        source = result["sources"]["auto.danawa.com"]
        self.assertEqual(source["status"], "CURATED_AVAILABLE")
        self.assertEqual(source["fresh_facts"], 0)
        self.assertEqual(source["curated_audited_on"], "2026-09-04")
        for fact in result["facts"]:
            self.assertEqual(fact["evidence_origins"], ["curated_profile"])
            self.assertTrue(all(not entry["retrieved_at"] for entry in fact["provenance"]))

    def test_fresh_fact_wins_same_source_conflict_over_curated(self):
        historical = policy.Fact("length", "Длина", "dimensions", "4800 mm", "mm", .99,
                                 "auto-data.net", URL, "curated_profile", "", "2026-09-04")
        fresh = dataclasses.replace(historical, display_value="4855 mm", confidence=.91,
                                    evidence_origin="fresh_page", retrieved_at="2026-09-09T00:00:00Z",
                                    curated_audited_on="")
        result = policy.deduplicate([historical, fresh])[0]
        self.assertEqual(result["display_value"], "4855 mm")
        self.assertEqual(result["evidence_origins"], ["fresh_page"])

    def test_incomplete_vpic_identity_is_rejected(self):
        base = {"Make": "KIA", "Model": "K5", "ModelYear": "2018", "ErrorCode": "0"}
        self.assertTrue(policy.vpic_identity_matches(CAR, base))
        for key in base:
            missing = dict(base)
            missing.pop(key)
            self.assertFalse(policy.vpic_identity_matches(CAR, missing), key)

    def test_new_vin_cannot_inherit_historical_profile_by_prefix(self):
        unaudited = dict(CAR, vin="KNAGS416BLA000001", year="2019")
        self.assertIsNone(policy.match_profile(unaudited))
        self.assertEqual(policy.profile_facts(policy.match_profile(unaudited)), [])

    def test_japanese_frame_needs_mapping_and_is_never_sent_to_vpic(self):
        opener = mock.Mock(side_effect=AssertionError("no VIN/frame may be transmitted"))
        self.assertEqual(policy.normalize_identity(" nhp10-1234567 "), "NHP10-1234567")
        with self.assertRaises(policy.SourcePolicyError):
            policy.normalize_identity("arbitrary-123456")
        result = policy.enrich({"vin": "NHP10-1234567", "brand": "Toyota", "model": "Aqua"}, opener=opener)
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["facts"], [])
        self.assertTrue(all(item["status"] == "NOT_RUN_UNRESOLVED_IDENTITY" for item in result["sources"].values()))
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
