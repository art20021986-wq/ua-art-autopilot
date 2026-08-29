#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from stage_guard import audit_catalog, enforce_catalog, public_eta, stage_number  # noqa: E402


def row(identifier, status, photos=1):
    return {
        "auto_number": identifier, "status": status, "published": 1,
        "brand": "Hyundai", "model": "SONATA", "year": "2018",
        "mileage_km": 51000, "engine_cc": 2000, "fuel": "газ",
        "gearbox": "автомат", "vin": "KMHE341DBKA544289",
        "price": 11500, "photos": "[]" if not photos else '[{"file_id":"x"}]',
        "videos": None,
    }


class StageGuardTests(unittest.TestCase):
    def test_status_mapping(self):
        self.assertEqual(stage_number(row("UA-0001", "kr_verified")), 1)
        self.assertEqual(stage_number(row("UA-0001", "sea_transit")), 2)
        self.assertEqual(stage_number(row("UA-0001", "ge_arrived")), 3)
        self.assertEqual(stage_number(row("UA-0001", "ua_delivered")), 4)

    def test_fallback_becomes_full_photo_card(self):
        source = """<!doctype html><html><head></head><body>
        <a class="ua-cat-fallback-v1" href="UA-0011.html">
        <span>UA-0011</span><span>На пароме · Корея → Грузия</span></a>
        <div class="empty-assist"></div></body></html>"""
        rows = [row("UA-0011", "sea_loaded")]
        candidate = enforce_catalog(source, rows, {"UA-0011": "https://example.test/UA-0011.jpg"})
        result = audit_catalog(candidate, rows)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertIn("На пароме · маршрут — Киев", candidate)
        self.assertNotIn("Корея → Грузия", candidate)
        self.assertIn('data-ua-card-stage="more"', candidate)
        self.assertIn("UA-0011.jpg", candidate)
        self.assertIn("11 500 $", candidate)
        self.assertEqual(result["unified_templates"], 1)
        self.assertEqual(result["absolute_photos"], 1)

    def test_stage_change_moves_category_without_duplication(self):
        source = """<!doctype html><html><head></head><body>
        <a class="kat" href="UA-0011.html"><img src="x.jpg"><b>UA-0011</b>
        <span>На пароме</span><span>Маршрут: Корея → Грузия</span></a>
        <div class="empty-assist"></div></body></html>"""
        for status, expected in (("kr_verified", "korea"), ("sea_loaded", "more"),
                                 ("ge_arrived", "gruzia"), ("ua_delivered", "kiev")):
            rows = [row("UA-0011", status)]
            candidate = enforce_catalog(source, rows, {"UA-0011": "https://example.test/x.jpg"})
            result = audit_catalog(candidate, rows)
            self.assertEqual(result["status"], "PASS", result["errors"])
            self.assertEqual(result["cards"]["UA-0011"]["category"], expected)
            self.assertEqual(candidate.count('href="UA-0011.html"'), 1)
            if status == "sea_loaded":
                self.assertNotIn("Корея → Грузия", candidate)
                self.assertIn("маршрут — Киев", candidate)

    def test_existing_photo_cards_are_rebuilt_to_one_template(self):
        source = """<!doctype html><html><head></head><body>
        <article class="catalog-card"><a href="UA-0001.html"><img src="old-1.jpg"></a>
        <b>UA-0001</b></article>
        <a class="plitka" href="UA-0002.html"><img src="old-2.jpg"><b>UA-0002</b></a>
        <div class="empty-assist"></div></body></html>"""
        rows = [row("UA-0001", "kr_verified"), row("UA-0002", "ua_arrived")]
        candidate = enforce_catalog(source, rows, {
            "UA-0001": "https://example.test/UA-0001.jpg",
            "UA-0002": "https://example.test/UA-0002.jpg",
        })
        result = audit_catalog(candidate, rows)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["unified_templates"], 2)
        self.assertEqual(result["absolute_photos"], 2)
        self.assertNotIn("catalog-card", candidate)
        self.assertNotIn("old-1.jpg", candidate)
        self.assertNotIn("old-2.jpg", candidate)

    def test_stage_three_eta_uses_actual_transition(self):
        item = row("UA-0001", "ge_to_kyiv")
        item["ge_released"] = "2026-08-29"
        ru, uk = public_eta(item, 3)
        self.assertIn("13 сентября 2026", ru)
        self.assertIn("13 вересня 2026", uk)
        self.assertNotIn("предоплат", ru.casefold())

    def test_audit_rejects_legacy_photo_card(self):
        source = """<!doctype html><html><head></head><body>
        <a class="plitka" href="UA-0001.html" data-ua-card-stage="korea">
        <img src="https://example.test/UA-0001.jpg"><b>UA-0001</b>
        <span>В Корее · выкуплен и проверен</span></a></body></html>"""
        result = audit_catalog(source, [row("UA-0001", "kr_verified")])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("TEMPLATE_MISMATCH:UA-0001", result["errors"])


if __name__ == "__main__":
    unittest.main()
