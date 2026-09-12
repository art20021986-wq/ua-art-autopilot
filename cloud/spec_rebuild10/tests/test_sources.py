import copy
import importlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sources as s

IDENTITY = s.VehicleIdentity(vin="KNAGU416BKA900010", make="Kia", model="K5", year=2019,
                            market="KR", fuel="LPG", gearbox="automatic")
URLS = {"kia_kr": "https://www.kia.com/kr/vehicles/k5/specification",
        "danawa": "https://auto.danawa.com/auto/?Model=3260&Tab=spec&Work=model",
        "carisyou": "https://www.carisyou.com/car/5217/Spec/52976"}
DOCUMENT_SHA = "a" * 64


def grant(source="kia_kr"):
    return s.AccessGrant(source, True, True, True, "TEST-ONLY-SUPPLIER-RIGHTS")


def payload(source="kia_kr", key="length_mm", value=4855, category="technical"):
    return {"schema": "ua-art.normalized-source.v1", "source_id": source,
        "identity": vars(IDENTITY).copy(), "document": {"url": URLS[source],
            "sha256": DOCUMENT_SHA, "evidence_kind": "manufacturer_document" if source == "kia_kr" else "catalog_record"},
        "facts": [{"key": key, "value": value, "unit": "mm", "label_uk": "Довжина",
                   "label_ru": "Длина", "category": category}]}


def parse(source="kia_kr", value=None):
    return s.parse_normalized_import(source, value or payload(source), IDENTITY,
        access=grant(source), authorization=s.ImportAuthorization(source, "FIXTURE-NORMALIZER", DOCUMENT_SHA))


class SourceTests(unittest.TestCase):
    def assertCode(self, code, fn):
        with self.assertRaises(s.SourceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_exact_ten_are_not_live_pass(self):
        registry = s.load_registry()
        self.assertEqual(set(registry), s.APPROVED_IDS)
        self.assertEqual(len(registry), 10)
        self.assertEqual(s.readiness_report()["live_pass"], 0)
        self.assertTrue(all(x.live_acceptance == "NOT_TESTED" for x in registry.values()))
        self.assertEqual(sum(x.provisioning == "NOT_PROVISIONED" for x in registry.values()), 9)

    def test_old_registry_sources_rejected(self):
        for source in ("carwiki", "carfolio", "encycarpedia", "automobile_catalog"):
            with self.subTest(source=source):
                self.assertCode("SOURCE_NOT_APPROVED", lambda: s.validate_source_url(source, "https://example.com/"))

    def test_registry_duplicate_rejected(self):
        raw = json.loads(Path(s.__file__).with_name("sources.json").read_text())
        raw["sources"][0] = raw["sources"][1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(raw))
            self.assertCode("REGISTRY_MUST_CONTAIN_EXACT_APPROVED_TEN", lambda: s.load_registry(path))

    def test_import_has_no_network(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            spec = importlib.util.spec_from_file_location("sources_no_network_check", s.__file__)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
                self.assertEqual(len(module.load_registry()), 10)
            finally:
                del sys.modules[spec.name]

    def test_url_rejects_adversarial_hosts_and_paths(self):
        urls = ("http://www.kia.com/kr/a", "https://www.kia.com.evil.test/kr/a",
            "https://www.kia.com@127.0.0.1/kr/a", "https://127.0.0.1/kr/a",
            "https://[::1]/kr/a", "https://localhost/kr/a", "https://169.254.169.254/kr/a",
            "https://www.kia.com:444/kr/a", "https://www.kia.com./kr/a",
            "https://www.kia.com/kr/../secret", "https://www.kia.com/kr/%2e%2e/secret",
            "https://www.kia.com/kr/%252e%252e/secret", "https://www.kia.com/kr/a%00b",
            "https://www.kia.com/kr/a\\b", "https://www.kia.com/kr/a#credentials",
            "https://www.kia.com/private/a", "https://www.kia.com/kr/a?api_key=SECRET",
            "https://www.kia.com/kr/a?redirect=https://evil.test", "https://www.kia.com/kr/a\n")
        for url in urls:
            with self.subTest(url=url), self.assertRaises(s.SourceError):
                s.validate_source_url("kia_kr", url)

    def test_supplier_grant_required_before_transport(self):
        called = []
        self.assertCode("SUPPLIER_NOT_PROVISIONED", lambda: s.fetch_source("kia_kr", URLS["kia_kr"],
            transport=lambda request: called.append(request)))
        self.assertEqual(called, [])

    def test_no_default_network(self):
        self.assertCode("TRANSPORT_NOT_CONFIGURED", lambda: s.fetch_source("vpic",
            "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/KNAGU416BKA900010?format=json"))

    def test_incomplete_storage_or_display_rights_rejected(self):
        for access in (s.AccessGrant("kia_kr", True, False, True, "x"),
                       s.AccessGrant("kia_kr", True, True, False, "x"), grant("danawa")):
            with self.subTest(access=access), self.assertRaises(s.SourceError):
                s.fetch_source("kia_kr", URLS["kia_kr"], access=access, transport=lambda _: s.Response(200, b""))

    def test_redirect_only_approved_audi_host_and_no_credentials(self):
        requests = []
        def transport(request):
            requests.append(request)
            return (s.Response(302, b"", {"Location": "https://www.audi.com/en/a6/"})
                    if len(requests) == 1 else s.Response(200, b"ok"))
        access = s.AccessGrant("audi_official", True, True, True, "fixture", {"Authorization": "SECRET"})
        self.assertEqual(s.fetch_source("audi_official", "https://www.audi-mediacenter.com/en/audi-a6-40",
                                       access=access, transport=transport).body, b"ok")
        self.assertEqual(requests[1].headers, {})
        self.assertNotIn("SECRET", repr(requests[0]))
        self.assertNotIn("SECRET", repr(access))

    def test_foreign_redirect_and_retry_are_forbidden(self):
        requests = []
        def transport(request):
            requests.append(request)
            return s.Response(302, b"", {"location": "https://evil.test/path"})
        self.assertCode("URL_HOST_NOT_APPROVED", lambda: s.fetch_source("kia_kr", URLS["kia_kr"],
                       access=grant(), transport=transport))
        self.assertEqual(len(requests), 1)

    def test_transport_error_does_not_expose_secret(self):
        def transport(request):
            raise RuntimeError("api_key=SECRET PRIVATE RESPONSE")
        self.assertCode("TRANSPORT_FAILED", lambda: s.fetch_source("kia_kr", URLS["kia_kr"],
                       access=grant(), transport=transport))

    def test_response_limit(self):
        self.assertCode("RESPONSE_TOO_LARGE", lambda: s.fetch_source("kia_kr", URLS["kia_kr"],
            access=grant(), max_bytes=3, transport=lambda _: s.Response(200, b"1234")))

    def test_redirect_loop(self):
        self.assertCode("REDIRECT_LOOP", lambda: s.fetch_source("kia_kr", URLS["kia_kr"],
            access=grant(), transport=lambda _: s.Response(302, b"", {"location": URLS["kia_kr"]})))

    def test_import_requires_out_of_band_trust(self):
        self.assertCode("TRUSTED_NORMALIZER_REQUIRED", lambda: s.parse_normalized_import(
            "kia_kr", payload(), IDENTITY, access=grant()))

    def test_import_source_impersonation(self):
        data = payload()
        data["source_id"] = "danawa"
        self.assertCode("SOURCE_IMPERSONATION", lambda: parse(value=data))
        data = payload()
        data["facts"][0]["source_id"] = "danawa"
        self.assertCode("SOURCE_IMPERSONATION", lambda: parse(value=data))

    def test_document_hash_mismatch(self):
        data = payload()
        data["document"]["sha256"] = "b" * 64
        self.assertCode("DOCUMENT_HASH_MISMATCH", lambda: parse(value=data))

    def test_exact_identity_rejects_wrong_variant(self):
        for key, value in (("market", "US"), ("fuel", "petrol"), ("gearbox", "manual"),
                           ("year", 2020), ("model", "Optima"), ("make", "Hyundai")):
            data = payload()
            data["identity"][key] = value
            with self.subTest(key=key):
                self.assertCode("IDENTITY_MISMATCH", lambda: parse(value=data))

    def test_missing_market_rejected(self):
        data = payload()
        data["identity"]["market"] = ""
        self.assertCode("IDENTITY_INCOMPLETE", lambda: parse(value=data))

    def test_zero_unknown_and_false_are_distinct(self):
        self.assertEqual(parse(value=payload(key="mileage_km", value=0))[0]["value"], 0)
        self.assertEqual(parse(value=payload(key="mileage_km", value="unknown")), [])
        self.assertEqual(parse(value=payload(key="mileage_km", value=None)), [])
        self.assertCode("ZERO_OR_NEGATIVE_PLACEHOLDER_FORBIDDEN", lambda: parse(value=payload(value=0)))
        data = payload(key="sunroof", value=False, category="equipment")
        data["document"]["evidence_kind"] = "vehicle_document"
        self.assertIs(parse(value=data)[0]["value"], False)

    def test_equipment_requires_matching_vehicle_document(self):
        data = payload(key="sunroof", value=True, category="equipment")
        self.assertCode("EQUIPMENT_REQUIRES_VEHICLE_EVIDENCE", lambda: parse(value=data))
        data["document"]["evidence_kind"] = "vehicle_document"
        data["identity"]["vin"] = ""
        self.assertCode("VEHICLE_EVIDENCE_REQUIRES_EXACT_VIN", lambda: parse(value=data))

    def test_html_in_fact_rejected(self):
        self.assertCode("FACT_TEXT_INVALID", lambda: parse(value=payload(key="engine", value="<script>ads</script>")))

    def test_exact_manufacturer_or_two_independent_catalogs(self):
        self.assertEqual(len(s.resolve_facts(parse(), IDENTITY)["accepted"]), 1)
        danawa = parse("danawa")
        self.assertEqual(s.resolve_facts(danawa, IDENTITY)["accepted"], [])
        self.assertEqual(s.resolve_facts(danawa + danawa, IDENTITY)["accepted"], [])
        both = s.resolve_facts(danawa + parse("carisyou"), IDENTITY)
        self.assertEqual(len(both["accepted"]), 1)
        self.assertEqual(both["accepted"][0]["provenance"]["corroborating_sources"], ["carisyou", "danawa"])

    def test_conflict_remains_pending(self):
        data = payload("danawa", value=4900)
        result = s.resolve_facts(parse() + parse("danawa", data), IDENTITY)
        self.assertEqual(result["accepted"], [])
        self.assertEqual({x["reason"] for x in result["pending"]}, {"SOURCE_CONFLICT"})

    def test_origin_group_impersonation_rejected(self):
        row = parse("danawa")[0]
        row["provenance"]["origin_group"] = "kia_manufacturer"
        self.assertEqual(s.resolve_facts([row], IDENTITY)["rejected"][0]["reason"], "UNTRUSTED_CANDIDATE")

    def test_failed_refresh_retains_existing_and_manual_priority(self):
        previous = [{"key": "length_mm", "value": 4860, "manual_override": True}]
        frozen = copy.deepcopy(previous)
        self.assertEqual(s.retain_on_failed_refresh(previous, error="SOURCE_HTTP_ERROR"), previous)
        self.assertEqual(s.retain_on_failed_refresh(previous, resolved={"accepted": []}), previous)
        self.assertEqual(s.retain_on_failed_refresh(previous, resolved=s.resolve_facts(parse(), IDENTITY)), previous)
        self.assertEqual(previous, frozen)

    def test_vpic_identity_is_not_full_spec_or_equipment(self):
        data = {"Results": [{"VIN": IDENTITY.vin, "ErrorCode": "0", "Make": "KIA", "Model": "K5",
                             "ModelYear": "2019", "DisplacementL": "2.0", "BodyClass": "Sedan"}]}
        rows = s.parse_vpic(data, IDENTITY)
        self.assertTrue(rows)
        self.assertTrue(all(x["verification_status"] == "IDENTITY_ONLY" for x in rows))
        self.assertEqual(s.resolve_facts(rows, IDENTITY)["accepted"], [])
        self.assertEqual(len(s.resolve_facts(rows, IDENTITY)["pending"]), len(rows))

    def test_vpic_incomplete_wrong_vin_and_wrong_year_rejected(self):
        row = {"VIN": IDENTITY.vin, "ErrorCode": "0", "Make": "KIA", "Model": "K5", "ModelYear": "2019"}
        for change, code in (({"ErrorCode": "0,5"}, "VPIC_DECODE_INCOMPLETE"),
                             ({"VIN": "KNAGU416BKA324446"}, "VIN_MISMATCH"),
                             ({"ModelYear": "2020"}, "IDENTITY_MISMATCH")):
            with self.subTest(change=change):
                self.assertCode(code, lambda: s.parse_vpic({"Results": [dict(row, **change)]}, IDENTITY))


if __name__ == "__main__":
    unittest.main()
