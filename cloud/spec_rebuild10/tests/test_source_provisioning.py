import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cloud.spec_rebuild10 import sources
from cloud.spec_rebuild10.source_provisioning import (
    kia_2023_lpi_candidate, reviewed_file_collector, ReviewedSourceInput,
)
from cloud.spec_rebuild10.worker import CollectionRequest, SpecWorker
from cloud.spec_rebuild10.store import SpecStore


CAPTURE = ("The 2023 K5\n2.0 LPI\n전장 (mm): 4,905\n전폭 (mm): 1,860\n"
           "전고 (mm): 1,445\n축거 (mm): 2,850\n배기량 (cc): 1,999\n"
           "최고 출력 (ps): 146\n최대 토크 (kgf.m): 19.5\n자동: 6단\n").encode()


class SourceProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.payload = kia_2023_lpi_candidate(CAPTURE)
        self.access = sources.AccessGrant("kia_kr", True, True, True, "SYNTHETIC_TEST_GRANT")
        capture = self.base / "capture.txt"
        capture.write_bytes(CAPTURE)
        normalized = self.base / "candidate.json"
        encoded = json.dumps(self.payload, ensure_ascii=False).encode()
        normalized.write_bytes(encoded)
        digest = hashlib.sha256(CAPTURE).hexdigest()
        self.entry = ReviewedSourceInput(capture, normalized, digest,
            hashlib.sha256(encoded).hexdigest(),
            sources.ImportAuthorization("kia_kr", "SYNTHETIC_TEST_REVIEW", digest))

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **changes):
        identity = dict(self.payload["identity"], **changes)
        return CollectionRequest("kia_kr", "UA-0099", 1, "a" * 64, identity, 15)

    def binding(self, entries=None):
        return reviewed_file_collector("kia_kr", entries or [self.entry], access=self.access)

    def test_exact_eight_facts_and_units(self):
        rows = {row["key"]: row for row in self.payload["facts"]}
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows["power_ps"]["unit"], "PS")
        self.assertEqual(rows["length_mm"]["value"], 4905)
        self.assertEqual(rows["torque_kgfm"]["value"], 19.5)
        self.assertEqual(self.payload["document"]["capture_format"], "reviewed-text-excerpt-v1")

    def test_wrong_year_rejected(self):
        with self.assertRaisesRegex(sources.SourceError, "SCOPE_INVALID"):
            kia_2023_lpi_candidate(CAPTURE.replace(b"2023", b"2026"))

    def test_petrol_power_not_imported_as_lpi(self):
        with self.assertRaisesRegex(sources.SourceError, "VARIANT_MISMATCH"):
            kia_2023_lpi_candidate(CAPTURE.replace(b"146", b"160"))

    def test_html_not_a_reviewed_excerpt(self):
        with self.assertRaisesRegex(sources.SourceError, "FORMAT_INVALID"):
            kia_2023_lpi_candidate(b"<script>" + CAPTURE)

    def test_unknown_fields_fail_instead_of_shifted_columns(self):
        with self.assertRaisesRegex(sources.SourceError, "SCHEMA_CHANGED"):
            kia_2023_lpi_candidate(CAPTURE.replace(b"1,860", b"unknown"))

    def test_file_collector_feeds_real_parser(self):
        result = self.binding().collect(self.request())
        facts = sources.parse_normalized_import("kia_kr", result.payload,
            self.request().identity, access=self.access, authorization=result.authorization)
        self.assertEqual(len(sources.resolve_facts(facts, self.request().identity)["accepted"]), 8)

    def test_changed_capture_rejected(self):
        binding = self.binding()
        self.entry.capture_path.write_bytes(CAPTURE + b"\n")
        with self.assertRaisesRegex(sources.SourceError, "FILE_CHANGED"):
            binding.collect(self.request())

    def test_changed_payload_rejected(self):
        binding = self.binding()
        self.entry.payload_path.write_text("{}")
        with self.assertRaisesRegex(sources.SourceError, "FILE_CHANGED"):
            binding.collect(self.request())

    def test_other_year_returns_no_match(self):
        self.assertEqual(self.binding().collect(self.request(year=2019)).outcome, "NO_MATCH")

    def test_market_is_not_inferred(self):
        with self.assertRaisesRegex(sources.SourceError, "IDENTITY_INCOMPLETE"):
            self.binding().collect(self.request(market=""))

    def test_rounded_displacement_does_not_match(self):
        self.assertEqual(self.binding().collect(self.request(engine_cc=2000)).outcome, "NO_MATCH")

    def test_two_documents_are_ambiguous(self):
        with self.assertRaisesRegex(sources.SourceError, "AMBIGUOUS"):
            self.binding([self.entry, self.entry]).collect(self.request())

    def test_owner_selection_cannot_forge_supplier_rights(self):
        with self.assertRaisesRegex(sources.SourceError, "RIGHTS_INCOMPLETE"):
            reviewed_file_collector("kia_kr", [self.entry],
                access=sources.AccessGrant("kia_kr", reference="OWNER_APPROVED_SELECTION"))

    def test_real_worker_retains_verified_local_facts_without_publication(self):
        with SpecStore(self.base / "store.sqlite") as store:
            store.upsert_vehicle("UA-0099", self.payload["identity"])
            report = SpecWorker(store, {"kia_kr": self.binding()}).run_once()
            self.assertFalse(report["publication_performed"])
            self.assertEqual(len(store.get_facts("UA-0099")), 8)


if __name__ == "__main__":
    unittest.main()
