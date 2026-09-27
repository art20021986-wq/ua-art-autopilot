"""Execute both workflow copy blocks in temporary directories, without a token."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import prepare_nonce_fix as fix


class DurableCopyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.pinned = self.root / 'pinned'
        self.source.mkdir()
        self.pinned.mkdir()
        self.nonce = 'fixture-install-20260927T050000Z'
        self.paths = {
            'claim': 'state/claims/task.json',
            'transaction': 'state/transactions/task.json',
            'request': 'tasks/requests/task.json',
            'ledger': 'state/autostart_consumed/task.json',
            'backup': 'state/receipts/backup.json',
            'nonce': 'state/autostart_nonces/' + self.nonce + '.json',
        }
        self.source_commit = '1' * 40
        self.write('nonce', {'nonce': self.nonce, 'status': 'RESERVED'})
        self.ledger = {
            'nonce': self.nonce,
            'nonce_reservation_path': self.paths['nonce'],
            'nonce_reservation_sha256': hashlib.sha256(self.path('nonce').read_bytes()).hexdigest(),
        }
        self.write('ledger', self.ledger)
        self.write('claim', {'autostart_ledger_path': self.paths['ledger'],
                             'autostart_source_commit': self.source_commit})
        self.write('transaction', {'request_path': self.paths['request'],
                                   'backup_receipt_path': self.paths['backup'], 'status': 'ROLLING_BACK'})
        self.write('request', {'production_required': True})
        self.write('backup', {'status': 'PASS'})
        self.environment = {
            **os.environ, 'PINNED_ROOT': str(self.pinned), 'SOURCE_COMMIT': self.source_commit,
            'CLAIM_PATH': self.paths['claim'], 'TRANSACTION_PATH': self.paths['transaction'],
            'EXPECTED_TRANSACTION_PATH': self.paths['transaction'],
            'REQUEST_PATH': self.paths['request'], 'EXPECTED_REQUEST_PATH': self.paths['request'],
        }

    def path(self, key):
        return self.source / self.paths[key]

    def write(self, key, value):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + '\n')

    def execute(self, relative, *, old=False):
        data = (fix.ROOT / relative).read_bytes()
        if not old:
            data = fix.candidate(relative, data)
        script = fix.copied_state_script(data.decode())
        return subprocess.run([sys.executable, '-I', '-c', script], cwd=self.source,
                              env=self.environment, text=True, capture_output=True, timeout=10)

    def both_fail(self, message):
        for relative in fix.SOURCES:
            with self.subTest(workflow=relative):
                result = self.execute(relative)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(any(p.is_file() for p in self.pinned.rglob('*')))

    def test_original_reproduces_missing_nonce_in_both_workflows(self):
        for relative in fix.SOURCES:
            with self.subTest(workflow=relative):
                result = self.execute(relative, old=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.pinned / self.paths['nonce']).exists())

    def test_candidate_copies_exact_six_durable_records(self):
        for relative in fix.SOURCES:
            with self.subTest(workflow=relative):
                result = self.execute(relative)
                self.assertEqual(result.returncode, 0, result.stderr)
                files = {p.relative_to(self.pinned).as_posix() for p in self.pinned.rglob('*') if p.is_file()}
                self.assertEqual(files, set(self.paths.values()))
                for path in files:
                    self.assertEqual((self.pinned / path).read_bytes(), (self.source / path).read_bytes())

    def test_missing_nonce_fails_before_any_copy(self):
        self.path('nonce').unlink()
        self.both_fail('PINNED_NONCE_FILE')

    def test_changed_nonce_fails_before_any_copy(self):
        self.path('nonce').write_text('{}')
        self.both_fail('PINNED_NONCE_SHA_BINDING')

    def test_outside_nonce_scope_fails_before_any_copy(self):
        self.ledger['nonce_reservation_path'] = '../elsewhere.json'
        self.write('ledger', self.ledger)
        self.both_fail('PINNED_NONCE_PATH_BINDING')

    def test_other_valid_nonce_path_rejected(self):
        self.ledger['nonce_reservation_path'] = 'state/autostart_nonces/another-install-20260927.json'
        self.write('ledger', self.ledger)
        self.both_fail('PINNED_NONCE_PATH_BINDING')

    def test_nonce_source_symlink_rejected(self):
        original = self.path('nonce').read_bytes()
        other = self.root / 'outside.json'
        other.write_bytes(original)
        self.path('nonce').unlink()
        self.path('nonce').symlink_to(other)
        self.both_fail('PINNED_NONCE_FILE')

    def test_destination_symlink_rejected_before_copy(self):
        target = self.pinned / self.paths['nonce']
        target.parent.mkdir(parents=True)
        outside = self.root / 'outside.json'
        outside.write_text('untouched')
        target.symlink_to(outside)
        for relative in fix.SOURCES:
            result = self.execute(relative)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('PINNED_DESTINATION_SYMLINK', result.stderr)
            self.assertEqual(outside.read_text(), 'untouched')
            self.assertFalse((self.pinned / self.paths['claim']).exists())

    def test_source_commit_drift_rejected_before_copy(self):
        self.environment['SOURCE_COMMIT'] = '2' * 40
        self.both_fail('PINNED_SOURCE_COMMIT_BINDING')

    def test_unreviewed_workflow_rejected(self):
        for relative in fix.SOURCES:
            with self.assertRaisesRegex(ValueError, 'WORKFLOW_SOURCE_DRIFT'):
                fix.candidate(relative, (fix.ROOT / relative).read_bytes() + b'\n')


if __name__ == '__main__':
    unittest.main()
