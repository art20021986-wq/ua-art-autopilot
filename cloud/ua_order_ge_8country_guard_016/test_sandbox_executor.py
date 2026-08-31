#!/usr/bin/env python3
"""
Executable offline test suite for sandbox_executor.py.
Run with: python3 -m unittest cloud/ua_order_ge_8country_guard_016/test_sandbox_executor.py -v
or simply: python3 test_sandbox_executor.py

All tests are self-contained, stdlib-only, and perform no network or
production filesystem access.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sandbox_executor as se  # noqa: E402

HERE = Path(__file__).resolve().parent


class TestLanguageWhitelist(unittest.TestCase):
    def test_default_uk_on_missing(self):
        self.assertEqual(se.normalize_lang(None), "uk")
        self.assertEqual(se.normalize_lang(""), "uk")

    def test_ge_forbidden_as_lang_code(self):
        self.assertEqual(se.normalize_lang("ge"), "uk")
        self.assertEqual(se.normalize_lang("GE"), "uk")

    def test_whitelist_accepted_case_insensitive(self):
        for code in ("uk", "ru", "ka"):
            self.assertEqual(se.normalize_lang(code), code)
            self.assertEqual(se.normalize_lang(code.upper()), code)

    def test_unknown_falls_back_to_uk(self):
        self.assertEqual(se.normalize_lang("fr"), "uk")
        self.assertEqual(se.normalize_lang("xx"), "uk")


class TestCountryWhitelist(unittest.TestCase):
    def test_default_korea_on_missing(self):
        self.assertEqual(se.normalize_country(None), "korea")
        self.assertEqual(se.normalize_country(""), "korea")

    def test_unknown_falls_back_to_korea(self):
        self.assertEqual(se.normalize_country("mars"), "korea")

    def test_all_eight_countries_accepted(self):
        self.assertEqual(len(se.COUNTRY_WHITELIST), 8)
        for code in se.COUNTRY_WHITELIST:
            self.assertEqual(se.normalize_country(code), code)


class TestRoutes(unittest.TestCase):
    def test_route_format(self):
        route = se.build_route("canada", "ka")
        self.assertEqual(route, "podbor.html?strana=canada&lang=ka")

    def test_all_eight_routes_present(self):
        for code in se.COUNTRY_WHITELIST:
            route = se.build_route(code, "uk")
            self.assertIn(f"strana={code}", route)
            self.assertIn("lang=uk", route)

    def test_unknown_country_route_falls_back(self):
        route = se.build_route("atlantis", "ru")
        self.assertIn("strana=korea", route)


class TestCountryModelsConfig(unittest.TestCase):
    def setUp(self):
        self.data = se.load_country_models()

    def test_config_validates_clean(self):
        errs = se.validate_country_models(self.data)
        self.assertEqual(errs, [])

    def test_each_country_has_five_models(self):
        for code in se.COUNTRY_WHITELIST:
            models = self.data["countries"][code]["models"]
            self.assertEqual(len(models), 5)

    def test_total_models_is_forty(self):
        total = sum(len(self.data["countries"][c]["models"]) for c in se.COUNTRY_WHITELIST)
        self.assertEqual(total, 40)

    def test_uae_independent_of_usa(self):
        usa = self.data["countries"]["usa"]["models"]
        uae = self.data["countries"]["uae"]["models"]
        self.assertIsNot(usa, uae)

    def test_georgia_models_match_owner_approved_list(self):
        georgia = [m["name"] for m in self.data["countries"]["georgia"]["models"]]
        expected = [
            "Ford Fusion / Fusion Hybrid",
            "Toyota Camry",
            "Volkswagen Jetta",
            "Toyota RAV4 / RAV4 Hybrid",
            "Subaru Forester",
        ]
        self.assertEqual(georgia, expected)


class TestI18n(unittest.TestCase):
    def setUp(self):
        self.data = se.load_i18n()

    def test_three_languages_present(self):
        for lang in ("uk", "ru", "ka"):
            self.assertIn(lang, self.data)

    def test_ka_control_strings_exact_match(self):
        errs = se.validate_i18n(self.data)
        self.assertEqual(errs, [])

    def test_ka_strings_round_trip_utf8(self):
        for key, value in self.data["ka"].items():
            if isinstance(value, str):
                encoded = value.encode("utf-8")
                self.assertEqual(encoded.decode("utf-8"), value)


class TestNoUnsafeInnerHTML(unittest.TestCase):
    def test_no_innerhtml_or_eval_in_source(self):
        src = (HERE / "sandbox_executor.py").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", src)
        self.assertNotIn("eval(", src)


class TestCardBaseline(unittest.TestCase):
    def make_cars(self):
        cars = []
        stage_map = (["kyiv"] * 3) + (["georgia"] * 1) + (["on_ferry"] * 8) + (["korea"] * 4)
        for i, stage in enumerate(stage_map, start=1):
            cars.append({
                "id": f"UA-{i:04d}",
                "vin": f"VIN{i:010d}",
                "stage": stage,
                "price": 10000 + i,
                "photo_count": 10,
                "video_count": 1,
                "diagnostics_count": 1,
                "container": f"CNT{i}",
                "media_sha256": f"hash{i}",
            })
        return cars

    def test_baseline_16_and_stage_counts(self):
        cars = self.make_cars()
        errs, counters = se.validate_card_baseline(cars)
        self.assertEqual(errs, [])
        self.assertEqual(counters, {"kyiv": 3, "georgia": 1, "on_ferry": 8, "korea": 4})
        self.assertEqual(sum(counters.values()), 16)

    def test_duplicate_id_detected(self):
        cars = self.make_cars()
        cars[1]["id"] = cars[0]["id"]
        errs, _ = se.validate_card_baseline(cars)
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_wrong_total_detected(self):
        cars = self.make_cars()[:15]
        errs, _ = se.validate_card_baseline(cars)
        self.assertTrue(any("expected 16" in e for e in errs))

    def test_ua_0009_present_in_synthetic_manifest(self):
        cars = self.make_cars()
        ids = [c["id"] for c in cars]
        self.assertIn("UA-0009", ids)


class TestManifestComparison(unittest.TestCase):
    def test_identical_manifests_no_diff(self):
        before = [{"id": "UA-0001", "vin": "V1", "price": 100}]
        after = [{"id": "UA-0001", "vin": "V1", "price": 100}]
        diffs = se.compare_manifests(before, after)
        self.assertEqual(diffs, [])

    def test_changed_field_detected(self):
        before = [{"id": "UA-0001", "vin": "V1", "price": 100}]
        after = [{"id": "UA-0001", "vin": "V1", "price": 999}]
        diffs = se.compare_manifests(before, after)
        self.assertEqual(len(diffs), 1)
        self.assertIn("price", diffs[0])

    def test_id_set_change_detected(self):
        before = [{"id": "UA-0001"}]
        after = [{"id": "UA-0002"}]
        diffs = se.compare_manifests(before, after)
        self.assertIn("card id set changed", diffs)


class TestProductionGuard(unittest.TestCase):
    def test_production_marker_detected(self):
        self.assertTrue(se.is_production_path("/home/uaartcompany/prod"))
        self.assertTrue(se.is_production_path("/var/www/site"))

    def test_safe_tmp_path_not_flagged(self):
        self.assertFalse(se.is_production_path("/tmp/sandbox_build_xyz"))

    def test_sandbox_root_equal_to_production_rejected(self):
        with self.assertRaises(ValueError):
            se.assert_safe_sandbox_root("/tmp/shared_root", production_root="/tmp/shared_root")

    def test_sandbox_root_nested_in_production_rejected(self):
        with self.assertRaises(ValueError):
            se.assert_safe_sandbox_root("/tmp/prodroot/nested", production_root="/tmp/prodroot")

    def test_sandbox_root_with_production_marker_rejected(self):
        with self.assertRaises(ValueError):
            se.assert_safe_sandbox_root("/var/www/anything")

    def test_safe_sandbox_root_accepted(self):
        result = se.assert_safe_sandbox_root(
            "/tmp/isolated_sandbox_016", production_root="/tmp/prodroot"
        )
        self.assertTrue(result)


class TestRollbackReadiness(unittest.TestCase):
    def test_rollback_point_doc_exists(self):
        rollback_doc = HERE / "ROLLBACK_POINT.md"
        self.assertTrue(rollback_doc.exists())
        content = rollback_doc.read_text(encoding="utf-8")
        self.assertIn("rollback", content.lower())


class TestSelfTestCommand(unittest.TestCase):
    def test_self_test_returns_zero(self):
        rc = se.cmd_self_test()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
