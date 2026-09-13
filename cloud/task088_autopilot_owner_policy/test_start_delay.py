from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

import owner_policy as p


class StartDelayTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
        self.identity = p.Identity("ORDINARY-TASK-1", "a" * 64, "attempt-1")

    def decision(self, **changes):
        values = dict(identity=self.identity, snapshot_identity=self.identity,
                      readiness_episode="ready-1", task_kind="ORDINARY", task_state="READY",
                      approval_verified=True, readiness_verified=True,
                      ready_since=self.now - timedelta(minutes=5), checked_at=self.now,
                      now=self.now, delivered_event_keys=())
        values.update(changes)
        return p.start_delay_decision(**values)

    def test_threshold_before_exactly_at_and_after_five_minutes(self):
        for seconds, expected in ((299.999, "WAIT"), (300, "NOTIFY_ELIGIBLE"),
                                  (301, "NOTIFY_ELIGIBLE"), (3600, "NOTIFY_ELIGIBLE")):
            with self.subTest(seconds=seconds):
                self.assertEqual(self.decision(ready_since=self.now - timedelta(seconds=seconds)).action, expected)

    def test_price_sync_does_not_use_five_minute_rule(self):
        self.assertEqual(self.decision(task_kind="PRICE_SYNC").reason,
                         "PRICE_SYNC_HAS_SEPARATE_60_SECOND_DEADLINE")
        rules = json.loads(Path(__file__).with_name("owner_decisions.json").read_text())
        self.assertEqual(rules["pricing"]["max_sync_seconds"], 60)
        self.assertEqual(rules["autopilot"]["ordinary_ready_task_start_delay_seconds"], 300)

    def test_blocked_unapproved_running_and_terminal_tasks_do_not_alert(self):
        for state in ("QUEUED", "WAITING_DEPENDENCIES", "PENDING_APPROVAL", "RUNNING",
                      "FINISHED", "FAILED", "ROLLED_BACK", "STOPPED"):
            with self.subTest(state=state):
                self.assertEqual(self.decision(task_state=state).action, "WAIT")
        self.assertEqual(self.decision(approval_verified=False).action, "WAIT")
        self.assertEqual(self.decision(readiness_verified=False).action, "WAIT")

    def test_exact_task_request_and_attempt_are_bound(self):
        for change in (dict(task_id="OTHER"), dict(request_sha256="b" * 64), dict(attempt_id="attempt-2")):
            with self.subTest(change=change):
                self.assertEqual(self.decision(snapshot_identity=replace(self.identity, **change)).action, "WAIT")

    def test_delivered_episode_not_repeated_and_next_episode_is_distinct(self):
        first = self.decision()
        self.assertEqual(first.event_type, "START_DELAY")
        self.assertEqual(self.decision(delivered_event_keys=(first.event_key,)).action, "WAIT")
        next_episode = self.decision(readiness_episode="ready-2", delivered_event_keys=(first.event_key,))
        self.assertEqual(next_episode.action, "NOTIFY_ELIGIBLE")
        self.assertNotEqual(first.event_key, next_episode.event_key)
        next_id = replace(self.identity, attempt_id="attempt-2")
        self.assertNotEqual(first.event_key, self.decision(identity=next_id, snapshot_identity=next_id).event_key)

    def test_snapshot_must_be_fresh_but_readiness_can_be_old(self):
        self.assertEqual(self.decision(checked_at=self.now - timedelta(seconds=31)).action, "WAIT")
        self.assertEqual(self.decision(checked_at=self.now - timedelta(seconds=30)).action, "NOTIFY_ELIGIBLE")

    def test_invalid_or_future_timestamps_rejected(self):
        for changes in (dict(ready_since=self.now + timedelta(seconds=1)),
                        dict(checked_at=self.now + timedelta(seconds=1)),
                        dict(now=self.now.replace(tzinfo=None)), dict(ready_since=None)):
            with self.subTest(changes=changes), self.assertRaises(p.PolicyInputError):
                self.decision(**changes)

    def test_equivalent_vietnam_and_utc_times_produce_same_alert(self):
        vietnam = timezone(timedelta(hours=7))
        self.assertEqual(self.decision(), self.decision(now=self.now.astimezone(vietnam)))

    def test_malformed_boolean_identity_event_and_kind_rejected(self):
        for changes in (dict(approval_verified=1), dict(readiness_verified="true"),
                        dict(readiness_episode=""), dict(delivered_event_keys=("bad",)),
                        dict(identity=None), dict(task_kind="UNKNOWN")):
            with self.subTest(changes=changes), self.assertRaises(p.PolicyInputError):
                self.decision(**changes)

    def test_delay_is_notified_without_adding_progress_messages_or_failure_delay(self):
        self.assertTrue(p.telegram_event_selected(self.decision().event_type))
        for event in ("STARTED", "PROGRESS", "COMPLETED", "RESUMED"):
            self.assertFalse(p.telegram_event_selected(event))
        self.assertEqual(p.failure_decision(self.identity, "f-1", "TRANSIENT").action, "STOP")


if __name__ == "__main__":
    unittest.main()
