# TASK 056 — Align one stale backup-ordering test with the mandatory complete evidence skeleton

## Authority and hard safety boundary

This is a narrow offline test-maintenance task for CRM-SPEED-001.

- Modify **only** the supplied test file plus the three reporting/status files listed below.
- Do not modify `crm_speed_gate_a.py` or any other product/module source.
- Do not run Gate A.
- Do not access PythonAnywhere.
- Do not touch Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, schedules, or UA-0009.
- All validation is offline against temporary fixtures only.

## Exact observed result

Independent controller audit of commit `0df9bae057d88ab0aab17da072b1d254098eefa5`:

- Python static compile: PASS.
- Full discovery: 313 tests.
- 312 PASS, 1 FAIL, 0 ERROR, 0 SKIP.
- No background exception.

The only failure is:

`test_task_032_orchestration.BackupOrderingTests.test_backup_mismatch_blocks_before_candidate_creation`

It currently asserts that `candidates_compile` is absent. That is stale and directly contradicts TASK 055's mandatory fail-closed contract: before receipt emission every key in `REQUIRED_PREDICATES` must exist as a dict whose status is exactly `OK` or `BLOCKED`. On an early backup mismatch, `candidates_compile` must therefore be present as:

```python
{"status": "BLOCKED", "reason": "skipped_due_to_prior_block"}
```

This is evidence-skeleton completion, not candidate creation.

## Required edit

In only `BackupOrderingTests.test_backup_mismatch_blocks_before_candidate_creation`:

1. Preserve the checks that the receipt is `BLOCKED` and contains `backup_verification_failed`.
2. Replace the stale `assertNotIn("candidates_compile", ...)` with exact assertions that:
   - `receipt["evidence"]["candidates_compile"]` is a dict;
   - status is `BLOCKED`;
   - reason is `skipped_due_to_prior_block`.
3. Preserve the meaning "before candidate creation" with a filesystem assertion that the run's `candidates` directory does not exist:
   `os.path.join(self.cfg["run_root"], receipt["run_id"], "candidates")`.
4. Do not weaken, skip, delete, rename, or mark expected-failure any test.
5. Make no unrelated formatting or behavior changes.

## Required output files — exactly these four

1. `cloud/crm_speed_optimization/test_task_032_orchestration.py`
2. `cloud/crm_speed_optimization/TASK_056_REPORT.md`
3. `cloud/latest_status.md`
4. `cloud/owner_reply.md`

Status must be `READY_FOR_CONTROLLER_REVIEW_TASK_056`, never `READY_FOR_GATE_A`.

## Exact current source to preserve except for the narrow assertion change

```python
"""Offline, deterministic tests for TASK 032: real orchestration entry
point, secure run lifecycle, measured phases, and manifest/verification
integrity. No network access. No /home/Carix paths. Only temporary
directories, local files, and fake HTTPS openers are used.
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import crm_speed_gate_a as gate_a
import build_manifest
import verify_gate_a
import RUN_GATE_A_CRM_SPEED as launcher

from test_crm_speed_gate_a import (
    CLEAN_CARS_UI, CLEAN_USERCUSTOMIZE, CLEAN_AVTOPEREDACHA,
    DB_FUNCTION_SOURCE, _FakeOpener,
)

CARS_UI_SIDE_EFFECT_SOURCE = """def gallery(update, context):
    undefined_name_reference_only_fails_if_executed()
def video_gallery(update, context): pass
def diag_photo_show(update, context): pass
def diag_video_show(update, context): pass
"""


def _fake_opener_404():
    return _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))


def _make_temp_config():
    tmp = tempfile.mkdtemp(prefix="task032_")
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    required = []
    for name in names:
        p = os.path.join(tmp, name)
        if name == "cars_ui.py":
            content = CLEAN_CARS_UI
        elif name == "usercustomize.py":
            content = CLEAN_USERCUSTOMIZE
        elif name == "avtoperedacha.py":
            content = CLEAN_AVTOPEREDACHA
        else:
            content = "# fixture" + os.linesep
        with open(p, "w") as fh:
            fh.write(content)
        required.append(p)

    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_path = os.path.join(tmp, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha = gate_a._sha256_file(backup_path)

    site_root1 = os.path.join(tmp, "site")
    site_root2 = os.path.join(tmp, "video")
    site_root3 = os.path.join(tmp, "public_html")
    for root in (site_root1, site_root2, site_root3):
        os.makedirs(root)
        with open(os.path.join(root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

    run_root = os.path.join(tmp, "qa_root")
    os.makedirs(run_root, mode=0o700)

    config = {
        "required_inputs": required,
        "site_roots": {
            site_root1: ["index.html", "katalog.html"],
            site_root2: ["index.html", "katalog.html"],
            site_root3: ["index.html", "katalog.html"],
        },
        "ua0009_url": "https://example.com/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": [],
        "db_function_source": DB_FUNCTION_SOURCE,
        "min_free_bytes": 1024,
    }
    return config, tmp


class _TempConfigCase(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_temp_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class LauncherTests(unittest.TestCase):
    def test_launcher_calls_orchestration_and_propagates_pass(self):
        fake_receipt = {
            "status": "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL",
            "run_id": "x", "unmet_predicates": [], "phases": [], "production_write": "NO",
        }
        calls = []

        def fake_orchestrate(cfg):
            calls.append(cfg)
            return fake_receipt

        rc = launcher.main(orchestrate=fake_orchestrate, config={"marker": True})
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"marker": True}])

    def test_launcher_propagates_blocked_nonzero(self):
        fake_receipt = {
            "status": "BLOCKED", "run_id": "x", "unmet_predicates": ["a"],
            "phases": [], "production_write": "NO",
        }
        rc = launcher.main(orchestrate=lambda cfg: fake_receipt, config={})
        self.assertEqual(rc, 1)

    def test_launcher_internal_error_is_nonzero(self):
        def boom(cfg):
            raise RuntimeError("deliberate")
        rc = launcher.main(orchestrate=boom, config={})
        self.assertEqual(rc, 1)


class RunDirCreationTests(_TempConfigCase):
    def test_exactly_one_validated_run_dir_created_before_safewriter(self):
        seen = []
        original_init = gate_a.SafeWriter.__init__

        def spy_init(self, run_dir):
            seen.append(os.path.isdir(run_dir) and not os.path.islink(run_dir))
            return original_init(self, run_dir)

        with mock.patch.object(gate_a.SafeWriter, "__init__", spy_init):
            gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        self.assertTrue(seen)
        self.assertTrue(all(seen))
        subdirs = [
            d for d in os.listdir(self.cfg["run_root"])
            if os.path.isdir(os.path.join(self.cfg["run_root"], d))
        ]
        self.assertEqual(len(subdirs), 1)


class SecureInputTests(_TempConfigCase):
    def test_symlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        os.symlink(os.path.join(self.tmp, "crm.db"), target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("symlink_input" in b for b in receipt.get("blockers", [])))

    def test_missing_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("missing_input" in b for b in receipt.get("blockers", [])))

    def test_hardlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        other = os.path.join(self.tmp, "other_copy.py")
        os.link(target, other)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("hard_linked_input" in b for b in receipt.get("blockers", [])))


class BackupOrderingTests(_TempConfigCase):
    def test_backup_mismatch_blocks_before_candidate_creation(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertNotIn("candidates_compile", receipt["evidence"])
        self.assertTrue(any("backup_verification_failed" in b for b in receipt.get("blockers", [])))


class LockDuplicateTests(_TempConfigCase):
    def test_duplicate_lock_returns_promptly_without_altering_owner_evidence(self):
        qa_root_real = os.path.realpath(self.cfg["run_root"])
        holder = canonical_modules.CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        self.assertTrue(holder.acquire())
        try:
            before = holder._read_evidence()
            t0 = time.time()
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
            elapsed = time.time() - t0
            after = holder._read_evidence()
            self.assertLess(elapsed, 2.0)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertIn("gate_a_lock_held", receipt.get("blockers", []))
            self.assertEqual(before.token, after.token)
        finally:
            holder.release()


class PhaseOrderTests(_TempConfigCase):
    def test_phase_order_and_measured_durations(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        phase_nums = [p["phase"] for p in receipt["phases"]]
        self.assertEqual(phase_nums, [20, 40, 60, 80, 100])
        for p in receipt["phases"]:
            self.assertGreaterEqual(p["end"], p["start"])
            self.assertGreaterEqual(p["duration"], 0)
        self.assertEqual(receipt["phases"][-1]["status"], "finished")


class InventorySurroundTests(_TempConfigCase):
    def test_inventories_surround_entire_workload(self):
        call_count = {"n": 0}
        original = gate_a.scan_bounded_inventory

        def counting(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        with mock.patch.object(gate_a, "scan_bounded_inventory", counting):
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        n_roots = len(self.cfg["site_roots"])
        self.assertEqual(call_count["n"], n_roots * 2)
        self.assertIn("before", receipt["site_inventories"])
        self.assertIn("after", receipt["site_inventories"])


class CompileOnlyTests(_TempConfigCase):
    def test_candidates_compile_without_import_execution(self):
        cars_ui_path = [p for p in self.cfg["required_inputs"] if p.endswith("cars_ui.py")][0]
        with open(cars_ui_path, "w") as fh:
            fh.write(CARS_UI_SIDE_EFFECT_SOURCE)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIn("candidates_compile", receipt["evidence"])
        self.assertEqual(receipt["evidence"]["candidates_compile"]["status"], "OK")


def _clean_pass_fixture(tmp):
    required = []
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    for name in names:
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write("# fixture" + os.linesep)
        required.append(p)
    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_archive = os.path.join(tmp, "backup.tar.gz")
    with open(backup_archive, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha256 = gate_a._sha256_file(backup_archive)

    site_root = os.path.join(tmp, "site")
    os.makedirs(site_root)
    with open(os.path.join(site_root, "index.html"), "w") as fh:
        fh.write("<html></html>")
    with open(os.path.join(site_root, "katalog.html"), "w") as fh:
        fh.write("<html></html>")

    run_dir = os.path.join(tmp, "run")
    fp = {"a": 1}
    return {
        "required_inputs": required,
        "backup_archive": backup_archive,
        "backup_archive_sha256": backup_sha256,
        "cars_ui_source": CLEAN_CARS_UI,
        "usercustomize_source": CLEAN_USERCUSTOMIZE,
        "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
        "protected_fingerprints_before": fp,
        "protected_fingerprints_after": dict(fp),
        "db_path": db_path,
        "ua0009_fingerprint_before": {"h": "same"},
        "ua0009_fingerprint_after": {"h": "same"},
        "ua0009_url": "https://example.com/UA-0009.html",
        "ua0009_opener": _fake_opener_404(),
        "site_root": site_root,
        "allowed_site_names": ["index.html", "katalog.html"],
        "protected_function_names": ["upload_media", "delete_media"],
        "tmp_dir": tmp,
        "db_function_source": DB_FUNCTION_SOURCE,
        "site_before": {"x": 1},
        "site_after": {"x": 1},
        "run_dir": run_dir,
    }


class ManifestVerifyTests(_TempConfigCase):
    def test_receipt_and_manifest_hash_tamper_detected(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIsNotNone(receipt.get("run_id"))
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        self.assertTrue(os.path.isdir(run_dir))

        package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
        manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)

        receipt_path = os.path.join(run_dir, "receipt.json")
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertTrue(ok, reason)

        with open(receipt_path, "r") as fh:
            data = fh.read()
        with open(receipt_path, "w") as fh:
            fh.write(data + os.linesep + "tampered")

        ok2, reason2 = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertFalse(ok2)

    def test_missing_required_predicate_blocks_verification(self):
        tmp2 = tempfile.mkdtemp(prefix="task032_legacy_")
        try:
            fixture = _clean_pass_fixture(tmp2)
            receipt = gate_a.run_gate_a(fixture)
            self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL")
            del receipt["evidence"]["backup_verified"]
            receipt_path = os.path.join(tmp2, "tampered_receipt.json")
            with open(receipt_path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(receipt_path)
            self.assertFalse(ok)
            self.assertTrue(reason.startswith("missing_or_malformed_predicate"))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_altered_candidate_diff_report_blocks_verification(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
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


class BlockedNonzeroTests(_TempConfigCase):
    def test_blocked_orchestration_returns_nonzero_with_complete_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64

        def orchestrate(cfg):
            return gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())

        rc = launcher.main(orchestrate=orchestrate, config=self.cfg)
        self.assertEqual(rc, 1)

    def test_blocked_receipt_has_bounded_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("phases", receipt)
        self.assertIn("blockers", receipt)
        self.assertEqual(receipt["production_write"], "NO")


class RebuildQueueAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task032_rq_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_slow_callback_still_yields_prompt_enqueue_return(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        release_cb = threading.Event()

        def slow_cb():
            release_cb.wait(timeout=3)

        q = canonical_modules.RebuildQueue(slow_cb, lock_path)
        t0 = time.time()
        status = q.enqueue()
        elapsed = time.time() - t0
        self.assertEqual(status, "accepted")
        self.assertLess(elapsed, 0.20)
        release_cb.set()
        q.shutdown(timeout=5)

    def test_immediate_observation_sees_callback_entry(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        entered = threading.Event()

        def cb():
            entered.set()

        q = canonical_modules.RebuildQueue(cb, lock_path)
        status = q.enqueue()
        self.assertEqual(status, "accepted")
        self.assertTrue(entered.is_set())
        q.shutdown(timeout=5)


if __name__ == "__main__":
    unittest.main()

```
