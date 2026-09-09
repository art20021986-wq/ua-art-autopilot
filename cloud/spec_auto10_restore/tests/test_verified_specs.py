import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "build_verified_specs.py"
module_spec = importlib.util.spec_from_file_location("verified_spec_export_test", MODULE)
exporter = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(exporter)


class VerifiedSpecExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = exporter.identity_policy()

    def card(self, **values):
        defaults = dict(id=16, auto_number="UA-0016", vin="KNAGS416BHA141028",
                        brand="Kia", model="К5", year="1999", published=1)
        return tuple({**defaults, **values}.get(key) for key in exporter.CRM_FIELDS.split(","))

    def test_hash_mismatch_fails_closed_without_database_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            spec, crm = Path(folder) / "spec.db", Path(folder) / "crm.db"
            with sqlite3.connect(spec) as conn:
                for table, fields in exporter.SPEC_FIELDS.items():
                    conn.execute("CREATE TABLE " + table + " (" +
                                 ",".join(field + " TEXT" for field in fields.split(",")) + ")")
            with sqlite3.connect(crm) as conn:
                conn.execute("CREATE TABLE placeholder (id INTEGER)")
            before = (exporter.file_digest(spec), exporter.file_digest(crm))
            with self.assertRaisesRegex(exporter.ExportError, "SPEC_SEMANTIC_HASH_MISMATCH"):
                exporter.build(spec, crm)
            self.assertEqual(before, (exporter.file_digest(spec), exporter.file_digest(crm)))
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["crm.db", "spec.db"])

    def test_year_conflict_keeps_crm_value_and_blocks_restore(self):
        card = self.card()
        quality = exporter.identity_quality(card, self.policy)
        self.assertEqual(quality["status"], "NEEDS_REVIEW")
        self.assertTrue(quality["inspection_only"])
        self.assertFalse(quality["eligible_for_stored_fact_restore"])
        self.assertEqual(quality["inferred_model_year"], 2017)
        self.assertIn("1999", quality["warning_uk"])
        self.assertEqual(card[5], "1999")

    def test_numeric_european_chassis_code_is_not_a_false_model_year(self):
        quality = exporter.identity_quality(self.card(vin="WDD2452322J561014", brand="Mercedes-Benz",
                                                      model="B-Class", year="2010"), self.policy)
        self.assertEqual(quality["status"], "STORED_CONTEXT_MATCH")
        self.assertIsNone(quality["inferred_model_year"])

    def test_model_alias_and_one_year_difference_are_accepted(self):
        profile = next(profile for profile in self.policy.profile_library.PROFILES
                       if profile["id"] == "mercedes-w246-b200-cdi-dct")
        quality = exporter.identity_quality(self.card(vin=profile["exact_vins"][0], brand="Mercedes-Benz",
                                                      model="Б-КЛАССА", year="2015"), self.policy)
        self.assertEqual(quality["status"], "STORED_CONTEXT_MATCH")
        self.assertTrue(quality["profile_model_matches"])
        self.assertEqual(quality["year_check"], "WITHIN_ONE_YEAR")

    def test_exact_vin_does_not_bypass_crm_model_conflict(self):
        quality = exporter.identity_quality(self.card(model="Sportage", year="2017"), self.policy)
        self.assertIn("CRM_MODEL_DIFFERS_FROM_EXACT_VIN_PROFILE", quality["issues"])
        self.assertTrue(quality["inspection_only"])


if __name__ == "__main__":
    unittest.main()
