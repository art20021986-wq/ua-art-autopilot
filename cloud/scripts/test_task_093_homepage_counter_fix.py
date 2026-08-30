#!/usr/bin/env python3
"""
Offline test suite for task_093_homepage_counter_fix.py.

All operations run against temporary fixture files created by this
test module. No network access, no live CRM, no PythonAnywhere,
no UA ART production files are touched.
"""
import json
import os
import shutil
import tempfile
import unittest

import task_093_homepage_counter_fix as fixmod


EXPECTED_COUNTERS = {"kyiv": 3, "georgia": 1, "ferry": 7, "korea": 2}
EXPECTED_TOTAL = 13


def make_snapshot_rows():
    rows = []
    for i in range(1, 4):
        rows.append({"id": f"UA-KYIV-{i}", "stage": "kyiv", "published": True})
    rows.append({"id": "UA-GEO-1", "stage": "georgia", "published": True})
    for i in range(1, 8):
        rows.append({"id": f"UA-FERRY-{i}", "stage": "ferry", "published": True})
    for i in range(1, 3):
        rows.append({"id": f"UA-KOREA-{i}", "stage": "korea", "published": True})
    # unpublished / duplicate noise that must NOT be counted
    rows.append({"id": "UA-FERRY-1", "stage": "ferry", "published": True})  # dup
    rows.append({"id": "UA-DRAFT-1", "stage": "kyiv", "published": False})
    return rows


class TestComputeCounters(unittest.TestCase):
    def test_counts_unique_published_rows(self):
        rows = make_snapshot_rows()
        counters, total = fixmod.compute_counters(rows)
        self.assertEqual(counters, EXPECTED_COUNTERS)
        self.assertEqual(total, EXPECTED_TOTAL)

    def test_ignores_unpublished(self):
        rows = [{"id": "X", "stage": "kyiv", "published": False}]
        counters, total = fixmod.compute_counters(rows)
        self.assertEqual(total, 0)

    def test_ignores_unknown_stage(self):
        rows = [{"id": "X", "stage": "mars", "published": True}]
        counters, total = fixmod.compute_counters(rows)
        self.assertEqual(total, 0)


class TestApplyFixIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task093_test_")
        self.snapshot_path = os.path.join(self.tmpdir, "snapshot.json")
        self.homepage_a = os.path.join(self.tmpdir, "homepage_a.json")
        self.homepage_b = os.path.join(self.tmpdir, "homepage_b.json")

        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(make_snapshot_rows(), f)

        base_homepage = {
            "stage_counters": {"kyiv": 3, "georgia": 1, "ferry": 4, "korea": 2},
            "cta_total": 10,
            "hero_title": "UA ART",
            "other_untouched": {"nested": [1, 2, 3]},
        }
        with open(self.homepage_a, "w", encoding="utf-8") as f:
            json.dump(base_homepage, f)
        with open(self.homepage_b, "w", encoding="utf-8") as f:
            json.dump(base_homepage, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_run_pass_and_preserves_other_fields(self):
        result = fixmod.run(
            self.snapshot_path, [self.homepage_a, self.homepage_b]
        )
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["counters"], EXPECTED_COUNTERS)
        self.assertEqual(result["total"], EXPECTED_TOTAL)

        for path in (self.homepage_a, self.homepage_b):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["stage_counters"], EXPECTED_COUNTERS)
            self.assertEqual(data["cta_total"], EXPECTED_TOTAL)
            self.assertEqual(data["hero_title"], "UA ART")
            self.assertEqual(data["other_untouched"], {"nested": [1, 2, 3]})

        for entry in result["results"]:
            self.assertTrue(os.path.exists(entry["backup"]))

    def test_backup_created_before_write(self):
        result = fixmod.run(
            self.snapshot_path, [self.homepage_a, self.homepage_b]
        )
        for entry in result["results"]:
            with open(entry["backup"], "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            self.assertEqual(
                backup_data["stage_counters"],
                {"kyiv": 3, "georgia": 1, "ferry": 4, "korea": 2},
            )
            self.assertEqual(backup_data["cta_total"], 10)

    def test_rollback_on_forced_mismatch(self):
        original_dump = fixmod.dump_json_atomic

        def corrupting_dump(path, data):
            corrupted = json.loads(json.dumps(data))
            corrupted["cta_total"] = 999999
            original_dump(path, corrupted)

        fixmod.dump_json_atomic = corrupting_dump
        try:
            result = fixmod.run(self.snapshot_path, [self.homepage_a])
        finally:
            fixmod.dump_json_atomic = original_dump

        self.assertEqual(result["overall"], "ROLLED_BACK")
        with open(self.homepage_a, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["cta_total"], 10)
        self.assertEqual(
            data["stage_counters"],
            {"kyiv": 3, "georgia": 1, "ferry": 4, "korea": 2},
        )


if __name__ == "__main__":
    unittest.main()
