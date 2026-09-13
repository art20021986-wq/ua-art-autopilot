import dataclasses
from datetime import datetime, timedelta, timezone, time
import unittest

import owner_policy as p


class OwnerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.identity = p.Identity("TASK088-STAGE3", "a" * 64, "run-123")
        self.now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        self.evidence = p.RecoveryEvidence(
            identity=self.identity, failure_id="failure-1", checked_at=self.now,
            evidence_sha256="b" * 64, checkpoint_sha256="c" * 64,
            root_cause_fixed=True, checks_passed=True, checkpoint_verified=True,
            backup_verified=True, rollback_verified=True, gate_b_verified=True,
            owner_authorization_verified=True, gate_b_receipt_sha256="d" * 64,
        )

    def resume(self, **overrides):
        values = dict(identity=self.identity, failure_id="failure-1", task_state="STOPPED",
                      production=True, planned_actions=("backup", "install", "verify"),
                      completed_actions=("backup",), proposed_action="install",
                      next_action_not_started=True, evidence=self.evidence, now=self.now)
        values.update(overrides)
        return p.resume_decision(**values)

    def independent(self, **overrides):
        values = dict(candidate=p.Identity("DOC-1", "e" * 64, "run-456"),
                      stopped=self.identity, candidate_resources=("DOCS/manual",),
                      stopped_resources=("CRM_DB",), safety_proven=True,
                      impact_isolated=True, checked_at=self.now,
                      evidence_sha256="f" * 64, required_dependencies=(),
                      receipts=(), now=self.now)
        values.update(overrides)
        return p.independent_task_decision(**values)

    def test_all_failure_classes_stop_without_retry(self):
        for kind in ("TRANSIENT", "HTTP503", "TIMEOUT", "LOGICAL", "SAFETY", "UNKNOWN"):
            with self.subTest(kind=kind):
                self.assertEqual(p.failure_decision(self.identity, "f-1", kind).action, "STOP")

    def test_empty_or_malformed_identity_rejected(self):
        for args in (("", "a" * 64, "run"), ("task", "a", "run"),
                     ("task", "a" * 64, " "), (None, "a" * 64, "run")):
            with self.subTest(args=args), self.assertRaises(p.PolicyInputError):
                p.Identity(*args)

    def test_same_attempt_verified_recovery_is_eligible_only(self):
        self.assertEqual(self.resume().action, "RESUME_ELIGIBLE")

    def test_new_attempt_or_changed_request_or_task_is_rejected(self):
        for identity in (dataclasses.replace(self.identity, attempt_id="run-124"),
                         dataclasses.replace(self.identity, request_sha256="e" * 64),
                         dataclasses.replace(self.identity, task_id="TASK088-STAGE4")):
            with self.subTest(identity=identity):
                self.assertEqual(self.resume(identity=identity).action, "STOP")

    def test_wrong_failure_rejected(self):
        self.assertEqual(self.resume(failure_id="failure-2").action, "STOP")

    def test_stale_or_future_evidence_rejected(self):
        for offset in (-301, 1):
            evidence = dataclasses.replace(self.evidence, checked_at=self.now + timedelta(seconds=offset))
            with self.subTest(offset=offset):
                self.assertEqual(self.resume(evidence=evidence).action, "STOP")

    def test_freshness_boundary(self):
        evidence = dataclasses.replace(self.evidence, checked_at=self.now - timedelta(minutes=5))
        self.assertEqual(self.resume(evidence=evidence).action, "RESUME_ELIGIBLE")

    def test_missing_root_cause_checks_or_checkpoint_stops(self):
        for field in ("root_cause_fixed", "checks_passed", "checkpoint_verified"):
            with self.subTest(field=field):
                self.assertEqual(self.resume(evidence=dataclasses.replace(self.evidence, **{field: False})).action, "STOP")

    def test_production_requires_every_existing_safety_gate(self):
        for field in ("backup_verified", "rollback_verified", "gate_b_verified", "owner_authorization_verified"):
            with self.subTest(field=field):
                self.assertEqual(self.resume(evidence=dataclasses.replace(self.evidence, **{field: False})).action, "STOP")
        self.assertEqual(self.resume(evidence=dataclasses.replace(self.evidence, gate_b_receipt_sha256="")).action, "STOP")

    def test_nonproduction_does_not_invent_production_gate(self):
        evidence = dataclasses.replace(self.evidence, backup_verified=False, rollback_verified=False,
                                       gate_b_verified=False, owner_authorization_verified=False,
                                       gate_b_receipt_sha256="")
        self.assertEqual(self.resume(production=False, evidence=evidence).action, "RESUME_ELIGIBLE")

    def test_all_boolean_evidence_fields_require_exact_bool(self):
        for field in ("root_cause_fixed", "checks_passed", "checkpoint_verified", "backup_verified",
                      "rollback_verified", "gate_b_verified", "owner_authorization_verified"):
            for invalid in (1, 0, "true", None):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(p.PolicyInputError):
                    dataclasses.replace(self.evidence, **{field: invalid})

    def test_recovery_boolean_arguments_require_exact_bool(self):
        for field in ("production", "next_action_not_started"):
            with self.subTest(field=field), self.assertRaises(p.PolicyInputError):
                self.resume(**{field: 1})

    def test_ambiguous_write_cannot_replay(self):
        self.assertEqual(self.resume(next_action_not_started=False).action, "STOP")

    def test_completed_action_cannot_replay(self):
        self.assertEqual(self.resume(proposed_action="backup").action, "STOP")

    def test_checkpoint_cannot_skip_action_or_invent_completed_action(self):
        for actions in (("install",), ("unknown",), ("backup", "verify")):
            with self.subTest(actions=actions):
                self.assertEqual(self.resume(completed_actions=actions).action, "STOP")
        self.assertEqual(self.resume(proposed_action="verify").action, "STOP")

    def test_terminal_task_never_resumes(self):
        for state in ("FINISHED", "FAILED", "ROLLED_BACK", "RUNNING", "UNKNOWN"):
            with self.subTest(state=state):
                self.assertEqual(self.resume(task_state=state).action, "STOP")

    def test_all_completed_means_no_resume(self):
        self.assertEqual(self.resume(completed_actions=("backup", "install", "verify")).action, "STOP")

    def test_empty_or_duplicate_plan_rejected(self):
        for plan in ((), ("backup", "backup"), ["backup"], ("",)):
            with self.subTest(plan=plan), self.assertRaises(p.PolicyInputError):
                self.resume(planned_actions=plan)

    def test_unverified_or_empty_receipt_hash_rejected(self):
        for field in ("evidence_sha256", "checkpoint_sha256"):
            with self.subTest(field=field), self.assertRaises(p.PolicyInputError):
                dataclasses.replace(self.evidence, **{field: ""})

    def test_naive_time_rejected(self):
        with self.assertRaises(p.PolicyInputError):
            self.resume(now=datetime(2026, 9, 13))

    def test_safe_independent_work_eligible(self):
        self.assertEqual(self.independent().action, "CONTINUE_ELIGIBLE")

    def test_unproven_isolation_safety_or_stale_evidence_waits(self):
        for changes in (dict(safety_proven=False), dict(impact_isolated=False),
                        dict(checked_at=self.now - timedelta(minutes=6)),
                        dict(checked_at=self.now + timedelta(seconds=1))):
            with self.subTest(changes=changes):
                self.assertEqual(self.independent(**changes).action, "WAIT")

    def test_empty_resources_rejected(self):
        with self.assertRaises(p.PolicyInputError):
            self.independent(candidate_resources=())

    def test_ambiguous_or_unknown_resources_rejected(self):
        for resource in ("DOCS/../CRM_DB", "DOCS//manual", "DOCS/./manual", "DOCS/", "crm_db", "UNKNOWN_SCOPE"):
            with self.subTest(resource=resource), self.assertRaises(p.PolicyInputError):
                self.independent(candidate_resources=(resource,))

    def test_resource_equality_hierarchy_global_and_catalog_conflicts(self):
        for a, b in (("CRM_DB", "CRM_DB"), ("DOCS", "DOCS/manual"),
                     ("DOCS/manual", "GLOBAL_PRODUCTION"), ("CONTROL_PLANE", "DOCS/manual"),
                     ("CARD:UA-0010", "CATALOG_ALL_CARDS"), ("HOMEPAGE", "CATALOG_RENDERER"),
                     ("CARD:UA-0010", "CRM_DB"), ("CRM_DB/table1", "CRM_DB/table2"),
                     ("DOCS/manual", "CONTROL_PLANE/policy")):
            with self.subTest(a=a, b=b):
                self.assertEqual(self.independent(candidate_resources=(a,), stopped_resources=(b,)).action, "WAIT")

    def test_same_task_is_not_independent(self):
        self.assertEqual(self.independent(candidate=dataclasses.replace(self.identity, attempt_id="new-run")).action, "WAIT")

    def test_dependency_exact_success_receipt_required(self):
        dependency = p.Identity("TASK088-STAGE1", "f" * 64, "run-1")
        receipt = p.DependencyReceipt(dependency, "FINISHED", "a" * 64, True)
        self.assertEqual(self.independent(required_dependencies=(dependency,), receipts=(receipt,)).action, "CONTINUE_ELIGIBLE")
        for receipts in ((), (dataclasses.replace(receipt, status="FAILED"),),
                         (dataclasses.replace(receipt, independently_verified=False),),
                         (dataclasses.replace(receipt, identity=dataclasses.replace(dependency, request_sha256="b" * 64)),)):
            with self.subTest(receipts=receipts):
                self.assertEqual(self.independent(required_dependencies=(dependency,), receipts=receipts).action, "WAIT")

    def test_stopped_dependency_never_eligible_even_with_receipt(self):
        receipt = p.DependencyReceipt(self.identity, "FINISHED", "a" * 64, True)
        self.assertEqual(self.independent(required_dependencies=(self.identity,), receipts=(receipt,)).action, "WAIT")

    def test_duplicate_receipts_fail_closed(self):
        receipt = p.DependencyReceipt(self.identity, "FINISHED", "a" * 64, True)
        with self.assertRaises(p.PolicyInputError):
            self.independent(receipts=(receipt, receipt))

    def test_independence_exact_booleans_required(self):
        for field in ("safety_proven", "impact_isolated"):
            with self.subTest(field=field), self.assertRaises(p.PolicyInputError):
                self.independent(**{field: "true"})
        with self.assertRaises(p.PolicyInputError):
            p.DependencyReceipt(self.identity, "FINISHED", "a" * 64, 1)

    def test_telegram_only_failure_and_daily(self):
        for event in ("FAILURE", "DAILY_REPORT"):
            self.assertTrue(p.telegram_event_selected(event))
        for event in ("PROGRESS", "STARTED", "COMPLETED", "RESUMED"):
            self.assertFalse(p.telegram_event_selected(event))
        for unknown in (None, "", "CUSTOM"):
            with self.assertRaises(p.PolicyInputError):
                p.telegram_event_selected(unknown)

    def test_owner_reporting_requirements(self):
        self.assertEqual(p.REPORT_LOCAL_TIME, time(10, 0))
        self.assertEqual(p.REPORT_TIMEZONE, "Asia/Ho_Chi_Minh")
        self.assertEqual(p.REPORT_FORMAT, "SHORT_WITH_DETAIL_LINK")
        self.assertEqual(p.TELEGRAM_DESTINATION, "VERIFIED_OWNER_PRIVATE_CRM_CHAT")
        self.assertEqual(p.OPERATING_WINDOW, "24X7")


if __name__ == "__main__":
    unittest.main()
