"""TASK 055 focused orchestrator tests.

These tests exercise crm_speed_gate_a.orchestrate_gate_a() end to end
against temporary, offline fixtures only. All real transform/probe/
sqlite-ownership dependencies are deterministically mocked at the
module-attribute level so this file tests ONLY the TASK 055
orchestrator-level behavior:

  - early transform block produces every REQUIRED_PREDICATES key with
    an OK/BLOCKED status and a final BLOCKED gate status;
  - accepted_candidate_set is False for original compile-only evidence
    produced on an early block;
  - the canonical publication probe spy is invoked exactly once, both
    on an early block (via the phase100 fallback) and on the normal
    successful path (via phase80);
  - a successful candidate-source fixture yields exactly the eight
    expected candidate names/hashes/install mapping, never a ninth
    legacy usercustomize.py key.

No network, no PythonAnywhere, no Production, no Gate A execution
against real inputs -- only temporary directories and fully offline,
deterministic in-process mocks.

NOTE ON RECEIPT/MANIFEST VERIFICATION: the exact source of the
repository's real receipt/manifest verifier module was not part of the
exact-source input supplied for TASK 055, so this file does not import
an assumed external verifier API. Instead it uses a small, local,
self-contained hash-binding helper (defined below) to exercise the same
untampered/receipt-tamper/report-tamper semantics described in the
TASK 055 requirements, using only the receipt.json/report.md bytes that
orchestrate_gate_a() itself writes via SafeWriter. This does not modify
any production, candidate_transforms, sqlite_ownership,
canonical_modules, or verifier module.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock

import crm_speed_gate_a as gate_a


SAFE_CARS_UI_SOURCE = (
    "def gallery():\n    return None\n\n"
    "def video_gallery():\n    return None\n\n"
    "def diag_photo_show():\n    return None\n\n"
    "def diag_video_show():\n    return None\n"
)


class FakeOwnershipEvidence:
    def __init__(self, status="OK", reason=None, **kwargs):
        self.status = status
        self.reason = reason
        self.extra = kwargs

    def to_dict(self):
        return {"status": self.status, "reason": self.reason}


def _fake_transform_cars_ui_ok(source, entry_points=None):
    return {"candidate": SAFE_CARS_UI_SOURCE, "status": "OK", "reasons": []}


def _fake_transform_cars_ui_blocked(source, entry_points=None):
    return {"candidate": None, "status": "BLOCKED", "reasons": ["forced_test_block"]}


def _fake_transform_usercustomize(source, tag):
    return {"candidate": "", "status": "OK", "reasons": []}


def _fake_transform_launcher_singleton(source, lock_path):
    return {"candidate": "x = 1\n", "status": "OK", "reasons": []}


def _fake_transform_avtoperedacha_rebuild(source):
    return {"candidate": "", "status": "OK", "reasons": []}


def _fake_transform_sqlite_short_ownership(source):
    return {"candidate": "", "status": "OK", "reasons": []}


def _fake_generate_runtime_support_source():
    return "# support module\n"


def _fake_check_db_closed(source):
    return {"status": "OK"}


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _make_sqlite_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()


def _build_success_config(tmp_root):
    run_root = os.path.join(tmp_root, "run_root")
    os.makedirs(run_root, exist_ok=True)

    uc310 = _write(os.path.join(tmp_root, "python3.10", "site-packages", "usercustomize.py"), "")
    uc313 = _write(os.path.join(tmp_root, "python3.13", "site-packages", "usercustomize.py"), "")
    start_safe = _write(os.path.join(tmp_root, "start_safe.py"), "x = 1\n")
    run_all = _write(os.path.join(tmp_root, "run_all.py"), "x = 1\n")
    cars_ui = _write(os.path.join(tmp_root, "cars_ui.py"), SAFE_CARS_UI_SOURCE)
    avtoperedacha = _write(os.path.join(tmp_root, "avtoperedacha.py"), "")
    samokontrol = _write(os.path.join(tmp_root, "samokontrol.py"), "")

    db_path = os.path.join(tmp_root, "crm.db")
    _make_sqlite_db(db_path)

    backup_bytes = b"fake-backup-bytes-task-055"
    backup_path = os.path.join(tmp_root, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(backup_bytes)
    backup_sha = hashlib.sha256(backup_bytes).hexdigest()

    site_root = os.path.join(tmp_root, "site")
    os.makedirs(site_root, exist_ok=True)

    return {
        "required_inputs": [uc310, uc313, start_safe, run_all, cars_ui, avtoperedacha, samokontrol, db_path],
        "site_roots": {site_root: ["index.html"]},
        "ua0009_url": "https://example.invalid/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": ["gallery"],
        "db_function_source": None,
        "min_free_bytes": 1,
        "ua0009_table": "cards",
        "ua0009_id_column": "id",
        "ua0009_id_value": "UA-0009",
    }


def _patch_sqlite_ownership(stack):
    stack.enter_context(mock.patch.object(gate_a.sqlite_ownership, "OwnershipEvidence", FakeOwnershipEvidence))
    stack.enter_context(mock.patch.object(
        gate_a.sqlite_ownership, "collect_ua0009_ownership_evidence",
        lambda *a, **k: FakeOwnershipEvidence(status="OK")))
    stack.enter_context(mock.patch.object(
        gate_a.sqlite_ownership, "compare_ownership_evidence",
        lambda before, after: (True, "unchanged")))


def _patch_success_transforms(stack):
    stack.enter_context(mock.patch.object(gate_a, "transform_cars_ui", _fake_transform_cars_ui_ok))
    stack.enter_context(mock.patch.object(gate_a, "_verify_launcher_candidate_structural", lambda *a, **k: True))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "transform_usercustomize", _fake_transform_usercustomize))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "transform_launcher_singleton", _fake_transform_launcher_singleton))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "transform_avtoperedacha_rebuild", _fake_transform_avtoperedacha_rebuild))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "transform_sqlite_short_ownership", _fake_transform_sqlite_short_ownership))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "generate_runtime_support_source", _fake_generate_runtime_support_source))
    stack.enter_context(mock.patch.object(gate_a.candidate_transforms, "check_db_closed_before_slow_work_candidate", _fake_check_db_closed))
    _patch_sqlite_ownership(stack)


def _make_probe_spy(status="PASS", reason="not_served_404", status_code=404):
    return mock.MagicMock(return_value=SimpleNamespace(status=status, reason=reason, status_code=status_code))


def _write_manifest(run_dir):
    receipt_path = os.path.join(run_dir, "receipt.json")
    report_path = os.path.join(run_dir, "report.md")
    with open(receipt_path, "rb") as fh:
        receipt_hash = hashlib.sha256(fh.read()).hexdigest()
    with open(report_path, "rb") as fh:
        report_hash = hashlib.sha256(fh.read()).hexdigest()
    manifest = {"receipt_sha256": receipt_hash, "report_sha256": report_hash}
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh)
    return manifest_path


def _verify_receipt_report_against_manifest(run_dir):
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    receipt_path = os.path.join(run_dir, "receipt.json")
    report_path = os.path.join(run_dir, "report.md")
    with open(receipt_path, "rb") as fh:
        actual_receipt_hash = hashlib.sha256(fh.read()).hexdigest()
    with open(report_path, "rb") as fh:
        actual_report_hash = hashlib.sha256(fh.read()).hexdigest()
    if actual_receipt_hash != manifest["receipt_sha256"]:
        return False, "receipt_hash_mismatch"
    if actual_report_hash != manifest["report_sha256"]:
        return False, "report_hash_mismatch"
    return True, None


class TestTask055OrchestratorFinal(unittest.TestCase):
    def setUp(self):
        self.tmp_root = tempfile.mkdtemp(prefix="task055_")

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_early_block_predicate_skeleton_complete_and_final_blocked(self):
        config = _build_success_config(self.tmp_root)
        with ExitStack() as stack:
            _patch_sqlite_ownership(stack)
            stack.enter_context(mock.patch.object(gate_a, "transform_cars_ui", _fake_transform_cars_ui_blocked))
            probe_spy = _make_probe_spy()
            stack.enter_context(mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", probe_spy))
            receipt = gate_a.orchestrate_gate_a(config, opener=None)

        self.assertEqual(receipt["status"], "BLOCKED")
        for key in gate_a.REQUIRED_PREDICATES:
            item = receipt["evidence"].get(key)
            self.assertIsInstance(item, dict, key)
            self.assertIn(item.get("status"), ("OK", "BLOCKED"), key)

        cc = receipt["evidence"]["candidates_compile"]
        self.assertEqual(cc.get("accepted_candidate_set"), False)
        self.assertEqual(cc.get("candidate_origin"), "original_due_to_transform_block")
        self.assertEqual(probe_spy.call_count, 1)

    def test_successful_candidate_set_exactly_eight_and_probe_once(self):
        config = _build_success_config(self.tmp_root)
        with ExitStack() as stack:
            _patch_success_transforms(stack)
            probe_spy = _make_probe_spy()
            stack.enter_context(mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", probe_spy))
            receipt = gate_a.orchestrate_gate_a(config, opener=None)

        expected_names = {
            "usercustomize_py310.py", "usercustomize_py313.py", "start_safe.py",
            "run_all.py", "cars_ui.py", "avtoperedacha.py", "samokontrol.py",
            "crm_speed_runtime.py",
        }
        self.assertEqual(set(receipt["package_hashes"].keys()), expected_names)
        self.assertEqual(set(receipt["extended_candidates"]["candidate_hashes"].keys()), expected_names)
        self.assertNotIn("usercustomize.py", receipt["package_hashes"])
        self.assertTrue(receipt["extended_candidates"]["available"])
        self.assertEqual(receipt["extended_candidates"]["support_module_install_target"], "crm_speed_runtime.py")
        self.assertEqual(probe_spy.call_count, 1)

        for key in gate_a.REQUIRED_PREDICATES:
            item = receipt["evidence"].get(key)
            self.assertIsInstance(item, dict, key)
            self.assertIn(item.get("status"), ("OK", "BLOCKED"), key)

    def test_blocked_receipt_manifest_verifies_then_receipt_tamper_detected(self):
        config = _build_success_config(self.tmp_root)
        with ExitStack() as stack:
            _patch_sqlite_ownership(stack)
            stack.enter_context(mock.patch.object(gate_a, "transform_cars_ui", _fake_transform_cars_ui_blocked))
            probe_spy = _make_probe_spy()
            stack.enter_context(mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", probe_spy))
            receipt = gate_a.orchestrate_gate_a(config, opener=None)

        self.assertEqual(receipt["status"], "BLOCKED")
        run_dir = os.path.join(config["run_root"], receipt["run_id"])
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "receipt.json")))
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "report.md")))

        _write_manifest(run_dir)
        ok, reason = _verify_receipt_report_against_manifest(run_dir)
        self.assertTrue(ok)
        self.assertIsNone(reason)

        receipt_path = os.path.join(run_dir, "receipt.json")
        with open(receipt_path, "a") as fh:
            fh.write("\n// tampered\n")
        ok, reason = _verify_receipt_report_against_manifest(run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "receipt_hash_mismatch")

    def test_blocked_report_tamper_detected(self):
        config = _build_success_config(self.tmp_root)
        with ExitStack() as stack:
            _patch_sqlite_ownership(stack)
            stack.enter_context(mock.patch.object(gate_a, "transform_cars_ui", _fake_transform_cars_ui_blocked))
            probe_spy = _make_probe_spy()
            stack.enter_context(mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", probe_spy))
            receipt = gate_a.orchestrate_gate_a(config, opener=None)

        run_dir = os.path.join(config["run_root"], receipt["run_id"])
        _write_manifest(run_dir)
        report_path = os.path.join(run_dir, "report.md")
        with open(report_path, "a") as fh:
            fh.write("\n// tampered report\n")
        ok, reason = _verify_receipt_report_against_manifest(run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "report_hash_mismatch")

    def test_probe_never_called_twice_across_full_invocation(self):
        config = _build_success_config(self.tmp_root)
        with ExitStack() as stack:
            _patch_success_transforms(stack)
            probe_spy = _make_probe_spy()
            stack.enter_context(mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", probe_spy))
            receipt = gate_a.orchestrate_gate_a(config, opener=None)
        self.assertLessEqual(probe_spy.call_count, 1)
        self.assertEqual(receipt["publication_result"], receipt["evidence"].get("ua0009_not_public"))


if __name__ == "__main__":
    unittest.main()
