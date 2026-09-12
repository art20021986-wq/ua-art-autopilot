"""Offline vPIC response-binding regressions for the next joint candidate."""
import hashlib
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))
from repair_vpic_identity import patch_vpic_identity

SOURCE = (ROOT / "runtime/source_policy.py").read_text()
PATCHED = patch_vpic_identity(SOURCE)
policy = types.ModuleType("source_policy_vpic_binding_fixture")
sys.modules[policy.__name__] = policy
exec(compile(PATCHED, "source_policy.py", "exec"), policy.__dict__)
VIN = "KNAXX0000J0000001"
CAR = {"vin": VIN, "brand": "Kia", "model": "K5", "year": "2018", "fuel": "LPI", "engine_cc": 1999}
ROW = {"VIN": VIN, "Make": "KIA", "Model": "K5", "ModelYear": "2018", "ErrorCode": "0", "Doors": "4"}


class BindingTest(unittest.TestCase):
    def test_same_make_model_year_wrong_vin_is_rejected(self):
        self.assertTrue(policy.vpic_identity_matches(CAR, ROW))
        self.assertFalse(policy.vpic_identity_matches(CAR, dict(ROW, VIN="KNAXX0000J0000002")))

    def test_missing_malformed_frame_or_empty_vin_is_rejected(self):
        for bad in (None, "", "NHP10-1234567", "NOT-A-VIN", "KNAXX0000J000000I"):
            with self.subTest(bad=bad):
                self.assertFalse(policy.vpic_identity_matches(CAR, dict(ROW, VIN=bad)))
        self.assertFalse(policy.vpic_identity_matches({k: v for k, v in CAR.items() if k != "vin"}, ROW))

    def test_existing_make_model_year_and_error_guards_remain(self):
        for key, value in (("Make", "Hyundai"), ("Model", "Sonata"), ("ModelYear", "2023"), ("ErrorCode", "0,1")):
            self.assertFalse(policy.vpic_identity_matches(CAR, dict(ROW, **{key: value})))

    def test_decoder_keeps_actual_returned_identity_and_facts(self):
        class Response(io.BytesIO):
            status = 200
            def geturl(self):
                return "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
        seen = []
        def opener(request, **kwargs):
            seen.append(request.full_url)
            return Response(json.dumps({"Results": [dict(ROW, VIN="KNAXX0000J0000002")]}).encode())
        identity, facts = policy.decode_vpic(CAR, opener=opener)
        self.assertEqual(identity["VIN"], "KNAXX0000J0000002")
        self.assertTrue(facts)
        self.assertFalse(policy.vpic_identity_matches(CAR, identity))
        self.assertEqual(len(seen), 1)
        self.assertIn(VIN, seen[0])

    def test_patch_rejects_drift_and_repeat(self):
        for source in (SOURCE + "\n", PATCHED):
            with self.assertRaisesRegex(ValueError, "VPIC_SOURCE_SHA_MISMATCH"):
                patch_vpic_identity(source)
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(),
                         "e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d")
        self.assertEqual(policy.SOURCE_DOMAINS, (
            "vpic.nhtsa.dot.gov", "auto-data.net", "carwiki.co.kr", "auto.danawa.com", "carisyou.com",
            "ultimatespecs.com", "automobile-catalog.com", "cars-data.com", "carfolio.com", "encycarpedia.com"))

    def test_enrichment_does_not_accept_wrong_vehicle_facts(self):
        class Response(io.BytesIO):
            status = 200
            def geturl(self):
                return "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
        body = json.dumps({"Results": [dict(ROW, VIN="KNAXX0000J0000002")]}).encode()
        with mock.patch.object(policy, "known_urls", return_value=[]), mock.patch.object(policy, "discover_urls", return_value=[]):
            result = policy.enrich(CAR, opener=lambda request, **kwargs: Response(body))
        self.assertEqual(result["sources"]["vpic.nhtsa.dot.gov"]["status"], "IDENTITY_MISMATCH")
        self.assertEqual(result["sources"]["vpic.nhtsa.dot.gov"]["facts"], 0)
        self.assertEqual(result["facts"], [])


if __name__ == "__main__":
    unittest.main()
