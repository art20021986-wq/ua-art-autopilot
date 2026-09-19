"""Isolated failure/competition tests; all provider facts are explicit fixtures."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from state_machine import Journal, Protocol, Rejected, digest


def fixture_plan():
    return {
        "contract": "TASK088-ISOLATED-QUIESCENCE-PROTOTYPE-1", "task_id": "TEST-ISOLATED-088",
        "operation_id": "test-operation-0001", "reviewed_code_sha256": "1" * 64, "authorization_sha256": "2" * 64,
        "inventory_sha256": "3" * 64, "before_sources_sha256": "4" * 64, "candidate_sources_sha256": "5" * 64,
        "supervisors": [{"id": 266084, "command": "python3.10 /home/Carix/start_safe.py", "enabled": True}],
        "writers": [
            {"id": "test-photo-before-db", "mode": "MANAGED_PROCESS", "source_sha256": "6" * 64, "candidate_source_sha256": "16" * 32, "supervisor_id": 266084},
            {"id": "test-legacy-rebuild", "mode": "HELD_LOCK", "source_sha256": "7" * 64, "candidate_source_sha256": "17" * 32, "lock_path": "/home/Carix/example-test.lock"},
            {"id": "test-monitor", "mode": "READ_ONLY", "source_sha256": "8" * 64, "candidate_source_sha256": "8" * 64},
        ],
    }


def fixture_observation(*, paused=False, version="AFTER", installed=False):
    plan = fixture_plan()
    return {
        "operation_id": plan["operation_id"], "inventory_sha256": plan["inventory_sha256"],
        "observed_at": 1000, "raw_evidence_sha256": "a" * 64, "unaccounted_writers": [],
        "supervisors": [{"id": 266084, "command": plan["supervisors"][0]["command"], "enabled": not paused,
            "running": not paused, "membership_complete": True, "live_process_count": 0 if paused else 1,
            "in_flight_mutations": 0, "membership_evidence_sha256": "b" * 64, "exactly_one_instance": not paused}],
        "writers": [
            {"id": "test-photo-before-db", "source_sha256": "16" * 32 if installed else "6" * 64, "supervisor_id": 266084, "status": "STOPPED_AND_DRAINED", "evidence_sha256": "c" * 64},
            {"id": "test-legacy-rebuild", "source_sha256": "17" * 32 if installed else "7" * 64, "lock_path": "/home/Carix/example-test.lock", "status": "LOCK_HELD_AND_DRAINED", "lease_operation_id": plan["operation_id"], "evidence_sha256": "d" * 64},
            {"id": "test-monitor", "source_sha256": "8" * 64, "status": "READ_ONLY_PROVEN", "evidence_sha256": "e" * 64},
        ],
        "canonical_install_admission_pass": True, "canonical_admission_evidence_sha256": "f" * 64,
        "coherence": {
            "version": version, "sources_sha256": "5" * 64 if version == "AFTER" else "4" * 64,
            "complete_file_readback": True, "independent_database_readback": True, "schema_matches_version": True,
            "operator_changes_preserved": True, "protected_nonprice_content_preserved": True,
            "no_in_flight_installation": True, "backup_database_restored": False, "raw_evidence_sha256": "9" * 64,
        },
        "loaded_sources_sha256": "5" * 64 if version == "AFTER" else "4" * 64,
    }


class QuiescenceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "journal.jsonl"
        self.plan = fixture_plan()
        self.journal = Journal(self.path, self.plan)
        self.clock = 1000
        self.machine = Protocol(self.plan, self.journal, clock=lambda: self.clock)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def reopen(self):
        self.journal.close()
        self.journal = Journal(self.path, self.plan)
        self.machine = Protocol(self.plan, self.journal, clock=lambda: self.clock)

    def pause(self):
        self.machine.begin_pause(fixture_observation())
        self.machine.reconcile_pause(fixture_observation(paused=True))

    def apply(self):
        self.pause()
        self.machine.installation_boundary(fixture_observation(paused=True))

    def test_intent_is_durable_before_return_and_never_changes_id_or_command(self):
        intents = self.machine.begin_pause(fixture_observation())
        persisted = json.loads(self.path.read_bytes().splitlines()[-1])
        self.assertEqual(intents, persisted["intents"])
        self.assertEqual(intents[0]["supervisor_id"], 266084)
        self.assertEqual(intents[0]["expected_command"], self.plan["supervisors"][0]["command"])
        self.assertEqual(intents[0]["kind"], "PATCH_ENABLED_FALSE")

    def test_crash_after_durable_intent_before_delivery_requires_readback(self):
        self.machine.begin_pause(fixture_observation())
        self.reopen()
        with self.assertRaisesRegex(Rejected, "RECONCILIATION"):
            self.machine.begin_pause(fixture_observation())
        self.assertEqual(self.machine.outcome_unknown()[0]["kind"], "READ_ONLY_RECONCILE")
        self.machine.reconcile_pause(fixture_observation(paused=True))
        self.assertEqual(self.machine.state, "QUIESCED")

    def test_fsync_failure_returns_no_intent_and_poisoned_writer_cannot_continue(self):
        with patch("state_machine.os.fsync", side_effect=OSError("injected durability failure")):
            with self.assertRaises(OSError):
                self.machine.begin_pause(fixture_observation())
        self.assertTrue(self.journal.poisoned)
        with self.assertRaisesRegex(Rejected, "DURABILITY_UNKNOWN"):
            self.machine.begin_pause(fixture_observation())
        self.reopen()
        self.assertEqual(self.machine.state, "PAUSE_PENDING")

    def test_disabled_api_state_does_not_prove_photo_delete_worker_stopped(self):
        self.machine.begin_pause(fixture_observation())
        for field, bad in (("membership_complete", False), ("live_process_count", 1), ("in_flight_mutations", 1)):
            with self.subTest(field=field):
                obs = fixture_observation(paused=True)
                obs["supervisors"][0][field] = bad
                with self.assertRaisesRegex(Rejected, "COMPLETE_PROCESS_AND_WORK_DRAIN"):
                    self.machine.reconcile_pause(obs)
                self.assertEqual(self.machine.state, "PAUSE_PENDING")

    def test_empty_process_list_from_incomplete_namespace_fails(self):
        self.machine.begin_pause(fixture_observation())
        obs = fixture_observation(paused=True)
        obs["supervisors"][0]["membership_complete"] = False
        self.assertEqual(obs["supervisors"][0]["live_process_count"], 0)
        with self.assertRaises(Rejected):
            self.machine.reconcile_pause(obs)

    def test_command_drift_blocks_pause_and_resume_without_mutation_intent(self):
        obs = fixture_observation()
        obs["supervisors"][0]["command"] = "another application"
        with self.assertRaisesRegex(Rejected, "IDENTITY_DRIFT"):
            self.machine.begin_pause(obs)
        self.assertEqual(self.machine.state, "NEW")
        self.apply()
        self.machine.reconcile_installation(fixture_observation(paused=True, installed=True))
        obs = fixture_observation(paused=True, installed=True)
        obs["supervisors"][0]["command"] = "another application"
        with self.assertRaisesRegex(Rejected, "IDENTITY_DRIFT"):
            self.machine.begin_resume(obs)

    def test_unaccounted_monitor_or_missing_writer_fails(self):
        self.machine.begin_pause(fixture_observation())
        obs = fixture_observation(paused=True)
        obs["unaccounted_writers"] = ["test-unknown-spec-worker"]
        with self.assertRaisesRegex(Rejected, "UNACCOUNTED_WRITER"):
            self.machine.reconcile_pause(obs)
        obs = fixture_observation(paused=True)
        obs["writers"].pop()
        with self.assertRaisesRegex(Rejected, "WRITER_OBSERVATION_SET"):
            self.machine.reconcile_pause(obs)

    def test_lost_lock_and_different_operation_cannot_grant_install_boundary(self):
        self.pause()
        obs = fixture_observation(paused=True)
        obs["writers"][1]["lease_operation_id"] = "another-operation"
        with self.assertRaisesRegex(Rejected, "LOCK_NOT_HELD"):
            self.machine.installation_boundary(obs)

    def test_old_observation_is_not_refreshed_by_new_journal_timestamp(self):
        self.pause()
        self.clock = 1031
        with self.assertRaisesRegex(Rejected, "FRESH_ACTUAL_OBSERVATION"):
            self.machine.installation_boundary(fixture_observation(paused=True))
        self.assertEqual(self.machine.state, "QUIESCED")

    def test_existing_install_gates_remain_required(self):
        self.pause()
        obs = fixture_observation(paused=True)
        obs["canonical_install_admission_pass"] = False
        with self.assertRaisesRegex(Rejected, "CANONICAL_GATES"):
            self.machine.installation_boundary(obs)

    def test_install_reply_lost_has_no_timer_resume_and_needs_complete_coherence(self):
        self.apply()
        self.assertEqual(self.machine.outcome_unknown()[0]["kind"], "READ_ONLY_RECONCILE")
        self.reopen()
        self.clock += 3600
        with self.assertRaisesRegex(Rejected, "RECONCILIATION"):
            self.machine.begin_resume(fixture_observation(paused=True))
        obs = fixture_observation(paused=True, installed=True)
        obs["observed_at"] = self.clock
        obs["coherence"]["version"] = "MIXED"
        with self.assertRaisesRegex(Rejected, "UNKNOWN_OR_MIXED"):
            self.machine.reconcile_installation(obs)
        obs["coherence"]["version"] = "AFTER"
        self.machine.reconcile_installation(obs)
        self.assertEqual(self.machine.state, "COHERENT_AFTER")

    def test_old_backup_db_restore_or_lost_new_operator_change_blocks_resume(self):
        self.apply()
        for key, bad in (("backup_database_restored", True), ("operator_changes_preserved", False),
                         ("no_in_flight_installation", False), ("protected_nonprice_content_preserved", False)):
            with self.subTest(key=key):
                obs = fixture_observation(paused=True)
                obs["coherence"][key] = bad
                with self.assertRaises(Rejected):
                    self.machine.reconcile_installation(obs)
                self.assertEqual(self.machine.state, "APPLY_PENDING")

    def test_known_no_install_effect_can_restore_original_service(self):
        self.apply()
        obs = fixture_observation(paused=True, version="BEFORE")
        self.machine.reconcile_installation(obs)
        intent = self.machine.begin_resume(obs)[0]
        self.assertEqual(intent["kind"], "PATCH_ENABLED_TRUE")
        self.machine.reconcile_resume(fixture_observation(version="BEFORE"))
        self.assertEqual(self.machine.state, "RESTORED_PENDING_LIVE_ACCEPTANCE")

    def test_success_keeps_installation_distinct_from_live_acceptance(self):
        self.apply()
        self.machine.reconcile_installation(fixture_observation(paused=True, installed=True))
        self.machine.begin_resume(fixture_observation(paused=True, installed=True))
        self.machine.outcome_unknown()
        self.reopen()
        self.machine.reconcile_resume(fixture_observation())
        self.assertEqual(self.machine.state, "RESTORED_PENDING_LIVE_ACCEPTANCE")
        self.assertFalse(any("DELETE" in i["kind"] or "HALT" in i["kind"] for r in self.journal.records for i in r["intents"]))
        with self.assertRaises(Rejected):
            self.machine.begin_pause(fixture_observation())

    def test_running_with_unproven_loaded_code_is_not_restored(self):
        self.apply()
        self.machine.reconcile_installation(fixture_observation(paused=True, installed=True))
        self.machine.begin_resume(fixture_observation(paused=True, installed=True))
        obs = fixture_observation()
        obs["loaded_sources_sha256"] = "0" * 64
        with self.assertRaisesRegex(Rejected, "LOADED_CODE"):
            self.machine.reconcile_resume(obs)

    def test_competing_journal_writer_fails(self):
        with self.assertRaises(BlockingIOError):
            Journal(self.path, self.plan)

    def test_truncated_or_modified_journal_refuses_replay(self):
        self.machine.begin_pause(fixture_observation())
        self.journal.close()
        original = self.path.read_bytes()
        self.path.write_bytes(original[:-1])
        with self.assertRaisesRegex(Rejected, "TRUNCATED"):
            Journal(self.path, self.plan)
        self.path.write_bytes(original.replace(b"PAUSE_PENDING", b"COHERENT_AFTER"))
        with self.assertRaisesRegex(Rejected, "INTEGRITY"):
            Journal(self.path, self.plan)

    def test_journal_cannot_be_rebound_to_another_candidate(self):
        self.machine.begin_pause(fixture_observation())
        self.journal.close()
        other = copy.deepcopy(self.plan)
        other["candidate_sources_sha256"] = "0" * 64
        with self.assertRaisesRegex(Rejected, "PLAN_DRIFT"):
            Journal(self.path, other)

    def test_caller_plan_and_returned_intent_mutation_cannot_rebind_journal(self):
        self.plan["supervisors"][0]["command"] = "caller changed command"
        exposed = self.machine.plan
        exposed["writers"].clear()
        intents = self.machine.begin_pause(fixture_observation())
        self.assertEqual(intents[0]["expected_command"], "python3.10 /home/Carix/start_safe.py")
        self.assertEqual(len(self.machine.plan["writers"]), 3)
        intents[0]["supervisor_id"] = 999
        self.assertEqual(self.journal.records[-1]["intents"][0]["supervisor_id"], 266084)

    def test_internal_plan_bytes_drift_is_rejected_before_transition(self):
        other = self.machine.plan
        other["writers"].clear()
        from state_machine import encoded
        self.machine._plan_raw = encoded(other)
        with self.assertRaisesRegex(Rejected, "PLAN_MISMATCH"):
            self.machine.begin_pause(fixture_observation())
        self.assertEqual(self.machine.state, "NEW")

    def test_writer_pins_are_exact_for_each_installation_phase(self):
        self.machine.begin_pause(fixture_observation())
        with self.assertRaisesRegex(Rejected, "WRITER_SOURCE_DRIFT"):
            self.machine.reconcile_pause(fixture_observation(paused=True, installed=True))
        self.machine.reconcile_pause(fixture_observation(paused=True))
        self.machine.installation_boundary(fixture_observation(paused=True))
        with self.assertRaisesRegex(Rejected, "WRITER_SOURCE_DRIFT"):
            self.machine.reconcile_installation(fixture_observation(paused=True))
        self.machine.reconcile_installation(fixture_observation(paused=True, installed=True))
        with self.assertRaisesRegex(Rejected, "WRITER_SOURCE_DRIFT"):
            self.machine.begin_resume(fixture_observation(paused=True))
        self.machine.begin_resume(fixture_observation(paused=True, installed=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
