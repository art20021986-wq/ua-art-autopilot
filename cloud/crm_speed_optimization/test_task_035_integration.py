"""Offline, deterministic tests for TASK 035: evidence integration and
complete compatibility between the TASK 032 orchestrator and the
TASK 034 evidence modules. No network access. No /home/Carix or
production paths. No PythonAnywhere access. No Gate A execution against
production. Only temporary directories, local files, and fake HTTPS
openers are used.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a as gate_a
import build_manifest
import verify_gate_a
import sqlite_ownership
import ua0009_publication_check

import test_task_032_orchestration as t032
from test_task_032_orchestration import _make_temp_config, _fake_opener_404, CARS_UI_SIDE_EFFECT_SOURCE

PII_SEED = "no-pii-seed-marker-should-not-leak-task035"


# ---------------------------------------------------------------------------
# Regression 1: candidates_compile present after cars_ui semantic block
# ---------------------------------------------------------------------------

class Regression1CandidatesCompileAfterBlockTests(unittest.TestCase):
    def test_candidates_compile_present_from_original_bytes_and_final_status_blocked(self):
        cfg, tmp = _make_temp_config()
        try:
            cars_ui_path = [p for p in cfg["required_inputs"] if p.endswith("cars_ui.py")][0]
            with open(cars_ui_path, "w") as fh:
                fh.write(CARS_UI_SIDE_EFFECT_SOURCE)
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertIn("candidates_compile", receipt["evidence"])
            compile_ev = receipt["evidence"]["candidates_compile"]
            self.assertEqual(compile_ev["status"], "OK")
            self.assertEqual(compile_ev.get("candidate_origin"), "original_due_to_transform_block")
            # Safe compile evidence never by itself permits a final PASS.
            self.assertEqual(receipt["status"], "BLOCKED")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 2: build_manifest historical vs canonical call forms
# ---------------------------------------------------------------------------

class Regression2ManifestCompatTests(unittest.TestCase):
    def test_historical_manifest_call_with_receipt_dict_is_deterministic(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest1 = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest2 = build_manifest.build_manifest(package_dir, run_dir, receipt)
            self.assertIn("receipt_sha256", manifest1)
            self.assertIn("report_sha256", manifest1)
            self.assertEqual(build_manifest.canonical_json(manifest1), build_manifest.canonical_json(manifest2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_canonical_manifest_call_still_works_with_bounded_list(self):
        tmp = tempfile.mkdtemp(prefix="task035_manifest_")
        try:
            package_dir = os.path.join(tmp, "pkg")
            os.makedirs(package_dir)
            with open(os.path.join(package_dir, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            run_dir = os.path.join(tmp, "run")
            os.makedirs(run_dir)
            f1 = os.path.join(run_dir, "f1.txt")
            f2 = os.path.join(run_dir, "f2.txt")
            with open(f1, "w") as fh:
                fh.write("a")
            with open(f2, "w") as fh:
                fh.write("b")
            m1 = build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"multi": [f1, f2]})
            m2 = build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"multi": [f1, f2]})
            self.assertIsInstance(m1["run_artifact_hashes"]["multi"], list)
            self.assertEqual(len(m1["run_artifact_hashes"]["multi"]), 2)
            self.assertEqual(build_manifest.canonical_json(m1), build_manifest.canonical_json(m2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dict_artifact_value_blocks_cleanly(self):
        tmp = tempfile.mkdtemp(prefix="task035_manifest_dict_")
        try:
            package_dir = os.path.join(tmp, "pkg")
            os.makedirs(package_dir)
            with open(os.path.join(package_dir, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            run_dir = os.path.join(tmp, "run")
            os.makedirs(run_dir)
            f1 = os.path.join(run_dir, "f1.txt")
            with open(f1, "w") as fh:
                fh.write("a")
            with self.assertRaises(ValueError):
                build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"bad": {"nested": f1}})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 3: dual-schema fail-closed verifier
# ---------------------------------------------------------------------------

class Regression3VerifierSchemaTests(unittest.TestCase):
    def _historical_predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.HISTORICAL_REQUIRED_PREDICATES}

    def _focused_predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.REQUIRED_PREDICATES}

    def test_historical_schema_pass_valid_fixture(self):
        tmp = tempfile.mkdtemp(prefix="task035_hist_")
        try:
            receipt = {
                "status": "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL",
                "production_write": "NO",
                "evidence": self._historical_predicates_ok(),
                "unmet_predicates": [],
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertTrue(ok, reason)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_focused_schema_pass_valid_fixture(self):
        tmp = tempfile.mkdtemp(prefix="task035_foc_")
        try:
            receipt = {
                "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
                "predicates": self._focused_predicates_ok(), "unmet_predicates": [],
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertTrue(ok, reason)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mixed_schema_blocks_cleanly(self):
        tmp = tempfile.mkdtemp(prefix="task035_mix_")
        try:
            receipt = {
                "status": "BLOCKED", "production_write": "NO",
                "evidence": self._historical_predicates_ok(),
                "predicates": self._focused_predicates_ok(),
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "mixed_schema_forms")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_historical_predicate_exact_prefix(self):
        tmp = tempfile.mkdtemp(prefix="task035_missp_")
        try:
            preds = self._historical_predicates_ok()
            del preds["backup_verified"]
            receipt = {"status": "BLOCKED", "production_write": "NO", "evidence": preds}
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "missing_or_malformed_predicate:backup_verified")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_malformed_focused_predicate_blocks(self):
        tmp = tempfile.mkdtemp(prefix="task035_foc_bad_")
        try:
            preds = self._focused_predicates_ok()
            preds["pii_not_emitted"] = "not-a-dict"
            receipt = {
                "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
                "predicates": preds,
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "missing_or_malformed_predicate:pii_not_emitted")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 4: two-argument verify_receipt auto-binds run_dir/report.md
# ---------------------------------------------------------------------------

class Regression4ReportAutoBindTests(unittest.TestCase):
    def test_report_tamper_detected_with_two_positional_args(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest_path = os.path.join(run_dir, "manifest.json")
            with open(manifest_path, "w") as fh:
                json.dump(manifest, fh)
            report_path = os.path.join(run_dir, "report.md")
            with open(report_path, "a") as fh:
                fh.write("tampered-line" + os.linesep)
            ok, reason = verify_gate_a.verify_receipt(os.path.join(run_dir, "receipt.json"), manifest_path)
            self.assertFalse(ok)
            self.assertEqual(reason, "report_hash_mismatch")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_receipt_tamper_blocks(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest_path = os.path.join(run_dir, "manifest.json")
            with open(manifest_path, "w") as fh:
                json.dump(manifest, fh)
            receipt_path = os.path.join(run_dir, "receipt.json")
            with open(receipt_path, "a") as fh:
                fh.write(" ")
            ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path)
            self.assertFalse(ok)
            self.assertEqual(reason, "receipt_hash_mismatch")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Canonical delegation identity / monkeypatch tests
# ---------------------------------------------------------------------------

class DelegationIdentityTests(unittest.TestCase):
    def test_publication_probe_delegates_to_canonical_function(self):
        cfg, tmp = _make_temp_config()
        try:
            calls = []
            original = ua0009_publication_check.canonical_probe_ua0009

            def spy(url, opener=None, timeout=5.0):
                calls.append(url)
                return original(url, opener=opener, timeout=timeout)

            with mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", spy):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertTrue(calls)
            self.assertEqual(calls[0], cfg["ua0009_url"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sqlite_ownership_evidence_delegates_to_canonical_function(self):
        cfg, tmp = _make_temp_config()
        try:
            cfg["ua0009_table"] = "t"
            cfg["ua0009_id_column"] = "id"
            cfg["ua0009_id_value"] = "1"
            db_path = [p for p in cfg["required_inputs"] if p.endswith("crm.db")][0]
            conn = sqlite3.connect(db_path)
            # The temporary fixture already creates table t with column id
            # INTEGER (see _make_temp_config). Reuse that existing column
            # instead of duplicating it, and insert one deterministic row
            # whose id is compatible with cfg["ua0009_id_value"] == "1".
            conn.execute("INSERT INTO t (id) VALUES (1)")
            conn.commit()
            conn.close()

            calls = []
            original = sqlite_ownership.collect_ua0009_ownership_evidence

            def spy(*a, **kw):
                calls.append(a)
                return original(*a, **kw)

            with mock.patch.object(gate_a.sqlite_ownership, "collect_ua0009_ownership_evidence", spy):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertEqual(len(calls), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# SQLite before/after ordering (not adjacent, surrounding the workload)
# ---------------------------------------------------------------------------

class SqliteBeforeAfterOrderingTests(unittest.TestCase):
    def test_sqlite_calls_surround_the_full_workload(self):
        cfg, tmp = _make_temp_config()
        try:
            cfg["ua0009_table"] = "t"
            cfg["ua0009_id_column"] = "rowid"
            cfg["ua0009_id_value"] = "1"
            events = []
            original_sqlite = sqlite_ownership.collect_ua0009_ownership_evidence
            original_transform = gate_a.transform_cars_ui

            def spy_sqlite(*a, **kw):
                events.append("sqlite")
                return original_sqlite(*a, **kw)

            def spy_transform(*a, **kw):
                events.append("transform")
                return original_transform(*a, **kw)

            with mock.patch.object(gate_a.sqlite_ownership, "collect_ua0009_ownership_evidence", spy_sqlite), \
                 mock.patch.object(gate_a, "transform_cars_ui", spy_transform):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())

            self.assertGreaterEqual(len(events), 3)
            self.assertEqual(events[0], "sqlite")
            self.assertEqual(events[-1], "sqlite")
            self.assertIn("transform", events)
            self.assertGreater(events.index("transform"), events.index("sqlite"))
            self.assertLess(events.index("transform"), len(events) - 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# PII safety
# ---------------------------------------------------------------------------

class PIISafetyTests(unittest.TestCase):
    def test_pii_seed_never_appears_in_receipt_manifest_or_report(self):
        cfg, tmp = _make_temp_config()
        try:
            db_path = [p for p in cfg["required_inputs"] if p.endswith("crm.db")][0]
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE ua0009 (id TEXT, secret TEXT)")
            conn.execute("INSERT INTO ua0009 (id, secret) VALUES ('UA-0009', ?)", (PII_SEED,))
            conn.commit()
            conn.close()
            cfg["ua0009_table"] = "ua0009"
            cfg["ua0009_id_column"] = "id"
            cfg["ua0009_id_value"] = "UA-0009"

            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            serialized = json.dumps(receipt, default=str)
            self.assertNotIn(PII_SEED, serialized)

            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            self.assertNotIn(PII_SEED, build_manifest.canonical_json(manifest))

            with open(os.path.join(run_dir, "report.md")) as fh:
                report_text = fh.read()
            self.assertNotIn(PII_SEED, report_text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Compile-only sanity for the modules touched by this task
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in ("crm_speed_gate_a.py", "build_manifest.py", "verify_gate_a.py", "test_task_035_integration.py"):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()
