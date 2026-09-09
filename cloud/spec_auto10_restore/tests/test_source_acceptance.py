"""Synthetic acceptance mechanics; no test response proves a live source."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))
import source_acceptance as acceptance
from repair_vpic_identity import patch_vpic_identity

PLAN = json.loads((ROOT / "source_acceptance_plan.json").read_text())
policy = types.ModuleType("source_policy_acceptance_fixture")
sys.modules[policy.__name__] = policy
exec(compile(patch_vpic_identity((ROOT / "runtime/source_policy.py").read_text()), "source_policy.py", "exec"), policy.__dict__)
VIN = "KNAXX0000J0000001"
CAR = {"brand": "Kia", "model": "K5", "year": "2018", "fuel": "LPI", "engine_cc": 1999}
ROW = {"VIN": VIN, "Make": "KIA", "Model": "K5", "ModelYear": "2018", "ErrorCode": "0", "Doors": "4"}


class Response(io.BytesIO):
    status = 200
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url
    def geturl(self):
        return self.url


def vin_plan():
    plan = copy.deepcopy(PLAN)
    item = plan["sources"][0]
    item.update({"mode": "vin_decode", "url": "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/",
                 "control": {"vin_sha256": acceptance.sha(VIN.encode()), "car": CAR},
                 "control_review": {"reference": "SYNTHETIC_OFFLINE_ONLY", "sha256": "a" * 64}})
    return plan


class AcceptanceTests(unittest.TestCase):
    def test_default_offline_makes_no_requests_and_ten_not_run(self):
        fetch = mock.Mock(side_effect=AssertionError("network forbidden"))
        report = acceptance.run(PLAN, policy, opener=fetch)
        fetch.assert_not_called()
        self.assertEqual(report["source_count"], 10)
        self.assertEqual(report["network_calls_started"], 0)
        self.assertFalse(report["all_ten_adapters_pass"])
        self.assertTrue(all(i["adapter"] == "NOT_RUN" for i in report["sources"]))

    def test_first_transport_failure_stops_remaining_sources_without_retry(self):
        fetch = mock.Mock(side_effect=urllib.error.URLError(PermissionError("sensitive payload")))
        report = acceptance.run(PLAN, policy, network=True, origin="fixture", authorization_ref="fixture", opener=fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(report["stop_reason"], "ACCESS_DENIED")
        self.assertEqual(report["sources_with_http_response"], 0)
        self.assertNotIn("sensitive payload", json.dumps(report))

    def test_schema_and_unreviewed_identity_never_adapter_pass(self):
        def fetch(request, **kwargs):
            body = json.dumps({"Results": [{"Make_Name": "Kia", "Model_Name": "K5"}]}).encode() if "vpic" in request.full_url else b"<h1>Unreviewed vehicle identity</h1>"
            return Response(body, request.full_url)
        report = acceptance.run(PLAN, policy, network=True, origin="fixture", authorization_ref="fixture", opener=fetch)
        self.assertEqual(report["sources"][0]["adapter"], "API_SCHEMA_ONLY")
        self.assertEqual(report["sources"][4]["identity"], "CONTROL_REVIEW_REQUIRED")
        self.assertEqual(report["adapter_pass_count"], 0)
        self.assertEqual(report["network_calls_started"], 10)
        self.assertEqual(report["sources_with_http_response"], 10)
        self.assertTrue(report["probe_execution_complete"])
        self.assertEqual(report["gate_b"], "NOT_EVALUATED")

    def test_exact_vin_approval_hash_required_before_any_request(self):
        fetch = mock.Mock()
        for wrong in (None, "KNAXX0000J0000002", "NHP10-1234567"):
            with self.subTest(wrong=wrong):
                with self.assertRaises((acceptance.AcceptanceError, policy.SourcePolicyError)):
                    acceptance.run(vin_plan(), policy, network=True, origin="fixture", authorization_ref="fixture", private_vin=wrong, opener=fetch)
        fetch.assert_not_called()

    def test_wrong_vin_same_make_model_year_rejected_and_private_vin_redacted(self):
        def fetch(request, **kwargs):
            if "vpic" in request.full_url:
                return Response(json.dumps({"Results": [dict(ROW, VIN="KNAXX0000J0000002")]}).encode(), request.full_url)
            return Response(b"<h1>No matching facts</h1>", request.full_url)
        report = acceptance.run(vin_plan(), policy, network=True, origin="fixture", authorization_ref="fixture", private_vin=VIN, opener=fetch)
        self.assertEqual(report["sources"][0]["adapter"], "FAIL_IDENTITY_OR_FACTS")
        self.assertEqual(report["sources"][0]["field_count"], 0)
        self.assertNotIn(VIN, json.dumps(report))
        self.assertTrue(report["vin_request_attempted"])

    def test_exact_vin_and_existing_identity_guards_pass(self):
        item = vin_plan()["sources"][0]
        good = acceptance.evaluate_body(policy, item, json.dumps({"Results": [ROW]}).encode(), VIN)
        self.assertEqual(good["adapter"], "PASS")
        self.assertEqual(good["identity"], "EXACT_VIN_MAKE_MODEL_YEAR")
        self.assertEqual(good["fields"], ["doors"])

    def test_foreign_redirect_rejected_before_follow(self):
        handler = acceptance.DomainRedirects(policy, "carisyou.com")
        with self.assertRaisesRegex(acceptance.AcceptanceError, "REDIRECT_NOT_ALLOWED"):
            handler.redirect_request(urllib.request.Request("https://www.carisyou.com/car/5688/Spec/54625"), None, 302, "redirect", {}, "https://ads.example.org/")

    def test_limits_domains_and_unreviewed_control_cannot_be_relaxed(self):
        for mutate in (
            lambda p: p["limits"].update(retries=1),
            lambda p: p["sources"][4].update(domain="example.org"),
            lambda p: p["sources"][4].update(mode="model_adapter", control=CAR),
            lambda p: p["sources"][1].update(url="https://auto-data.net:444/spec"),
            lambda p: p["sources"][1].update(url="https://auto-data.net/spec?vin=" + VIN),
        ):
            plan = copy.deepcopy(PLAN)
            mutate(plan)
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.validate_plan(plan, policy)

    def test_runtime_drift_is_rejected_without_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for name in acceptance.RUNTIME_FILES:
                (path / name).write_text("raise AssertionError('must not execute')\n")
            with self.assertRaisesRegex(acceptance.AcceptanceError, "RUNTIME_HASH_MISMATCH"):
                acceptance.load_runtime(path, PLAN["runtime_sha256"])

    def test_429_records_retry_after_without_retry_or_false_pass(self):
        fetch = mock.Mock(side_effect=urllib.error.HTTPError("https://fixture.invalid", 429, "limited", {"Retry-After": "600"}, None))
        report = acceptance.run(PLAN, policy, network=True, origin="fixture", authorization_ref="fixture", opener=fetch)
        self.assertEqual(fetch.call_count, 10)
        self.assertEqual(report["sources"][0]["retry_after_seconds"], 600)
        self.assertEqual(report["adapter_pass_count"], 0)

    def test_oversized_response_and_non_200_are_rejected(self):
        item = PLAN["sources"][1]
        fetch = lambda request, **kwargs: Response(b"x" * 12, request.full_url)
        with mock.patch.object(acceptance, "MAX_BODY", 10):
            with self.assertRaisesRegex(acceptance.AcceptanceError, "RESPONSE_TOO_LARGE"):
                acceptance.request_body(policy, item, item["url"], fetch)

    def test_network_context_missing_refuses_before_calls(self):
        fetch = mock.Mock()
        with self.assertRaisesRegex(acceptance.AcceptanceError, "AUTHORIZED_EXECUTION_CONTEXT_REQUIRED"):
            acceptance.run(PLAN, policy, network=True, opener=fetch)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
