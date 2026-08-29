#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import logging


HERE = pathlib.Path(__file__).resolve().parents[1]
CORE_PATH = HERE.parent / "task_075_stage_guard/stage_guard.py"
RUNTIME_PATH = HERE / "runtime.py"
INSTALLER_PATH = HERE / "remote_installer.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("catalog_stage_guard_core", CORE_PATH)
runtime = load("catalog_stage_guard_runtime", RUNTIME_PATH)
installer = load("task082_remote_installer_test", INSTALLER_PATH)


class ContractTests(unittest.TestCase):
    def fixture(self, root: pathlib.Path):
        (root / "video").mkdir(parents=True)
        (root / "site").mkdir(parents=True)
        db = root / "crm.db"
        con = sqlite3.connect(db)
        con.execute("""CREATE TABLE cars (
            id INTEGER PRIMARY KEY, auto_number TEXT, status TEXT, stage INTEGER,
            published INTEGER, brand TEXT, model TEXT, year TEXT, vin TEXT,
            photos TEXT, videos TEXT, mileage INTEGER, engine_cc INTEGER,
            fuel TEXT, gearbox TEXT, price INTEGER, eta_manual TEXT
        )""")
        rows = [
            (9, "UA-0009", "sea_loaded", 2, 1, "Kia", "K5", "2018",
             "KNAGN418BKA123456", '["001.jpg"]', "[]", 99000, 2000, "LPG",
             "автомат", 9100, "2026-09-28"),
            (11, "UA-0011", "sea_loaded", 2, 1, "Hyundai", "SONATA", "2018",
             "KMHE341DBKA544289", '["001.jpg"]', "[]", 101000, 2000, "LPG",
             "автомат", 11400, "2026-09-09"),
        ]
        con.executemany("INSERT INTO cars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
        catalog = """<!doctype html><html><head></head><body>
<a class="kat" href="UA-0009.html"><h3>Kia K5</h3></a>
<a class="kat" href="UA-0011.html"><h3>Hyundai SONATA</h3><div>На пароме · Корея → Грузия</div></a>
<div class="empty-assist"></div></body></html>"""
        for variant in ("video", "site"):
            (root / variant / "katalog.html").write_text(catalog, encoding="utf-8")
            for identifier in ("UA-0009", "UA-0011"):
                (root / variant / (identifier + ".html")).write_text(
                    "<html><body><img src='foto/%s/m/001.jpg'></body></html>" % identifier,
                    encoding="utf-8",
                )
        runtime.ROOT = root
        runtime.DB_PATH = db
        runtime.CATALOGS = (root / "video/katalog.html", root / "site/katalog.html")
        runtime.BACKUP_PARENT = root / "backups"
        runtime.LOCK_PATH = root / ".lock"

    def test_repairs_ua0011_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            first = runtime.enforce_live_catalog("UA-0011")
            self.assertEqual(first["status"], "PASS")
            for variant in ("video", "site"):
                source = (root / variant / "katalog.html").read_text(encoding="utf-8")
                self.assertIn('data-ua-card-stage="more"', source)
                self.assertIn('data-ua-stage="2"', source)
                self.assertIn("VIN 4289", source)
                self.assertIn("На пароме · маршрут — Киев", source)
                self.assertIn("ua-stage-card-v2-photo", source)
                self.assertNotIn("Корея → Грузия", source)
            second = runtime.enforce_live_catalog("UA-0011", dry_run=True)
            for item in second["catalogs"].values():
                self.assertEqual(item["before_sha256"], item["candidate_sha256"])

    def test_missing_photo_fails_without_catalog_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            (root / "video/UA-0011.html").unlink()
            (root / "site/UA-0011.html").unlink()
            before = (root / "video/katalog.html").read_bytes()
            with self.assertRaises(runtime.GuardError):
                runtime.enforce_live_catalog("UA-0011")
            self.assertEqual(before, (root / "video/katalog.html").read_bytes())

    def test_publisher_wrapper_checks_tuple_success(self):
        sample = """def opublikovat(kod, proba=False):
    if proba:
        return True, "probe"
    return True, "ok"
"""
        patched = installer.patch_publisher(sample)
        self.assertEqual(patched.count(installer.START_MARKER), 1)
        self.assertIn("result[0]", patched)
        compile(patched, "publikaciya.py", "exec")

    def test_db_guard_blocks_stage_regression_when_container_exists(self):
        sample = '''import logging
CARD = {"status": "sea_loaded", "sea_container": "CONT-1"}
AUDIT = []
def get_card(table, card_id):
    return dict(CARD)
def log_action(actor_id, action, table, card_id, field, old, new):
    AUDIT.append((action, old, new))
def update_card_field(table, card_id, field, value, actor_id):
    CARD[field] = value
'''
        scope = {}
        exec(installer.patch_db(sample), scope)
        result = scope["update_card_field"]("cars", 18, "status", "kr_bought", 397376186)
        self.assertFalse(result)
        self.assertEqual(scope["CARD"]["status"], "sea_loaded")
        self.assertEqual(scope["AUDIT"], [("stage_regression_blocked", "sea_loaded", "kr_bought")])

    def test_exact_stage_repair_changes_only_target_status(self):
        with tempfile.TemporaryDirectory() as directory:
            original = installer.DB_PATH
            installer.DB_PATH = pathlib.Path(directory) / "crm.db"
            try:
                con = sqlite3.connect(installer.DB_PATH)
                con.execute('''CREATE TABLE cars (
                    id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, published INTEGER,
                    sea_container TEXT, status TEXT, updated_at TEXT
                )''')
                con.execute('''CREATE TABLE audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT,
                    entity_type TEXT, entity_id INTEGER, field TEXT, old_value TEXT,
                    new_value TEXT, created_at TEXT
                )''')
                con.execute("INSERT INTO cars VALUES (18,'UA-0011',?,1,'CONT-1','kr_bought','before')",
                            (installer.TARGET_VIN,))
                con.commit()
                con.close()
                result = installer.repair_target_stage()
                self.assertTrue(result["changed"])
                con = sqlite3.connect(installer.DB_PATH)
                row = con.execute("SELECT status,sea_container FROM cars WHERE id=18").fetchone()
                audit = con.execute("SELECT action,old_value,new_value FROM audit").fetchone()
                con.close()
                self.assertEqual(row, ("sea_loaded", "CONT-1"))
                self.assertEqual(audit, ("task082_stage_repair", "kr_bought", "sea_loaded"))
            finally:
                installer.DB_PATH = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
