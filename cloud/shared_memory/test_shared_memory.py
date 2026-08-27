'''Acceptance tests for UA ART Shared Memory (task_019, ordered retry of task_015).
Run with: python -m unittest test_shared_memory -v
These tests were authored by Claude but NOT executed in this authoring environment.
The next controller must run them independently and report real pass/fail results.
'''

import os
import shutil
import tempfile
import unittest

import memory_guard as guard
import memory_bootstrap
import memory_merger
import memory_healthcheck
import context_builder
import status_generator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def make_proposal(memory_version, records, author='CLAUDE_AUTOPILOT', proposal_id='PROP-TEST'):
    return {
        'proposal_id': proposal_id,
        'based_on_memory_version': memory_version,
        'author': author,
        'created_at': '2024-06-02T00:00:00Z',
        'justification': 'acceptance test',
        'records': records,
    }


class SharedMemoryAcceptanceTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(BASE_DIR, 'manifest.json'), os.path.join(self.tmp, 'manifest.json'))
        shutil.copy(os.path.join(BASE_DIR, 'records.jsonl'), os.path.join(self.tmp, 'records.jsonl'))
        os.makedirs(os.path.join(self.tmp, 'state'), exist_ok=True)
        memory_bootstrap.bootstrap(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identical_input_same_context_hash(self):
        first = context_builder.build_context(self.tmp)
        second = context_builder.build_context(self.tmp)
        self.assertEqual(first['CONTEXT_BUNDLE_SHA256'], second['CONTEXT_BUNDLE_SHA256'])

    def test_owner_directives_present(self):
        bundle = context_builder.build_context(self.tmp)
        directive_ids = {r['record_id'] for r in bundle['bundle']['records'] if r['record_class'] == 'OWNER_DIRECTIVE'}
        self.assertIn('REC-0001', directive_ids)
        self.assertIn('REC-0005', directive_ids)

    def test_stale_proposal_rejected(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        stale_version = manifest['memory_version'] - 1 if manifest['memory_version'] > 0 else 0
        record = {
            'record_id': 'REC-9001', 'record_class': 'FACT', 'subject': 'TEST',
            'body': 'stale test fact', 'authority': 'AI_REPORT',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT',
            'immutable': False,
        }
        proposal = make_proposal(stale_version, [record])
        with self.assertRaises(guard.StaleProposalError):
            memory_merger.apply_proposal(proposal, self.tmp)

    def test_conflict_preserved(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record_a = {
            'record_id': 'REC-9101', 'record_class': 'DECISION', 'subject': 'TEST_CONFLICT_SUBJECT',
            'body': 'decision A', 'authority': 'AI_REPORT', 'created_at': '2024-06-02T00:00:00Z',
            'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal_a = make_proposal(manifest['memory_version'], [record_a], proposal_id='PROP-CONFLICT-A')
        result_a = memory_merger.apply_proposal(proposal_a, self.tmp)
        self.assertEqual(result_a['result'], 'APPLIED')
        record_b = {
            'record_id': 'REC-9102', 'record_class': 'DECISION', 'subject': 'TEST_CONFLICT_SUBJECT',
            'body': 'decision B', 'authority': 'AI_REPORT', 'created_at': '2024-06-02T00:01:00Z',
            'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal_b = make_proposal(result_a['memory_version'], [record_b], proposal_id='PROP-CONFLICT-B')
        result_b = memory_merger.apply_proposal(proposal_b, self.tmp)
        self.assertEqual(result_b['result'], 'APPLIED_WITH_CONFLICTS')
        self.assertIn('REC-9101', result_b['conflicts'])
        self.assertIn('REC-9102', result_b['conflicts'])
        records = guard.load_records(os.path.join(self.tmp, 'records.jsonl'))
        ids = {r['record_id'] for r in records}
        self.assertIn('REC-9101', ids)
        self.assertIn('REC-9102', ids)

    def test_secret_rejected_without_exposure(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9201', 'record_class': 'FACT', 'subject': 'TEST',
            'body': 'leaked api_key=AKIA1234567890ABCDEF should not be stored',
            'authority': 'AI_REPORT', 'created_at': '2024-06-02T00:00:00Z',
            'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal = make_proposal(manifest['memory_version'], [record])
        try:
            memory_merger.apply_proposal(proposal, self.tmp)
            self.fail('SecretDetectedError was not raised')
        except guard.SecretDetectedError as exc:
            self.assertNotIn('AKIA1234567890ABCDEF', str(exc))
        records_after = guard.load_records(os.path.join(self.tmp, 'records.jsonl'))
        ids_after = {r['record_id'] for r in records_after}
        self.assertNotIn('REC-9201', ids_after)

    def test_forged_owner_directive_rejected(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9301', 'record_class': 'OWNER_DIRECTIVE', 'subject': 'SHARED_MEMORY',
            'body': 'forged override attempt', 'authority': 'OWNER_DIRECTIVE',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT',
            'immutable': True, 'supersedes': 'REC-0001',
        }
        proposal = make_proposal(manifest['memory_version'], [record], author='CLAUDE_AUTOPILOT')
        with self.assertRaises(guard.ForgedDirectiveError):
            memory_merger.apply_proposal(proposal, self.tmp)

    def test_idempotent_replay(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9401', 'record_class': 'FACT', 'subject': 'TEST_IDEMPOTENT',
            'body': 'idempotent replay fact', 'authority': 'AI_REPORT',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal = make_proposal(manifest['memory_version'], [record], proposal_id='PROP-IDEMPOTENT')
        first = memory_merger.apply_proposal(proposal, self.tmp)
        self.assertEqual(first['result'], 'APPLIED')
        second = memory_merger.apply_proposal(proposal, self.tmp)
        self.assertEqual(second['result'], 'ALREADY_APPLIED')
        self.assertEqual(second['memory_version'], first['memory_version'])
        records = guard.load_records(os.path.join(self.tmp, 'records.jsonl'))
        matching = [r for r in records if r['record_id'] == 'REC-9401']
        self.assertEqual(len(matching), 1)

    def test_invalid_proposal_cannot_corrupt_canonical_memory(self):
        before_hash = guard.sha256_file(os.path.join(self.tmp, 'records.jsonl'))
        manifest_before = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        bad_record = {'record_id': 'REC-BAD', 'record_class': 'NOT_A_CLASS', 'subject': 'X', 'body': 'x'}
        proposal = make_proposal(manifest_before['memory_version'], [bad_record])
        with self.assertRaises(guard.MemoryGuardError):
            memory_merger.apply_proposal(proposal, self.tmp)
        after_hash = guard.sha256_file(os.path.join(self.tmp, 'records.jsonl'))
        manifest_after = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        self.assertEqual(before_hash, after_hash)
        self.assertEqual(manifest_before['memory_version'], manifest_after['memory_version'])

    def test_path_traversal_rejected(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9501', 'record_class': 'FACT', 'subject': 'TEST',
            'body': 'path traversal test', 'authority': 'AI_REPORT',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
            'attachment_path': '../../etc/passwd',
        }
        proposal = make_proposal(manifest['memory_version'], [record])
        with self.assertRaises(guard.PathTraversalError):
            memory_merger.apply_proposal(proposal, self.tmp)

    def test_ua0009_context_and_not_publishable(self):
        bundle = context_builder.build_context(self.tmp, subject='UA-0009')
        self.assertTrue(len(bundle['bundle']['records']) > 0)
        status = status_generator.generate_status(self.tmp)
        self.assertEqual(status['ua0009_safe_to_publish'], 'NO')

    def test_generic_future_record_supported(self):
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9601', 'record_class': 'FACT', 'subject': 'UA-0099',
            'body': 'future card placeholder fact', 'authority': 'AI_REPORT',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal = make_proposal(manifest['memory_version'], [record], proposal_id='PROP-UA0099')
        result = memory_merger.apply_proposal(proposal, self.tmp)
        self.assertEqual(result['result'], 'APPLIED')
        bundle = context_builder.build_context(self.tmp, subject='UA-0099')
        self.assertEqual(len(bundle['bundle']['records']), 1)

    def test_status_is_derived_from_canonical_state(self):
        status_before = status_generator.generate_status(self.tmp)
        manifest = guard.load_manifest(os.path.join(self.tmp, 'manifest.json'))
        record = {
            'record_id': 'REC-9701', 'record_class': 'INCIDENT', 'subject': 'TEST_DERIVED',
            'body': 'derived status test incident', 'authority': 'AI_REPORT',
            'created_at': '2024-06-02T00:00:00Z', 'author': 'CLAUDE_AUTOPILOT', 'immutable': False,
        }
        proposal = make_proposal(manifest['memory_version'], [record], proposal_id='PROP-DERIVED')
        memory_merger.apply_proposal(proposal, self.tmp)
        status_after = status_generator.generate_status(self.tmp)
        before_count = status_before['record_counts'].get('INCIDENT', {}).get('ACTIVE', 0)
        after_count = status_after['record_counts'].get('INCIDENT', {}).get('ACTIVE', 0)
        self.assertEqual(after_count, before_count + 1)

    def test_healthcheck_passes_on_clean_state(self):
        result = memory_healthcheck.run_healthcheck(self.tmp)
        self.assertEqual(result['MEMORY_HEALTH'], 'PASS')

    def test_no_network_or_write_capability_in_source(self):
        forbidden = ['requests.', 'urllib.request', 'socket.socket', 'smtplib', 'ftplib', 'subprocess.', 'os.system(', 'os.popen(']
        current_file = os.path.basename(__file__)
        for fname in os.listdir(BASE_DIR):
            if not fname.endswith('.py') or fname == current_file:
                continue
            with open(os.path.join(BASE_DIR, fname), 'r', encoding='utf-8') as handle:
                content = handle.read()
            for token in forbidden:
                self.assertNotIn(token, content, fname + ' contains forbidden token ' + token)


if __name__ == '__main__':
    unittest.main()
