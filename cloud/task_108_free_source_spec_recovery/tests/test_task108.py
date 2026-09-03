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
        cls.operator_review_queue = task108.load_json(task108.OPERATOR_REVIEW_PATH)
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
        for item in self.report["enriched_cards"]:
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
        self.assertEqual({item["auto_number"] for item in zero}, {"UA-0014", "UA-0016"})
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
        self.assertEqual(self.report["status"], "CANARY_PASS_LIVE_REMEDIATION_REQUIRED")
        self.assertEqual(self.report["safe_to_publish_anything"], "NO")

    def test_21_operator_instruction_rows_are_removed_exactly(self):
        source = (
            '<div class="tehstr"><div class="m">•</div><div>Полезный текст.</div></div>'
            '<div class="tehstr"><div class="m">•</div><div>Чтобы изменить — пришлите новый текст. '
            'Он полностью заменит нынешний. Каждый пункт с новой строки.</div></div>'
            '<div class="tehstr"><div class="m">•</div><div>Пришлите новое значение текстом или голосом.</div></div>'
        )
        cleaned, removed = task108.strip_operator_instruction_rows(source)
        self.assertEqual(removed, 2)
        self.assertIn("Полезный текст", cleaned)
        self.assertFalse(task108.has_operator_instruction_leak(cleaned))

    def test_22_live_audit_rejects_empty_shells_and_leaks(self):
        gate = self.report["live_audit_gate"]
        self.assertEqual(gate["status"], "FAIL")
        self.assertEqual(gate["card_count"], 16)
        self.assertEqual(len(gate["empty_spec_cards"]), 15)
        self.assertIn("EMPTY_SPEC:UA-0005", gate["issues"])
        self.assertIn("EMPTY_SPEC_BLOCK_VISIBLE:UA-0005", gate["issues"])
        self.assertIn("OPERATOR_INSTRUCTION_LEAK:UA-0005", gate["issues"])

    def test_23_live_home_and_catalog_counts_match(self):
        issues = self.report["live_audit_gate"]["issues"]
        self.assertFalse(any(item.startswith("HOME_CATALOG_COUNT_MISMATCH") for item in issues))

    def test_24_every_enrichment_source_has_valid_claim_evidence(self):
        for source in self.policy["sources"]:
            if not source["allow_enrichment"]:
                continue
            evidence, errors = task108.load_source_evidence(source)
            self.assertEqual(errors, [], source["id"])
            self.assertIsNotNone(evidence)
            self.assertGreater(len(evidence["claims"]), 0)

    def test_25_tampered_evidence_hash_rejects_all_dependent_facts(self):
        policy = deepcopy(self.policy)
        source = task108.policy_index(policy)["MB_UK_PRICE_LIST_2013_MIRROR"]
        source["evidence_sha256"] = "0" * 64
        result = task108.process_bundle(self.cards["UA-0005"], self.bundles["UA-0005"], policy)
        self.assertEqual(result["status"], "REVIEW_REQUIRED_EMPTY")
        reasons = [reason for item in result["rejected"] for reason in item["reasons"]]
        self.assertIn("MB_UK_PRICE_LIST_2013_MIRROR:SOURCE_EVIDENCE_HASH_MISMATCH", reasons)

    def test_26_source_must_contain_exact_claim_value(self):
        bundle = deepcopy(self.bundles["UA-0005"])
        bundle["facts"][0]["value"] = 81
        result = task108.process_bundle(self.cards["UA-0005"], bundle, self.policy)
        rejected = next(item for item in result["rejected"] if item["code"] == "max_power_kw")
        self.assertIn(
            "MB_UK_PRICE_LIST_2013_MIRROR:SOURCE_CLAIM_VALUE_MISMATCH",
            rejected["reasons"],
        )
        self.assertNotIn("max_power_kw", [item["code"] for item in result["facts"]])

    def test_27_source_evidence_cannot_escape_task_root(self):
        source = deepcopy(task108.policy_index(self.policy)["AUTOGIDAS_MB_2013"])
        source["evidence_path"] = "../../../../etc/passwd"
        _, errors = task108.load_source_evidence(source)
        self.assertEqual(errors, ["SOURCE_EVIDENCE_PATH_INVALID_OR_MISSING"])

    def test_28_blocked_pages_cannot_enrich(self):
        sources = task108.policy_index(self.policy)
        self.assertFalse(sources["AUTOMOBILE_CATALOG_MB_2013"]["allow_enrichment"])
        self.assertFalse(sources["DANAWA_SONATA_2018"]["allow_enrichment"])

    def test_29_three_w245_cards_share_exact_vin_type_fact_set(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        expected_codes = {
            item["code"] for item in self.fixture["fact_sets"]["MB_W245_245232_AUTOTRONIC"]
        }
        self.assertEqual(len(expected_codes), 22)
        for uid in ("UA-0002", "UA-0007", "UA-0008"):
            item = by_uid[uid]
            self.assertEqual(item["status"], "READY_FOR_OPERATOR_REVIEW")
            self.assertEqual(item["identity_status"], "MATCHED_BY_VIN_TYPE_PREFIX")
            self.assertEqual(item["verified_fact_count"], 22)
            self.assertEqual({fact["code"] for fact in item["facts"]}, expected_codes)
            self.assertEqual(item["rejected"], [])

    def test_30_shared_fact_set_refuses_inline_override(self):
        bundle = deepcopy(self.bundles["UA-0002"])
        bundle["facts"] = [{"code": "length_mm"}]
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_INLINE_AND_SHARED_FACTS"):
            task108.expand_bundle(bundle, self.fixture)

    def test_31_source_year_range_mismatch_rejects_w245_claims(self):
        bundle = task108.expand_bundle(self.bundles["UA-0002"], self.fixture)
        card = deepcopy(self.cards["UA-0002"])
        bundle["identity"]["year"] = "2012"
        card["year"] = "2012"
        result = task108.process_bundle(card, bundle, self.policy)
        self.assertEqual(result["status"], "REVIEW_REQUIRED_EMPTY")
        reasons = [reason for item in result["rejected"] for reason in item["reasons"]]
        self.assertTrue(any("SOURCE_IDENTITY_YEAR_RANGE_MISMATCH" in reason for reason in reasons))

    def test_32_w245_does_not_claim_a_vpic_decode(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        for uid in ("UA-0002", "UA-0007", "UA-0008"):
            self.assertFalse(by_uid[uid]["vpic_usable_for_detailed_facts"])

    def test_33_operator_primary_field_block_has_priority_over_ready_thresholds(self):
        bundle = deepcopy(self.bundles["UA-0005"])
        bundle["identity_status"] = "BLOCKED_OPERATOR_PRIMARY_FIELDS"
        bundle["operator_review_reasons"] = ["MILEAGE_REQUIRES_CONFIRMATION"]
        result = task108.process_bundle(self.cards["UA-0005"], bundle, self.policy)
        self.assertEqual(result["status"], "REVIEW_REQUIRED_OPERATOR_FIELDS")
        self.assertEqual(result["operator_review_reasons"], ["MILEAGE_REQUIRES_CONFIRMATION"])
        self.assertFalse(result["publication_allowed"])

    def test_34_k5_2018_safe_common_facts_are_prepared_but_not_publishable(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        expected_codes = {
            item["code"]
            for item in self.fixture["fact_sets"]["KIA_K5_JF_LPI_AUTOMATIC_2018_SAFE_COMMON"]
        }
        self.assertEqual(len(expected_codes), 6)
        self.assertEqual(by_uid["UA-0009"]["status"], "REVIEW_REQUIRED_EXACT_TRIM")
        self.assertEqual(by_uid["UA-0009"]["verified_fact_count"], 6)
        self.assertEqual({item["code"] for item in by_uid["UA-0009"]["facts"]}, expected_codes)
        self.assertEqual(by_uid["UA-0012"]["status"], "REVIEW_REQUIRED_OPERATOR_FIELDS")
        self.assertEqual(by_uid["UA-0012"]["verified_fact_count"], 6)
        self.assertEqual(
            by_uid["UA-0012"]["operator_review_reasons"],
            ["MILEAGE_342_REQUIRES_CONFIRMATION"],
        )
        self.assertFalse(by_uid["UA-0009"]["publication_allowed"])
        self.assertFalse(by_uid["UA-0012"]["publication_allowed"])

    def test_35_k5_trim_dependent_values_stay_in_conflict_quarantine(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        for uid in ("UA-0009", "UA-0012"):
            codes = {item["code"] for item in by_uid[uid]["facts"]}
            self.assertNotIn("max_power_ps", codes)
            self.assertNotIn("height_mm", codes)
            self.assertNotIn("combined_consumption_kmpl", codes)
            rejected = {item["code"] for item in by_uid[uid]["rejected"]}
            self.assertTrue({"max_power_ps", "height_mm", "combined_consumption_kmpl"} <= rejected)

    def test_36_operator_review_queue_matches_current_crm_values_exactly(self):
        expected = {
            ("UA-0012", "mileage_km", "342"),
            ("UA-0013", "year", '"2015"'),
            ("UA-0014", "engine_cc", "1645"),
            ("UA-0016", "year", '"1999"'),
            ("UA-0016", "mileage_km", "353"),
        }
        actual = {
            (item["auto_number"], item["field"], task108.canonical_json(item["observed_value"]))
            for item in self.operator_review_queue["items"]
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            task108.validate_operator_review_queue(self.operator_review_queue, self.cards), []
        )

    def test_37_operator_review_queue_cannot_contain_replacements(self):
        forbidden = {
            "replacement",
            "replacement_value",
            "suggested_value",
            "normalized_value",
            "new_value",
        }
        for item in self.operator_review_queue["items"]:
            self.assertTrue(task108.is_protected_code(item["field"]))
            self.assertFalse(forbidden.intersection(item))
            self.assertEqual(item["status"], "REVIEW_REQUIRED")

    def test_38_operator_review_cards_remain_blocked_and_visible_in_report(self):
        by_uid = {item["auto_number"]: item for item in self.report["batch_status"]}
        self.assertEqual(by_uid["UA-0012"]["status"], "REVIEW_REQUIRED_OPERATOR_FIELDS")
        self.assertEqual(by_uid["UA-0013"]["status"], "REVIEW_REQUIRED_OPERATOR_FIELDS")
        self.assertEqual(by_uid["UA-0014"]["status"], "REVIEW_REQUIRED_EMPTY")
        self.assertEqual(by_uid["UA-0016"]["status"], "REVIEW_REQUIRED_EMPTY")
        self.assertEqual(by_uid["UA-0013"]["operator_review_fields"], ["year"])
        self.assertEqual(by_uid["UA-0014"]["operator_review_fields"], ["engine_cc"])
        self.assertEqual(by_uid["UA-0016"]["operator_review_fields"], ["mileage_km", "year"])
        self.assertTrue(self.report["invariant_checks"]["operator_review_queue_valid"])
        self.assertTrue(self.report["invariant_checks"]["operator_review_cards_blocked"])
        self.assertEqual(self.report["operator_review_errors"], [])

    def test_39_three_2019_k5_cards_have_only_cross_checked_safe_facts(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        expected_codes = {
            item["code"]
            for item in self.fixture["fact_sets"][
                "KIA_K5_JF_LPI_AUTOMATIC_2019_SAFE_COMMON"
            ]
        }
        self.assertEqual(
            expected_codes,
            {"length_mm", "width_mm", "wheelbase_mm", "front_brakes", "rear_brakes"},
        )
        for uid in ("UA-0003", "UA-0004", "UA-0006"):
            item = by_uid[uid]
            self.assertEqual(item["status"], "REVIEW_REQUIRED_EXACT_TRIM")
            self.assertEqual(item["verified_fact_count"], 5)
            self.assertEqual({fact["code"] for fact in item["facts"]}, expected_codes)
            self.assertFalse(item["publication_allowed"])

    def test_40_2019_k5_ambiguous_engine_and_height_never_render(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        for uid in ("UA-0003", "UA-0004", "UA-0006"):
            accepted = {item["code"] for item in by_uid[uid]["facts"]}
            rejected = {item["code"] for item in by_uid[uid]["rejected"]}
            self.assertNotIn("max_power_ps", accepted)
            self.assertNotIn("height_mm", accepted)
            self.assertTrue({"max_power_ps", "height_mm"} <= rejected)

    def test_41_matching_2018_k5_reuses_only_the_safe_common_fact_set(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        reference_codes = {
            fact["code"]
            for fact in self.fixture["fact_sets"][
                "KIA_K5_JF_LPI_AUTOMATIC_2018_SAFE_COMMON"
            ]
        }
        item = by_uid["UA-0010"]
        self.assertEqual(item["status"], "REVIEW_REQUIRED_EXACT_TRIM")
        self.assertEqual(item["verified_fact_count"], 6)
        self.assertEqual({fact["code"] for fact in item["facts"]}, reference_codes)
        self.assertFalse(item["publication_allowed"])

    def test_42_two_sonata_cards_share_an_immutable_safe_fact_set(self):
        by_uid = {item["auto_number"]: item for item in self.report["enriched_cards"]}
        expected_codes = {
            fact["code"]
            for fact in self.fixture["fact_sets"][
                "HYUNDAI_SONATA_LF_LPI_AUTOMATIC_2018_SAFE_COMMON"
            ]
        }
        self.assertEqual(len(expected_codes), 6)
        for uid in ("UA-0011", "UA-0015"):
            item = by_uid[uid]
            self.assertEqual(item["status"], "REVIEW_REQUIRED_EXACT_TRIM")
            self.assertEqual({fact["code"] for fact in item["facts"]}, expected_codes)
            self.assertFalse(item["publication_allowed"])

    def test_43_e220d_exact_operator_fields_prepare_ten_cross_checked_facts(self):
        item = next(
            item for item in self.report["enriched_cards"] if item["auto_number"] == "UA-0001"
        )
        expected_codes = {
            fact["code"]
            for fact in self.fixture["fact_sets"]["MB_W213_E220D_2016_2020_SAFE_COMMON"]
        }
        self.assertEqual(item["status"], "READY_FOR_OPERATOR_REVIEW")
        self.assertEqual(item["identity_score"], 1.0)
        self.assertEqual(item["verified_fact_count"], 10)
        self.assertEqual({fact["code"] for fact in item["facts"]}, expected_codes)
        self.assertFalse(item["publication_allowed"])

    def test_44_e220d_consumption_and_rear_brake_conflicts_stay_quarantined(self):
        item = next(
            item for item in self.report["enriched_cards"] if item["auto_number"] == "UA-0001"
        )
        accepted = {fact["code"] for fact in item["facts"]}
        rejected = {fact["code"] for fact in item["rejected"]}
        self.assertNotIn("combined_consumption_l_100km", accepted)
        self.assertNotIn("rear_brakes", accepted)
        self.assertTrue({"combined_consumption_l_100km", "rear_brakes"} <= rejected)

    def test_45_cyrillic_owner_model_matches_b_class_sources_without_crm_rewrite(self):
        self.assertEqual(task108._identity_token("Б-КЛАССА"), "bclass")
        self.assertEqual(task108._identity_token("B-Class W246"), "bclassw246")
        card = self.cards["UA-0013"]
        self.assertEqual(card["model"], "Б-КЛАССА")

    def test_46_b200d_prepares_only_cross_checked_facts_and_stays_blocked(self):
        item = next(
            item for item in self.report["enriched_cards"] if item["auto_number"] == "UA-0013"
        )
        expected_codes = {
            fact["code"]
            for fact in self.fixture["fact_sets"]["MB_W246_B200D_DCT_2014_2018_SAFE_COMMON"]
        }
        self.assertEqual(item["status"], "REVIEW_REQUIRED_OPERATOR_FIELDS")
        self.assertEqual(item["identity_score"], 1.0)
        self.assertEqual(item["verified_fact_count"], 19)
        self.assertEqual({fact["code"] for fact in item["facts"]}, expected_codes)
        self.assertEqual(
            item["operator_review_reasons"],
            ["YEAR_2015_CONFLICTS_WITH_VIN_MODEL_YEAR_2016"],
        )
        self.assertFalse(item["publication_allowed"])

    def test_47_b200d_source_conflicts_are_quarantined(self):
        item = next(
            item for item in self.report["enriched_cards"] if item["auto_number"] == "UA-0013"
        )
        accepted = {fact["code"] for fact in item["facts"]}
        rejected = {fact["code"] for fact in item["rejected"]}
        conflicts = {
            "length_mm",
            "wheelbase_mm",
            "curb_weight_kg",
            "trunk_min_l",
            "max_speed_kmh",
            "acceleration_0_100_s",
            "combined_consumption_l_100km",
        }
        self.assertFalse(conflicts & accepted)
        self.assertTrue(conflicts <= rejected)


if __name__ == "__main__":
    unittest.main()
