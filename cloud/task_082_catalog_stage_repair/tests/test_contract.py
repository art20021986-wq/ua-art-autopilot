#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest


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
                self.assertIn("function setChipCount", source)
                self.assertIn("counts={all:cards.length", source)
                self.assertIn("setShown(shown)", source)
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

    def test_status_normalization_changes_only_status_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            con = sqlite3.connect(root / "crm.db")
            con.row_factory = sqlite3.Row
            con.execute("UPDATE cars SET status='kr_bought' WHERE auto_number='UA-0011'")
            con.commit()
            before = dict(con.execute(
                "SELECT * FROM cars WHERE auto_number='UA-0011'").fetchone())
            con.close()
            previous_root = installer.ROOT
            try:
                installer.ROOT = root
                value = installer.normalize_ua0011_status()
                self.assertTrue(value["changed"])
                self.assertEqual(value["before_status"], "kr_bought")
                self.assertEqual(value["after_status"], "sea_loaded")
                self.assertEqual(value["fields_changed"], ["status"])
                again = installer.normalize_ua0011_status()
                self.assertFalse(again["changed"])
                restored = installer.restore_ua0011_status(value)
                self.assertTrue(restored["changed"])
                self.assertEqual(restored["status"], "kr_bought")
            finally:
                installer.ROOT = previous_root
            con = sqlite3.connect(root / "crm.db")
            con.row_factory = sqlite3.Row
            after = dict(con.execute(
                "SELECT * FROM cars WHERE auto_number='UA-0011'").fetchone())
            con.close()
            self.assertEqual(before, after)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

