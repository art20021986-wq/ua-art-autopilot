"""Self-tests for the UA cards unified pipeline (Gate A only).

These tests do not touch production, PythonAnywhere, or the real
data/input_cards directory. They operate entirely on temporary directories
by monkeypatching the path constants in common.py before reloading the
pipeline modules.

Run with:
    python -m unittest cloud/ua_cards_unified/tests/test_pipeline.py -v
"""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_DIR))

import common  # noqa: E402


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ua_cards_test_"))
        self.input_dir = self.tmp / "input_cards"
        self.output_dir = self.tmp / "output"
        self.input_dir.mkdir(parents=True)
        self.output_dir.mkdir(parents=True)

        self._orig_input = common.INPUT_DIR
        self._orig_output = common.OUTPUT_DIR
        self._orig_manifest = common.MANIFEST_PATH
        self._orig_preflight = common.PREFLIGHT_REPORT_PATH
        self._orig_run_log = common.RUN_LOG_PATH

        common.INPUT_DIR = self.input_dir
        common.OUTPUT_DIR = self.output_dir
        common.MANIFEST_PATH = self.output_dir / "manifest.json"
        common.PREFLIGHT_REPORT_PATH = self.output_dir / "preflight_report.json"
        common.RUN_LOG_PATH = self.output_dir / "run_log.json"

        global preflight, runner, manifest_builder
        preflight = importlib.import_module("preflight")
        runner = importlib.import_module("runner")
        manifest_builder = importlib.import_module("manifest_builder")
        importlib.reload(preflight)
        importlib.reload(runner)
        importlib.reload(manifest_builder)

    def tearDown(self):
        common.INPUT_DIR = self._orig_input
        common.OUTPUT_DIR = self._orig_output
        common.MANIFEST_PATH = self._orig_manifest
        common.PREFLIGHT_REPORT_PATH = self._orig_preflight
        common.RUN_LOG_PATH = self._orig_run_log
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_card(self, name: str, payload: dict):
        with open(self.input_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_empty_input_blocks(self):
        report = preflight.run_preflight()
        self.assertEqual(report["status"], "FAIL")

    def test_banned_synthetic_id_is_rejected(self):
        self._write_card("bad", {"card_id": "UA-0003", "title": "x", "payload": {}})
        report = preflight.run_preflight()
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("BANNED" in f for f in report["blocking_findings"]))

        run_log = runner.run()
        self.assertEqual(run_log["gate_status"], "BLOCKED")

        manifest = manifest_builder.build_manifest()
        self.assertEqual(manifest["gate_status"], "BLOCKED")

    def test_valid_card_reaches_awaiting_gate_b(self):
        self._write_card(
            "REAL-CARD-9001",
            {"card_id": "REAL-CARD-9001", "title": "Real card", "payload": {"k": "v"}},
        )
        report = preflight.run_preflight()
        self.assertEqual(report["status"], "PASS")

        run_log = runner.run()
        self.assertEqual(run_log["gate_status"], "AWAITING_GATE_B")

        manifest = manifest_builder.build_manifest()
        self.assertEqual(manifest["gate_status"], "AWAITING_GATE_B")

    def test_single_failing_card_blocks_whole_batch(self):
        self._write_card(
            "REAL-CARD-9002",
            {"card_id": "REAL-CARD-9002", "title": "Real card", "payload": {}},
        )
        self._write_card("BROKEN-CARD-9003", {"title": "missing id"})

        preflight.run_preflight()
        run_log = runner.run()
        self.assertEqual(run_log["gate_status"], "BLOCKED")
        self.assertGreaterEqual(run_log["failed_cards"], 1)

        manifest = manifest_builder.build_manifest()
        self.assertEqual(manifest["gate_status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
