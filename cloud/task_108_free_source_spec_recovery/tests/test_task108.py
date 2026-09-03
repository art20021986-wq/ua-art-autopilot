from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import task108  # noqa: E402


class Task108ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = task108.load_json(task108.POLICY_PATH)
        cls.fixture = task108.load_json(task108.FIXTURE_PATH)
        cls.before = task108.load_json(task108.BEFORE_PATH)
        cls.report = task108.run()
        cls.cards = {item["auto_number"]: item for item in cls.before["cards"]}
        cls.bundles = {item["auto_number"]: item for item in cls.fixture["bundles"]}

    def test_01_snapshot_contains_exactly_16_unique_cards(self):
        uids = [item["auto_number"] for item in self.before["cards"]]
        self.assertEqual(uids, [f"UA-{index:04d}" for index in range(1, 17)])
        self.assertEqual(len(uids), len(set(uids)))

    def test_02_policy_forbids_paid_api_and_russian_sites(self):
        self.assertFalse(self.policy["paid_api_allowed"])
        self.assertFalse(self.policy["russian_sites_allowed"])
        for source in self.policy["sources"]:
            self.assertIn(source["cost"], {"free", "free_web"})
            self.assertNotEqual(source["country"], "RU")
            self.assertFalse(source["domain"].endswith(".ru"))

    def test_03_only_vpic_has_runtime_fetch_enabled(self):
        enabled = [item["id"] for item in self.policy["sources"] if item["runtime_fetch"]]
        self.assertEqual(enabled, ["NHTSA_VPIC"])

    def test_04_danawa_is_conflict_observation_not_enrichment(self):
        item = task108.policy_index(self.policy)["DANAWA_SONATA_2018"]
        self.assertFalse(item["allow_enrichment"])
        self.assertEqual(item["role"], "conflict_observation_only")

    def test_05_protected_semantic_codes_are_blocked(self):
        for code in (
            "price_usd",
            "purchase_price",
            "mileage_km",
            "engine_cc",
            "vin",
            "client_phone",
            "accident_history",
            "shipping_eta",
        ):
            self.assertTrue(task108.is_protected_code(code), code)
        self.assertFalse(task108.is_protected_code("wheelbase_mm"))

    def test_06_empty_bundle_is_never_pass(self):
        bundle = deepcopy(self.bundles["UA-0005"])
        bundle["facts"] = []
        bundle["conflicts"] = []
        result = task108.process_bundle(self.cards["UA-0005"], bundle, self.policy)
        self.assertEqual(result["status"], "REVIEW_REQUIRED_EMPTY")
        self.assertEqual(result["verified_fact_count"], 0)
        self.assertNotIn("PASS", result["status"])

    def test_07_vin_mismatch_blocks_identity(self):
        card = deepcopy(self.cards["UA-0005"])
        card["vin"] = "WDD00000000000000"
        result = task108.process_bundle(card, self.bundles["UA-0005"], self.policy)
        self.assertEqual(result["identity_score"], 0.0)
        self.assertIn("vin", result["identity_mismatches"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED_IDENTITY_MISMATCH")

    def test_08_conflicting_semantic_duplicate_is_quarantined(self):
        bundle = deepcopy(self.bundles["UA-0005"])
        first = deepcopy(bundle["facts"][0])
        first["value"] = 999
        bundle["facts"].append(first)
        result = task108.process_bundle(self.cards["UA-0005"], bundle, self.policy)
        self.assertNotIn("max_power_kw", [item["code"] for item in result["facts"]])
        reasons = [reason for item in result["rejected"] for reason in item["reasons"]]
        self.assertIn("SEMANTIC_DUPLICATE_CONFLICT", reasons)

    def test_09_declared_source_conflicts_do_not_render(self):
        result = next(item for item in self.report["canaries"] if item["auto_number"] == "UA-0015")
        codes = {item["code"] for item in result["facts"]}
        self.assertNotIn("height_mm", codes)
        self.assertNotIn("combined_consumption_kmpl", codes)
        self.assertNotIn("curb_weight_kg", codes)
        self.assertNotIn("co2_g_km", codes)

    def test_10_renderer_hides_empty_block(self):
        self.assertEqual(task108.render_details(self.cards["UA-0005"], []), "")

    def test_11_renderer_is_server_side_indexable_and_url_free(self):
        result = next(item for item in self.report["canaries"] if item["auto_number"] == "UA-0005")
        document = task108.render_details(self.cards["UA-0005"], result["facts"])
        self.assertIn("<details>", document)
        self.assertIn("Дополнительная спецификация", document)
        self.assertIn('type="application/ld+json"', document)
        self.assertIn('"additionalProperty"', document)
        for fact in result["facts"]:
            for source in fact["sources"]:
                self.assertNotIn(source["url"], document)

    def test_12_renderer_has_one_row_per_semantic_code(self):
        for item in self.report["canaries"]:
            document = self.report["previews"][item["auto_number"]]
            codes = [fact["code"] for fact in item["facts"]]
            self.assertEqual(len(codes), len(set(codes)))
            payload = document.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
            properties = json.loads(payload)["additionalProperty"]
            self.assertEqual(len(properties), len(codes))

    def test_13_mobile_layout_wraps_long_values(self):
        css = task108.component_css()
        self.assertIn("@media(max-width:640px)", css)
        self.assertIn("grid-template-columns:minmax(0,1fr)", css)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn("word-break:break-word", css)

    def test_14_protected_projection_hash_is_unchanged(self):
        self.assertEqual(self.report["before_protected_sha256"], self.report["after_protected_sha256"])
        self.assertTrue(self.report["invariant_checks"]["protected_fields_unchanged"])

    def test_15_canary_outcomes_are_explicit(self):
        by_uid = {item["auto_number"]: item for item in self.report["canaries"]}
        self.assertEqual(by_uid["UA-0005"]["status"], "READY_FOR_OPERATOR_REVIEW")
        self.assertEqual(by_uid["UA-0015"]["status"], "REVIEW_REQUIRED_EXACT_TRIM")
        self.assertGreaterEqual(by_uid["UA-0005"]["verified_fact_count"], 5)
        self.assertGreaterEqual(by_uid["UA-0015"]["verified_fact_count"], 5)

    def test_16_zero_fact_batch_cards_are_review_required(self):
        zero = [item for item in self.report["batch_status"] if item["verified_fact_count"] == 0]
        self.assertEqual(len(zero), 14)
        self.assertTrue(all(item["status"] == "REVIEW_REQUIRED_EMPTY" for item in zero))
        self.assertEqual(self.report["empty_cards_passed"], [])

    def test_17_ua0009_gate_is_closed(self):
        self.assertEqual(self.report["ua0009_publication_readiness"], "FAIL")
        self.assertEqual(self.report["safe_to_publish_ua0009"], "NO")

    def test_18_production_and_autopublication_are_blocked(self):
        for key in (
            "production_authorized",
            "production_touched",
            "live_crm_write",
            "public_path_write",
            "services_restarted",
            "autopublication",
        ):
            self.assertFalse(self.report[key], key)
        self.assertEqual(self.report["safe_to_publish_anything"], "NO")

    def test_19_ten_runs_are_identical(self):
        self.assertEqual(self.report["determinism"]["runs"], 10)
        self.assertEqual(len(self.report["determinism"]["unique_hashes"]), 1)
        self.assertTrue(self.report["invariant_checks"]["ten_identical_runs"])

    def test_20_canary_pipeline_pass_does_not_claim_production_ready(self):
        self.assertEqual(self.report["status"], "CANARY_PASS_PRODUCTION_BLOCKED")
        self.assertEqual(self.report["safe_to_publish_anything"], "NO")


if __name__ == "__main__":
    unittest.main()
