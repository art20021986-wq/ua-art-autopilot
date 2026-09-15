"""Isolated interruption/retained-evidence tests, with no live services."""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("checkpoint_inspect", HERE / "checkpoint_inspect.py")
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)
NOW = dt.datetime(2026, 9, 14, 18, tzinfo=dt.timezone.utc)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def put(self, name, value):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"path": name, "sha256": ci.sha(raw), "bytes": len(raw)}

    def fixture(self):
        source = self.put("cloud/builder.py", b"# original bytes\n")
        report = {"source_files_sha256": {source["path"]: source["sha256"]},
                  "builder_sha256": source["sha256"], "source_manifest_sha256": "a" * 64,
                  "finished_at": "2026-09-14T16:00:00Z"}
        report_ref = self.put("reports/software.json", report)
        quota_ref = self.put("reports/quota.json", {"observed_at": "2026-09-14T16:41:42.701Z"})
        checkpoint = {"recorded_at": "2026-09-14T17:44:28.847Z", "software": {**report, "report": report_ref},
                      "quota": quota_ref, "quota_observed_at": "2026-09-14T16:41:42.701Z",
                      "full_preview_gate": "NOT_PASSED", "stage3": "OPEN_NOT_PUBLISHED", "stage4": "OPEN_NOT_ACCEPTED"}
        self.put("checkpoint.json", checkpoint)
        return checkpoint

    def operation(self, status="RUNNING", with_receipt=True):
        request = self.put("tasks/requests/TASK088-TEST.json", {"task_id": "TASK088-TEST", "execution": {"receipt_path": "state/receipts/TASK088-TEST.json"}})
        receipt = self.put("state/receipts/TASK088-TEST.json", {
            "task_id": "TASK088-TEST", "run_id": "123", "request_sha256": request["sha256"], "status": "FINISHED"})
        claim = {"identity": {"task_id": "TASK088-TEST", "run_id": "123", "task_sha256": request["sha256"]},
                 "task_execution_status": status, "request_path": request["path"], "request_sha256": request["sha256"]}
        if with_receipt:
            claim.update(receipt_path=receipt["path"], receipt_sha256=receipt["sha256"])
        self.put("state/claims/TASK088-TEST.json", claim)
        return claim

    def test_unchanged_evidence_retained_without_rerun_or_timestamp_refresh(self):
        cp = self.fixture()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["reference_integrity"], "MATCH")
        self.assertEqual(result["software"]["disposition"], "RETAIN_UNCHANGED_HISTORICAL_RESULT")
        self.assertEqual(result["software"]["original_finished_at"], cp["software"]["finished_at"])
        self.assertEqual(result["saved_open_stages"]["full_preview_gate"], "NOT_PASSED")
        self.assertFalse(result["execution_authorized"])

    def test_source_drift_identifies_changed_scope(self):
        self.fixture()
        self.put("cloud/builder.py", b"# changed bytes\n")
        result = ci.inspect(self.root, "checkpoint.json", NOW)["software"]
        self.assertEqual(result["disposition"], "RECONCILE_CHANGED_SCOPE_BEFORE_SELECTIVE_RERUN")
        self.assertEqual([x["path"] for x in result["source_differences"]], ["cloud/builder.py"])

    def test_audit_notice_supersedes_stale_pending_prompt_narrative(self):
        cp = self.fixture()
        cp.update(next_actions=["Owner enters token into active hidden prompt"],
                  audit_continuation_notice="AUDIT_CONTINUATION_NOTICE.json")
        self.put("checkpoint.json", cp)
        self.put("AUDIT_CONTINUATION_NOTICE.json", {
            "observed_at": "2026-09-14T17:44:28.847Z",
            "credential_console": {"state": "SHELL_PROMPT_RECEIVER_EXITED"}})
        report = ci.inspect(self.root, "checkpoint.json", NOW)
        self.assertEqual(report["continuation_notice"]["last_saved_console_state"], "SHELL_PROMPT_RECEIVER_EXITED")
        self.assertTrue(report["continuation_notice"]["requires_current_readback"])
        self.assertNotIn("Owner enters token", json.dumps(report))

    def test_missing_and_corrupted_evidence_do_not_become_completed(self):
        self.fixture()
        self.put("reports/software.json", b"corrupted")
        (self.root / "reports/quota.json").unlink()
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        self.assertEqual(result["reference_integrity"], "INCOMPLETE")
        self.assertEqual(len(result["reference_issues"]), 2)
        self.assertEqual(result["software"]["disposition"], "RESTORE_OR_RECONCILE_MISSING_EVIDENCE")

    def test_quota_uses_original_raw_timestamp_not_updated_checkpoint(self):
        cp = self.fixture()
        cp["quota_observed_at"] = NOW.isoformat()
        self.put("checkpoint.json", cp)
        result = ci.inspect(self.root, "checkpoint.json", NOW)["quota"]
        self.assertEqual(result["status"], "EXPIRED")
        self.assertFalse(result["checkpoint_timestamp_matches_raw"])
        self.assertEqual(result["observed_at"], "2026-09-14T16:41:42.701Z")

    def test_freshness_boundary_future_and_missing(self):
        self.assertEqual(ci.freshness("2026-09-14T17:30:00Z", NOW, 1800)["status"], "EXPIRED")
        self.assertEqual(ci.freshness("2026-09-14T17:30:01Z", NOW, 1800)["status"], "WITHIN_TIME_WINDOW_ONLY")
        self.assertEqual(ci.freshness("2026-09-14T18:00:01Z", NOW, 1800)["status"], "FUTURE_INVALID")
        self.assertEqual(ci.freshness("2026-09-14T17:55:00", NOW, 1800)["status"], "MISSING_OR_INVALID")

    def test_success_before_ack_requires_reconciliation_never_replay(self):
        self.fixture()
        self.operation(status="RUNNING", with_receipt=True)
        # Simulates external operation success with persisted receipt before a
        # process crash, leaving claim RUNNING. A newly loaded inspector sees it.
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        operation = result["operations"][0]
        self.assertEqual(operation["receipt_integrity"]["status"], "MATCH")
        self.assertEqual(operation["disposition"], "RECONCILE_EXISTING_OPERATION")
        self.assertFalse(operation["replay_allowed"])
        self.assertEqual(result["next_action"], "READ_CURRENT_GIT_SERVER_AND_RECEIPTS")
        self.assertEqual(result["historical_records_requiring_classification"], 1)

    def test_missing_receipt_is_not_permission_even_for_terminal_claim(self):
        self.fixture()
        self.operation(status="FINISHED", with_receipt=False)
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertEqual(result["disposition"], "RECONCILE_EXISTING_OPERATION")
        self.assertIn("RECEIPT_MISSING_OR_CHANGED", result["binding_issues"])
        self.assertFalse(result["replay_allowed"])

    def test_receipt_wrong_identity_requires_reconciliation(self):
        self.fixture()
        claim = self.operation(status="FINISHED")
        receipt = self.put("state/receipts/wrong.json", {"task_id": "ANOTHER_TASK", "run_id": "123", "request_sha256": claim["request_sha256"]})
        claim.update(receipt_path=receipt["path"], receipt_sha256=receipt["sha256"])
        self.put("state/claims/TASK088-TEST.json", claim)
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertIn("RECEIPT_IDENTITY_MISMATCH:task_id", result["binding_issues"])

    def test_terminal_snapshot_never_authorizes_action(self):
        self.fixture()
        self.operation(status="FINISHED")
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        self.assertEqual(result["operations"][0]["disposition"], "RETAIN_TERMINAL_LOCAL_RECORD")
        self.assertFalse(result["retry_authorized"])
        self.assertEqual(result["next_action"], "READ_CURRENT_GIT_SERVER_AND_RECEIPTS")

    def test_request_changed_after_claim_is_reconciled(self):
        self.fixture()
        self.operation(status="FINISHED")
        self.put("tasks/requests/TASK088-TEST.json", {"task_id": "TASK088-TEST", "changed": True})
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertIn("REQUEST_HASH_MISSING_OR_CHANGED", result["binding_issues"])

    def test_failed_receipt_cannot_confirm_finished_claim(self):
        self.fixture()
        claim = self.operation(status="FINISHED")
        receipt_path = self.root / claim["receipt_path"]
        receipt = json.loads(receipt_path.read_bytes())
        receipt["status"] = "FAILED"
        ref = self.put(claim["receipt_path"], receipt)
        claim["receipt_sha256"] = ref["sha256"]
        self.put("state/claims/TASK088-TEST.json", claim)
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertEqual(result["disposition"], "RECONCILE_EXISTING_OPERATION")
        self.assertIn("RECEIPT_TERMINAL_STATUS_NOT_CONFIRMED", result["binding_issues"])

    def test_correct_receipt_at_unrequested_path_requires_reconciliation(self):
        self.fixture()
        claim = self.operation(status="FINISHED")
        ref = self.put("unrelated/receipt.json", (self.root / claim["receipt_path"]).read_bytes())
        claim.update(receipt_path=ref["path"], receipt_sha256=ref["sha256"])
        self.put("state/claims/TASK088-TEST.json", claim)
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertIn("RECEIPT_REQUEST_PATH_MISMATCH", result["binding_issues"])

    def test_orphan_terminal_transaction_requires_reconciliation(self):
        self.fixture()
        claim = self.operation(status="FINISHED")
        (self.root / "state/claims/TASK088-TEST.json").unlink()
        self.put("state/transactions/TASK088-TEST.json", {
            "status": "FINISHED", "task_id": "TASK088-TEST", "run_id": "123",
            "request_path": claim["request_path"], "request_sha256": claim["request_sha256"]})
        result = ci.inspect(self.root, "checkpoint.json", NOW)["operations"][0]
        self.assertEqual(result["disposition"], "RECONCILE_EXISTING_OPERATION")
        self.assertIn("TERMINAL_TRANSACTION_CLAIM_MISSING_OR_INVALID", result["binding_issues"])

    def test_nonobject_record_is_reported_without_aborting_inspection(self):
        self.fixture()
        self.put("state/claims/TASK088-TEST.json", [])
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        self.assertEqual(result["operations"][0]["disposition"], "RECONCILE_INVALID_LOCAL_RECORD")

    def test_new_checkout_with_only_pinned_archive_restores_software_without_writes(self):
        cp = self.fixture()
        raw = (self.root / cp["software"]["report"]["path"]).read_bytes()
        (self.root / cp["software"]["report"]["path"]).unlink()
        report_path = "cloud/task088_v5_acceptance/resume_20260914/software/gallery_fix_v2/FINAL_CURRENT_CANDIDATE_RESULTS.json"
        cp["software"]["report"].update(path=report_path)
        archive_path = "cloud/PR114_GALLERY_V2_SOFTWARE_EVIDENCE_20260914.zip"
        (self.root / archive_path).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.root / archive_path, "w") as z:
            z.writestr("gallery_fix_v2/FINAL_CURRENT_CANDIDATE_RESULTS.json", raw)
        cp["archive_index"] = [self.put(archive_path, (self.root / archive_path).read_bytes())]
        self.put("checkpoint.json", cp)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = ci.inspect(self.root, "checkpoint.json", NOW)
        self.assertEqual(result["software"]["report_integrity"]["source"], "PINNED_ARCHIVE_MEMBER_NO_EXTRACTION")
        self.assertEqual(result["software"]["source_files_checked"], 1)
        self.assertEqual(result["software"]["disposition"], "RETAIN_UNCHANGED_HISTORICAL_RESULT")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        # A present changed direct file is never masked by historical archive bytes.
        self.put(report_path, b"changed")
        self.assertEqual(ci.inspect(self.root, "checkpoint.json", NOW)["software"]["report_integrity"]["status"], "MISMATCH")

    def test_path_escape_and_symlink_are_rejected(self):
        self.fixture()
        ref = {"path": "../outside", "sha256": "a" * 64}
        self.assertEqual(ci.verify_ref(self.root, ref)["status"], "MISSING_OR_INVALID")
        (self.root / "linked").symlink_to(self.root / "reports", target_is_directory=True)
        raw = (self.root / "reports/software.json").read_bytes()
        self.assertEqual(ci.verify_ref(self.root, {"path": "linked/software.json", "sha256": ci.sha(raw)})["status"], "MISSING_OR_INVALID")

    def crash_writer(self, stage):
        directory = self.root / "reports"
        pid = os.fork()
        if pid == 0:
            ci.atomic_report(directory, "step", {"original_observed_at": "unchanged"},
                             hook=lambda reached: os._exit(77) if reached == stage else None)
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 77)
        return directory

    def test_crash_before_publish_leaves_no_partial_final_and_retains_previous(self):
        previous = ci.atomic_report(self.root / "reports", "previous", {"batch": 1})
        original = previous.read_bytes()
        directory = self.crash_writer("before_publish")
        self.assertEqual(list(directory.glob("step.*.json")), [])
        self.assertEqual(previous.read_bytes(), original)
        self.assertTrue(list(directory.glob(".partial-*")))

    def test_crash_after_publish_before_ack_finds_same_complete_report(self):
        directory = self.crash_writer("after_publish_before_ack")
        files = list(directory.glob("step.*.json"))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_bytes())
        resumed = ci.atomic_report(directory, "step", saved)
        self.assertEqual(resumed, files[0])
        self.assertEqual(len(list(directory.glob("step.*.json"))), 1)

    def test_new_batch_preserves_all_previous_reports(self):
        one = ci.atomic_report(self.root / "reports", "step", {"batch": 1})
        two = ci.atomic_report(self.root / "reports", "step", {"batch": 2})
        self.assertNotEqual(one, two)
        self.assertEqual(json.loads(one.read_bytes()), {"batch": 1})
        self.assertEqual(json.loads(two.read_bytes()), {"batch": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
