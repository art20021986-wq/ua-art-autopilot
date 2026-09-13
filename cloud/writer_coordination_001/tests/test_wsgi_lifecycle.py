"""Replay observed log bytes and reject specific unsafe interpretations.

Historical log transitions below are parser test inputs, not evidence of a
maintenance operation executed by this task. No source log is committed.
"""
import hashlib
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsgi_lifecycle as lifecycle

RAW_SHA256 = 'c9e694abf84b6ee242a0b038a2c69fb94b0cccbbecbb148af4d6e8f00eb0d71f'


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = os.environ.get('UAART_WSGI_CAPTURE')
        if not location:
            raise RuntimeError('EXACT_PRIVATE_WSGI_CAPTURE_REQUIRED')
        cls.raw = Path(location).read_bytes()
        if hashlib.sha256(cls.raw).hexdigest() != RAW_SHA256:
            raise RuntimeError('PRIVATE_WSGI_CAPTURE_SHA_MISMATCH')
        cls.before = cls.raw[:cls.raw.index(b'2026-09-07 12:08:28 ')]
        cls.stopped = cls.raw[:cls.raw.index(b'2026-09-07 12:08:33 ')]
        cls.reloaded = cls.raw[:cls.raw.index(b'2026-09-08 02:00:25 ')]

    def compare(self, before, after, operation='DISABLE', slots=(1, 2, 3)):
        return lifecycle.compare_captures(before, after, expected_worker_slots=slots, operation=operation)

    def test_current_workers_not_confused_with_prior_burials(self):
        value = lifecycle.inspect_log(self.raw)
        self.assertEqual(value['ignored_historical_prefix_bytes'], 424)
        self.assertEqual(value['current_master']['offset'], 5926)
        self.assertEqual([(w['slot'], w['pid']) for w in value['alive_workers']], [(1,12), (2,13), (3,18)])
        self.assertEqual(value['current_generation_scope_blockers'], ['UNSCOPED_CHILD_PROCESSES'])
        self.assertFalse(value['external_writer_verified'])

    def test_observed_historical_shutdown_is_data_only(self):
        value = self.compare(self.before, self.stopped)
        self.assertEqual(value['status'], 'PREEXISTING_WORKERS_TERMINATED_IN_ORDERED_LOG')
        self.assertEqual(len(value['baseline_workers']), 3)
        self.assertEqual(value['current_workers'], [])
        self.assertFalse(value['installation_authorized'])
        self.assertFalse(value['transport_authenticated'])

    def test_pid_reuse_creates_distinct_generation(self):
        value = self.compare(self.before, self.reloaded, 'RELOAD')
        old, new = value['baseline_workers'][0], value['current_workers'][0]
        self.assertEqual(old['pid'], new['pid'])
        self.assertNotEqual(old['master_offset'], new['master_offset'])
        self.assertNotEqual(old['spawn_offset'], new['spawn_offset'])
        self.assertFalse(value['loaded_runtime_verified'])

    def test_restart_is_not_disable(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'DISABLE_HAS_LIVE_WORKERS'):
            self.compare(self.before, self.reloaded)

    def test_missing_burial_cannot_be_forgiven_by_goodbye(self):
        missing = self.stopped.replace(b'2026-09-07 12:08:29 worker 2 buried after 1 seconds\n', b'')
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'MASTER_CLOSE_WITH_UNTERMINATED_WORKERS'):
            self.compare(self.before, missing)

    def test_master_overlap_is_rejected(self):
        overlap = self.before + self.reloaded[len(self.stopped):]
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'STARTUP_WITH_UNTERMINATED_WORKERS'):
            lifecycle.inspect_log(overlap)

    def test_no_new_events_is_not_drain(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'LOG_NOT_STRICT_APPEND_ONLY'):
            self.compare(self.raw, self.raw)

    def test_rotation_and_rewrite_are_rejected(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'LOG_NOT_STRICT_APPEND_ONLY'):
            self.compare(self.before, self.stopped.replace(b'11:44:31', b'11:44:32'))

    def test_partial_last_line_is_rejected(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'LOG_INCOMPLETE_LINE_OR_NUL'):
            lifecycle.inspect_log(self.raw[:-1])

    def test_duplicate_live_worker_slot_is_rejected(self):
        duplicate = self.before + b'2026-09-07 12:08:28 spawned uWSGI worker 1 (pid: 99, cores: 1)\n'
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'DUPLICATE_LIVE_WORKER_SLOT'):
            lifecycle.inspect_log(duplicate)

    def test_observed_nonworker_children_cannot_be_ignored(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'UNSCOPED_CHILD_PROCESSES'):
            self.compare(self.before, self.raw, 'RELOAD')

    def test_current_unscoped_children_block_even_with_added_burials(self):
        tail = b''.join(b'2026-09-09 11:44:00 worker %d buried after 1 seconds\n' % slot for slot in (1,2,3))
        tail += b'2026-09-09 11:44:00 goodbye to uWSGI.\n'
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'UNSCOPED_CHILD_PROCESSES'):
            self.compare(self.raw, self.raw + tail)

    def test_worker_count_must_cover_logged_core_capacity(self):
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'BASELINE_WORKER_INVENTORY_MISMATCH'):
            self.compare(self.before, self.stopped, slots=(1,2))

    def test_unknown_child_and_worker_formats_fail_closed(self):
        for row in (b'subprocess 777 exited on signal 9', b'Respawned uWSGI worker 1 (new pid: 99)',
                    b'spawned worker 4 (pid: 99, cores: 1)', b'SPAWNED WORKER 4 (pid: 99, cores: 1)'):
            with self.subTest(row=row):
                with self.assertRaisesRegex(lifecycle.LifecycleError, 'UNSUPPORTED_LIFECYCLE_LINE'):
                    lifecycle.inspect_log(self.before + b'2026-09-07 12:08:28 ' + row + b'\n')

    def test_activity_after_incomplete_history_shutdown_invalidates_boundary(self):
        marker = b'2026-09-07 11:44:20 goodbye to uWSGI.\n'
        child = b'2026-09-07 11:44:20 Respawned uWSGI worker 4 (new pid: 99)\n'
        contaminated_before = self.before.replace(marker, marker + child, 1)
        contaminated_after = self.stopped.replace(marker, marker + child, 1)
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'INCOMPLETE_HISTORY_WITHOUT_SHUTDOWN_BOUNDARY'):
            self.compare(contaminated_before, contaminated_after)

    def test_new_master_cannot_reuse_previous_startup_configuration(self):
        missing_startup = self.stopped + (
            b'2026-09-07 12:08:33 spawned uWSGI master process (pid: 1)\n'
            b'2026-09-07 12:08:33 spawned uWSGI worker 1 (pid: 12, cores: 1)\n')
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'NEW_MASTER_WITHOUT_NEW_STARTUP'):
            self.compare(self.before, missing_startup, 'RELOAD')

    def test_in_progress_new_startup_is_not_disable(self):
        after = self.raw[:5926]
        self.assertIsNotNone(lifecycle.inspect_log(after)['pending_startup'])
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'INCOMPLETE_NEW_STARTUP'):
            self.compare(self.before, after)


if __name__ == '__main__':
    unittest.main()
