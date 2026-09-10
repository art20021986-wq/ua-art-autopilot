"""Offline checks of loss-prevention, identity rollback and source outcomes."""
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "task_111_vin_spec_10src"))
sys.path.insert(0, str(HERE))
import spec84_collector as c
import vin_spec_service as legacy


CARD = {"car_uid": "UA-0001", "vin": "WDDZF0EB7HA053001", "published": True,
        "brand": "Mercedes", "model": "E220", "year": "2017", "engine_cc": 1950,
        "fuel": "diesel"}


def fact(key="length", value="4923 мм", domain="auto-data.net"):
    return {"field_key": key, "display_value": value, "label_ru": key,
            "category": "dimensions", "unit": "мм", "confidence": .9,
            "source_domains": [domain], "source_urls": ["https://www." + domain + "/en/technical"]}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.before = legacy.SPEC_DB
        legacy.SPEC_DB = pathlib.Path(self.temp.name) / "sidecar.db"
        legacy.ensure_schema()
        self.db = legacy.connect_spec()

    def tearDown(self):
        self.db.close()
        legacy.SPEC_DB = self.before
        self.temp.cleanup()

    def merge(self, incoming):
        self.db.execute("BEGIN IMMEDIATE")
        result = c.merge_in_transaction(self.db, CARD, incoming, guard=lambda conn, card: None)
        self.db.commit()
        return result

    def test_conflict_empty_and_manual_hidden_never_erase_or_downgrade(self):
        self.merge([fact(), fact("width", "1852 мм"), fact("height", "1468 мм")])
        self.db.execute("UPDATE additional_specification_meta SET is_manual=1 WHERE field_key='width'")
        self.db.execute("UPDATE additional_specification_meta SET is_visible=0 WHERE field_key='height'")
        self.db.commit()
        before = [tuple(row) for row in self.db.execute("SELECT * FROM additional_specification ORDER BY id")]
        conflict = fact(value="10 мм")
        conflict["confidence"] = 1.0
        outcome = self.merge([conflict, fact("width", "15 мм"), fact("height", "19 мм")])
        self.assertEqual(outcome["conflicts"], 1)
        self.assertEqual(outcome["protected"], 2)
        self.merge([])
        self.assertEqual(before, [tuple(row) for row in self.db.execute("SELECT * FROM additional_specification ORDER BY id")])
        self.assertEqual(self.db.execute("SELECT is_visible FROM additional_specification_meta WHERE field_key='height'").fetchone()[0], 0)

    def test_equal_value_unions_old_provenance_and_rejects_forbidden_primary_ad(self):
        self.merge([fact()])
        self.db.execute("UPDATE additional_specification_meta SET source_domains_json=?,source_urls_json=?",
                        (json.dumps(["carwiki.co.kr"]), json.dumps(["https://www.carwiki.co.kr/model/old"])))
        self.db.commit()
        ad = fact("boot_capacity", "5")
        ad["source_urls"] = ["https://www.auto-data.net/en/?utm_source=ads"]
        outcome = self.merge([fact(domain="ultimatespecs.com"), fact("price", "999"),
                              fact("torque", "99", "carwiki.co.kr"), ad])
        self.assertEqual(outcome["merged"], 1)
        self.assertEqual(outcome["rejected"], 3)
        row = self.db.execute("SELECT source_domains_json FROM additional_specification_meta").fetchone()
        self.assertEqual(set(json.loads(row[0])), {"carwiki.co.kr", "ultimatespecs.com"})

    def test_generation_changes_during_commit_roll_back_every_fact(self):
        calls = []
        def guard(conn, card):
            calls.append(1)
            if len(calls) == 2:
                raise c.CollectorError("VIN_GENERATION_CHANGED")
        self.db.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(c.CollectorError, "VIN_GENERATION_CHANGED"):
            c.merge_in_transaction(self.db, CARD, [fact()], guard=guard)
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT count(*) FROM additional_specification").fetchone()[0], 0)

    def test_offline_failure_keeps_dated_curated_and_ten_honest_outcomes(self):
        requests, emitted = [], []
        def unavailable(request, timeout):
            requests.append(request.full_url)
            raise OSError("offline fixture")
        result = c.collect(CARD, opener=unavailable,
                           emit_source=lambda sid, outcome, facts: emitted.append((sid, outcome, facts)))
        self.assertEqual(len(result["sources"]), 10)
        self.assertTrue(result["facts"])
        self.assertTrue(emitted)
        self.assertTrue(all(c._transport_domain(url) for url in requests))
        self.assertTrue(all(source in c.APPROVED_DOMAINS for f in result["facts"] for source in f["source_domains"]))
        self.assertEqual(result["sources"]["auto_data"]["status"], "CURATED")
        self.assertEqual(result["sources"]["auto_data"]["network_status"], "NOT_CONFIGURED")
        self.assertEqual(result["sources"]["auto_data"]["curated_at"], "2026-09-04")
        self.assertTrue(all(result["sources"][key]["status"] == "NOT_CONFIGURED"
                            for key in ("kia_korea", "hyundai_korea", "mercedes_archive", "audi_mediacenter")))
        self.assertFalse(any(outcome["fresh_facts"] for outcome in result["sources"].values()))

    def test_japanese_chassis_remains_valid_but_is_not_sent_to_vpic(self):
        def forbidden_network(*args, **kwargs):
            raise AssertionError("Chassis must not be sent to vPIC")
        result = c.collect(dict(CARD, vin="HE12-012345"), opener=forbidden_network)
        self.assertEqual(len(result["sources"]), 10)
        self.assertEqual(result["sources"]["nhtsa_vpic"]["status"], "NOT_APPLICABLE")
        self.assertEqual(result["status"], "COMPLETE_EMPTY")

    def test_binding_archives_manual_hidden_on_vin_change_without_losing_history(self):
        self.merge([fact()])
        self.db.execute("UPDATE additional_specification_meta SET is_manual=1,is_visible=0")
        c.ensure_identity_schema(self.db)
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        baseline = c.ensure_binding(self.db, CARD, 1, legacy_vin=CARD["vin"])
        self.assertEqual(baseline["retained_facts"], 1)
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        changed = c.ensure_binding(self.db, dict(CARD, vin="WDDZF0EB7HA053002"), 2)
        self.assertEqual(changed["archived_facts"], 1)
        self.db.commit()
        self.assertEqual(self.db.execute("SELECT count(*) FROM additional_specification").fetchone()[0], 0)
        archived = self.db.execute("SELECT * FROM spec84_fact_history").fetchone()
        self.assertEqual(json.loads(archived["facts_json"])[0]["field_value"], "4923 мм")
        flags = json.loads(archived["meta_json"])[0]
        self.assertEqual((flags["is_manual"], flags["is_visible"]), (1, 0))
        self.db.execute("BEGIN IMMEDIATE")
        c.ensure_binding(self.db, CARD, 3)
        self.db.commit()
        self.assertEqual(self.db.execute("SELECT count(*) FROM additional_specification").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM spec84_fact_history").fetchone()[0], 1)

    def test_unproven_baseline_and_failed_archive_transaction_leave_active_rows(self):
        self.merge([fact()])
        c.ensure_identity_schema(self.db)
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(c.IdentityError, "LEGACY_FACT_IDENTITY_UNPROVEN"):
            c.ensure_binding(self.db, CARD, 1)
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT count(*) FROM additional_specification").fetchone()[0], 1)
        self.db.execute("BEGIN IMMEDIATE")
        c.ensure_binding(self.db, CARD, 1, legacy_vin="WDDZF0EB7HA053002")
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT count(*) FROM additional_specification").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM spec84_fact_history").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
