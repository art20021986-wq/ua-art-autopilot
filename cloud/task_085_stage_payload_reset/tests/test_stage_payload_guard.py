#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import sqlite3
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "task085_stage_payload_guard", ROOT / "stage_payload_guard.py"
)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(guard)


class StagePayloadGuardTests(unittest.TestCase):
    def test_stage_mapping_is_explicit(self):
        self.assertEqual(guard.stage_number("kr_bought"), 1)
        self.assertEqual(guard.stage_number("sea_loaded"), 2)
        self.assertEqual(guard.stage_number("ge_to_kyiv"), 3)
        self.assertEqual(guard.stage_number("ua_ready"), 4)
        self.assertIsNone(guard.stage_number("sold"))

    def test_same_stage_is_idempotent(self):
        fields = ("eta_manual", "days_to_kyiv", "sea_container")
        self.assertEqual(
            guard.cleanup_fields_for_transition("sea_transit", "sea_loaded", fields), ()
        )

    def test_korea_transition_clears_all_downstream_payload(self):
        fields = set(guard.KOREA_RESET_FIELDS) | {"vin", "price_uah"}
        self.assertEqual(
            set(guard.cleanup_fields_for_transition("sea_loaded", "kr_bought", fields)),
            set(guard.KOREA_RESET_FIELDS),
        )

    def test_public_projection_never_leaks_previous_stage(self):
        base = {
            "status": "kr_bought",
            "sea_container": "ONEYSELGF1046602",
            "eta_manual": "2026-12-12",
            "days_to_kyiv": 105,
            "vin": "KMHE341DBKA544289",
        }
        projected = guard.public_projection(base)
        self.assertIsNone(projected["sea_container"])
        self.assertIsNone(projected["eta_manual"])
        self.assertIsNone(projected["days_to_kyiv"])
        self.assertEqual(projected["vin"], base["vin"])
        self.assertEqual(base["sea_container"], "ONEYSELGF1046602")

    def test_diagnostic_placeholder_is_complete_and_scoped(self):
        html = guard.diagnostic_placeholder_html("UA-0011")
        self.assertIn("Комплексная диагностика UA-0011", html)
        self.assertIn("Материалы комплексной диагностики ожидаются", html)
        self.assertIn("UA-0011.html", html)
        with self.assertRaises(guard.StagePayloadError):
            guard.diagnostic_placeholder_html("../UA-0011")

    def test_main_card_diagnostic_cta_is_exact_and_wrong_link_fails(self):
        html = (
            "<html><body><section>Полная карточка</section>"
            "<a class='kn_kupit' href='#buy'>Купить</a></body></html>"
        )
        result = guard.ensure_diagnostic_section(html, "UA-0011")
        self.assertEqual(result.count("UA-0011-diag.html"), 1)
        self.assertEqual(result.count("Комплексная диагностика"), 1)
        self.assertLess(result.index("Комплексная диагностика"), result.index("kn_kupit"))
        self.assertEqual(guard.ensure_diagnostic_section(result, "UA-0011"), result)
        with self.assertRaises(guard.StagePayloadError):
            guard.ensure_diagnostic_section(
                "<html><body><a href='UA-0009-diag.html'>Диагностика</a></body></html>",
                "UA-0011",
            )

    def test_sql_triggers_block_container_and_eta_for_korea(self):
        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE TABLE cars (id INTEGER PRIMARY KEY, status TEXT, "
            "sea_container TEXT, sea_date_out TEXT, days_to_kyiv INTEGER, "
            "eta_manual TEXT, ge_arrived TEXT)"
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(cars)")]
        guard.install_korea_triggers(con, columns)
        con.execute(
            "INSERT INTO cars VALUES (1,'kr_bought','OLD','2026-01-01',105,"
            "'2026-12-12','2026-02-01')"
        )
        row = con.execute("SELECT * FROM cars WHERE id=1").fetchone()
        self.assertEqual(row[1], "kr_bought")
        self.assertTrue(all(value is None for value in row[2:]))
        con.execute("UPDATE cars SET sea_container='SHOULD-NOT-STICK' WHERE id=1")
        self.assertIsNone(con.execute(
            "SELECT sea_container FROM cars WHERE id=1"
        ).fetchone()[0])
        con.execute("UPDATE cars SET status='sea_loaded', sea_container='VALID' WHERE id=1")
        self.assertEqual(con.execute(
            "SELECT sea_container FROM cars WHERE id=1"
        ).fetchone()[0], "VALID")
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

