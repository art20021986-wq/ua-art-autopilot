import copy
import io
import json
import pathlib
import tempfile
import unittest

import spec84_collector as collector
import spec_catalog_pages as pages
import spec_model_profiles as models
from spec_retry84 import Queue, input_signature, SLOTS, DOMAIN_TO_SOURCE
from test_collector84 import CollectorTests, CARD, fact

K5 = dict(car_uid="UA-0099", vin="KNAG541BBNA123456", brand="Kia", model="К5",
          year="2021", fuel="газ", engine_cc=1999, published=True)


class ModelTests(unittest.TestCase):
    def test_future_vin_gets_model_facts_without_vin_allowlist(self):
        self.assertEqual(models.resolve(K5)["id"], "kia-dl3-k5-20-lpi")
        for vin in ("KNAG541BBNA987654", "KNAG741BBLA456789"):
            profile = models.resolve(dict(K5, vin=vin))
            self.assertEqual(profile["facts"]["length"]["value"], "4905 мм")
            self.assertNotIn("tyre_size", profile["facts"])
            self.assertNotIn("combined_fuel_economy", profile["facts"])

    def test_wrong_generation_fuel_or_missing_inputs_fail_closed(self):
        for change in (dict(year="2025"), dict(year="2016"), dict(engine_cc=1598),
                       dict(fuel="бензин"), dict(fuel="hybrid"), dict(model="K3"),
                       dict(brand=""), dict(engine_cc=0), dict(vin="KNAGS416BNA123456")):
            self.assertIsNone(models.resolve(dict(K5, **change)))

    def test_audi_does_not_guess_power_gearbox_or_body(self):
        card = dict(K5, vin="WAUZZZ4G3GN123456", brand="Audi", model="А6",
                    year="2016", fuel="дизель", engine_cc=2967)
        fields = models.resolve(card)["facts"]
        self.assertEqual(fields["cylinders"]["value"], "6")
        self.assertFalse(set(fields) & {"maximum_power", "number_of_gears", "length", "body"})

    def test_official_sources_survive_worker_protocol(self):
        self.assertEqual(len(DOMAIN_TO_SOURCE), 10)
        def offline(*args, **kwargs):
            raise OSError("fixture offline")
        result = collector.collect(K5, opener=offline)
        self.assertEqual(result["sources"]["kia_korea"]["status"], "CURATED")
        self.assertEqual(result["sources"]["kia_korea"]["curated_at"], "2026-09-27")
        self.assertEqual(len(result["facts"]), 11)
        self.assertTrue(all("price" not in f["field_key"] for f in result["facts"]))

    def test_multi_engine_html_cannot_invent_equipment(self):
        body = b'<h1>Kia K5</h1><p>Length</p><p>4905 mm</p><p>Power</p><p>180 hp</p>'
        facts, state = pages.extract(K5, models.KIA, body, models.resolve(K5))
        self.assertNotIn("maximum_power", [f.field_key for f in facts])
        facts, state = pages.extract(dict(K5, vin="OTHER1234567890123"), models.KIA, body, None)
        self.assertEqual(facts, [])


class QueueTests(unittest.TestCase):
    def test_input_change_retries_but_price_and_repeat_click_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "queue.db"
            q = Queue(path)
            first = q.ensure_cycle(K5, now=1000)
            repeated = q.ensure_cycle(dict(K5, price=12000, purchase_price=6000, status="arrived"), now=2000)
            self.assertEqual(first, repeated)
            self.assertEqual([s["due_at"] for s in q.report()["slots"]], [1000 + n for n in SLOTS])
            changed = Queue(path).ensure_cycle(dict(K5, year="2022"), now=3000)
            self.assertEqual(changed["generation"], 2)
            self.assertEqual(len(q.report()["cycles"]), 2)
            self.assertEqual(Queue(path).ensure_cycle(dict(K5, year="2022"))["id"], changed["id"])

    def test_upgrade_backfills_old_completed_generation_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Queue(pathlib.Path(tmp) / "queue.db")
            q.ensure_cycle(K5, now=1000)
            with q.connect() as db:
                db.execute("DELETE FROM spec84_inputs")
                db.execute("UPDATE spec84_slots SET state='DONE'")
                db.execute("UPDATE spec84_cycles SET state='COMPLETE'")
            self.assertEqual(q.ensure_cycle(K5)["generation"], 2)
            self.assertEqual(q.ensure_cycle(K5)["generation"], 2)


class PriceAndRetentionTests(CollectorTests):
    def test_purchase_fields_and_disguised_price_labels_are_rejected(self):
        malicious = []
        for key in ("purchase_price", "buy_price", "acquisition_cost", "wholesale_price", "cost_price"):
            malicious.append(fact(key, "12000"))
        for text in ("Закупочная стоимость", "Закупівельна ціна", "Себестоимость", "purchase_price"):
            malicious.append(dict(fact("seats", "5"), label_ru=text))
            malicious.append(fact("seats", text))
        result = self.merge(malicious + [fact()])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["rejected"], len(malicious))

    def test_same_vin_model_refresh_preserves_manual_hidden_and_accepted_rows(self):
        self.merge([fact()])
        self.db.execute("UPDATE additional_specification_meta SET is_manual=1,is_visible=0")
        collector.ensure_identity_schema(self.db)
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        collector.ensure_binding(self.db, CARD, 1, legacy_vin=CARD["vin"])
        result = collector.ensure_binding(self.db, CARD, 2)
        self.db.commit()
        self.assertEqual(result["retained_facts"], 1)
        self.assertEqual(tuple(self.db.execute("SELECT is_manual,is_visible FROM additional_specification_meta").fetchone()), (1, 0))


if __name__ == "__main__":
    unittest.main()
