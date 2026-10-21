"""Offline private-bundle boundary tests; all authority and code are fixtures."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import release_bundle as bundle
from contract import Envelope, ContractError, PACKAGE_REL, APPROVAL_REL, canonical_json, sha
from transport import WORKER_FILES


BUILDER = b'''import argparse
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--sources',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
o=Path(a.output)
o.mkdir(mode=0o700)
(o/'manifest.json').write_bytes(b'{"fixture":true}\\n')
(o/'payload').mkdir()
(o/'payload/car.py').write_bytes(b'# synthetic fixture\\n')
(o/'install').mkdir()
for source in (Path(__file__).parent/'install').glob('*.py'):
    (o/'install'/source.name).write_bytes(source.read_bytes())
'''


class FakeTransport:
    def __init__(self, sources, backup):
        self.sources, self.backup = sources, backup
        self.calls = []

    def read_source(self, path, digest):
        self.calls.append(('source', path, digest))
        return self.sources[path]

    def read_backup_file(self, package_sha, transaction_id, filename, digest):
        self.calls.append(('backup', filename, digest, package_sha, transaction_id))
        return self.backup[filename]


class PrivateBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.code = {}
        def write(name, raw, *, executable=False):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            if executable:
                self.code[name] = sha(raw)
        write('automation/control_plane.py', b'# fixture authority\n')
        write('.github/workflows/uaart_critical.yml', b'# fixture workflow\n')
        write(PACKAGE_REL + '/controller.py', b'# fixture controller\n', executable=True)
        write(bundle.RECIPE_REL + '/build_release.py', BUILDER, executable=True)
        worker_hashes = {}
        for name in WORKER_FILES:
            raw = ('# fixture worker ' + name + '\n').encode()
            worker_hashes[name] = sha(raw)
            write(bundle.RECIPE_REL + '/install/' + name, raw, executable=True)
        data_name = bundle.RECIPE_REL + '/hash_only.py.txt'
        write(data_name, b'# inert hash-only test evidence\n')
        self.source_bytes = {remote: ('# baseline fixture for ' + local + '\n').encode()
                             for local, remote in bundle.SOURCE_PATHS.items()}
        source_hashes = {local: sha(self.source_bytes[remote]) for local, remote in bundle.SOURCE_PATHS.items()}
        self.package_sha = sha(b'{"fixture":true}\n')
        self.policy = dict(version=1, task_id=bundle.TASK_ID, parent_task_id=bundle.PARENT_TASK_ID,
            acceptance_scope='INSTALLATION_AND_RUNTIME_HTTP_VERIFY', package_sources=worker_hashes,
            package_manifest_path='package/manifest.json', package_manifest_sha256=self.package_sha,
            maximum_seconds=120, provider={}, http_checks={}, authority_policy={
                'control_plane_sha256': sha(b'# fixture authority\n'),
                'critical_workflow_sha256': sha(b'# fixture workflow\n'),
                'trusted_controller_sha256': sha(b'# fixture controller\n')})
        policy_sha = sha(bundle.encoded(self.policy))
        self.tx = 'tx-fixture-0000000000000001'
        self.request = {'http_checks': self.policy['http_checks'], 'critical': {'owner_approval_sha256': 'a' * 64}, 'deployment': {
            'version': 1, 'source_sha256': source_hashes,
            'data_sha256': {data_name: sha(b'# inert hash-only test evidence\n')}, 'policy': self.policy}}
        self.envelope = Envelope(self.root, 'backup', {
            'UAART_REQUEST_SHA256': 'b' * 64, 'UAART_MANIFEST_SHA256': 'c' * 64,
            'UAART_RUN_ID': '12345', 'UAART_TRANSACTION_ID': self.tx}, self.request, {}, {}, {}, self.code,
            sha(canonical_json(self.code)), self.root / 'fixture-receipt.json', self.package_sha, policy_sha)
        self.backup = {}
        entries = {}
        for index, (local, remote) in enumerate(bundle.SOURCE_PATHS.items()):
            if local in bundle.HISTORICAL or local == 'www_uaart_com_ua_wsgi.py':
                continue
            stored = str(index) + '.before'
            self.backup[stored] = self.source_bytes[remote]
            entries[remote.removeprefix('/home/Carix/')] = {
                'sha256': sha(self.source_bytes[remote]), 'stored': stored, 'mode': 0o600}
        self.backup['wsgi.before'] = self.source_bytes[bundle.SOURCE_PATHS['www_uaart_com_ua_wsgi.py']]
        code_raw = bundle.encoded({'package_sha256': self.package_sha, 'files': entries,
            'database_file': 'crm.snapshot.db', 'database_sha256': 'd' * 64,
            'database_logical_sha256': 'e' * 64, 'database_integrity': 'ok'})
        self.backup['backup_manifest.json'] = code_raw
        phase = dict(format=1, package_manifest_sha256=self.package_sha, transaction_id=self.tx,
            code_backup_manifest_sha256=sha(code_raw), wsgi_before_sha256=sha(self.backup['wsgi.before']),
            wsgi_destination=bundle.SOURCE_PATHS['www_uaart_com_ua_wsgi.py'], wsgi_backup_mode=0o644)
        self.backup['phase_backup_manifest.json'] = bundle.encoded(phase)
        self.transport = FakeTransport(self.source_bytes, self.backup)
        for args in (['init', '-q', '-b', 'main'], ['remote', 'add', 'origin', str(self.root)], ['add', '.'],
                     ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture']):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def phase(self, operation):
        values = dict(self.envelope.values, UAART_BACKUP_MANIFEST_SHA256=sha(self.backup['phase_backup_manifest.json']))
        return replace(self.envelope, operation=operation, values=values)

    def test_policy_digest_matches_actual_lifecycle_producer(self):
        from lifecycle_controller import installation_policy_sha256
        from package_install import encoded as installed_encoder
        plan = {key: value for key, value in self.policy.items() if key != 'authority_policy'}
        plan['authority'] = dict(self.policy['authority_policy'], repository_root='authority')
        self.assertIs(bundle.encoded, installed_encoder)
        self.assertEqual(self.envelope.installation_policy_sha256, installation_policy_sha256(plan))
        self.assertEqual(bundle.encoded({'label': 'Україна'}),
                         installed_encoder({'label': 'Україна'}))
        self.assertFalse(bundle.encoded(self.policy).endswith(b'\n'))

    def test_actual_worker_backup_serialization_is_consumed_without_reencoding(self):
        from lifecycle_worker import InstallWorker
        fixture = self
        class Transaction:
            folder = fixture.root / 'actual-worker-backup'
            def backup(self, lease):
                self.folder.mkdir(mode=0o700)
                (self.folder / 'backup_manifest.json').write_bytes(fixture.backup['backup_manifest.json'])
            def _manifest(self):
                raw = (self.folder / 'backup_manifest.json').read_bytes()
                return json.loads(raw), sha(raw)
        # Exercise the actual phase producer and verifier. Code backup and WSGI
        # acquisition are isolated fixture seams; no production path is opened.
        worker = object.__new__(InstallWorker)
        worker.package = SimpleNamespace(manifest_sha=self.package_sha)
        worker.transaction = Transaction()
        worker.transaction_id = self.tx
        worker.wsgi = SimpleNamespace(
            item={'before_sha256': sha(self.backup['wsgi.before']),
                  'destination': bundle.SOURCE_PATHS['www_uaart_com_ua_wsgi.py']},
            backup=lambda: None, _journal=lambda: {'mode': 0o644})
        produced = worker._prepare_backup(object())
        raw = (worker.transaction.folder / 'phase_backup_manifest.json').read_bytes()
        self.assertEqual(produced['backup_manifest_sha256'], sha(raw))
        self.assertFalse(raw.endswith(b'\n'))
        self.backup['phase_backup_manifest.json'] = raw
        result = bundle.prepare(self.phase('execute'), self.transport)
        self.assertEqual(produced['backup_manifest_sha256'], result.parameters['backup_manifest_sha256'])
        self.assertEqual(self.package_sha,
            sha(next(item.content for item in result.files if item.relative_path == 'package/manifest.json')))

    def test_backup_builds_exact_private_package_and_run_bound_plan(self):
        result = bundle.prepare(self.envelope, self.transport)
        files = {item.relative_path: item for item in result.files}
        self.assertEqual(sha(files['package/manifest.json'].content), self.package_sha)
        self.assertTrue(WORKER_FILES.issubset(files))
        self.assertEqual(result.identity['manifest_sha256'], 'c' * 64)
        self.assertEqual(result.parameters['backup_manifest_sha256'], None)
        self.assertEqual(len(self.transport.calls), len(bundle.SOURCE_PATHS))
        self.assertTrue(all(call[0] == 'source' for call in self.transport.calls))
        plan = json.loads(files[result.parameters['plan_path']].content)
        self.assertEqual(plan['package_manifest_path'], 'package/manifest.json')
        self.assertEqual(plan['authority']['repository_root'], 'authority')
        self.assertEqual(plan['authority']['request_sha256'], 'b' * 64)
        self.assertEqual(plan['authority']['transaction_id'], self.tx)
        self.assertEqual(plan['authority']['installation_approval'], {'path': APPROVAL_REL, 'sha256': 'a' * 64})
        self.assertEqual(sha(bundle.encoded(self.policy)), plan['installation_policy_sha256'])
        self.assertNotIn('PASS', files[result.parameters['plan_path']].content.decode())

    def test_execute_and_rollback_rebuild_original_bytes_after_live_code_changes(self):
        first = bundle.prepare(self.envelope, self.transport)
        original = {item.relative_path: item.content for item in first.files if item.relative_path.startswith('package/')}
        for operation in ('execute', 'rollback'):
            with self.subTest(operation=operation):
                current = dict(self.source_bytes)
                for local, remote in bundle.SOURCE_PATHS.items():
                    if local not in bundle.HISTORICAL:
                        current[remote] = b'changed after backup\n'
                transport = FakeTransport(current, self.backup)
                result = bundle.prepare(self.phase(operation), transport)
                self.assertEqual(original, {item.relative_path: item.content for item in result.files
                                            if item.relative_path.startswith('package/')})
                self.assertEqual({call[1] for call in transport.calls if call[0] == 'source'},
                                 {bundle.SOURCE_PATHS[name] for name in bundle.HISTORICAL})
                self.assertFalse(any('crm.snapshot.db' in call for call in transport.calls))

    def test_changed_recipe_fails_before_source_access(self):
        (self.root / bundle.RECIPE_REL / 'build_release.py').write_bytes(BUILDER + b'# changed\n')
        with self.assertRaisesRegex(ContractError, 'RECIPE_HASH_MISMATCH'):
            bundle.prepare(self.envelope, self.transport)
        self.assertEqual([], self.transport.calls)

    def test_extra_undeclared_recipe_data_fails_before_source_access(self):
        (self.root / bundle.RECIPE_REL / 'extra.txt').write_bytes(b'undeclared')
        with self.assertRaisesRegex(ContractError, 'RECIPE_EXACT_INVENTORY'):
            bundle.prepare(self.envelope, self.transport)
        self.assertEqual([], self.transport.calls)

    def test_policy_change_is_not_authorized_by_recipe_digest(self):
        self.policy['maximum_seconds'] += 1
        with self.assertRaisesRegex(ContractError, 'INSTALLATION_POLICY_HASH_MISMATCH'):
            bundle.prepare(self.envelope, self.transport)
        self.assertEqual([], self.transport.calls)

    def test_different_request_http_checks_fail_before_source_access(self):
        self.request['http_checks'] = {'installed': [], 'baseline': []}
        with self.assertRaisesRegex(ContractError, 'REQUEST_HTTP_POLICY_BINDING'):
            bundle.prepare(self.envelope, self.transport)
        self.assertEqual([], self.transport.calls)

    def test_authority_source_drift_fails_before_source_access(self):
        (self.root / 'automation/control_plane.py').write_bytes(b'changed\n')
        with self.assertRaisesRegex(ContractError, 'AUTHORITY_SOURCE_CHANGED'):
            bundle.prepare(self.envelope, self.transport)
        self.assertEqual([], self.transport.calls)

    def test_source_digest_mismatch_is_rejected(self):
        name = next(iter(self.source_bytes))
        self.source_bytes[name] = b'wrong bytes'
        with self.assertRaisesRegex(ContractError, 'SOURCE_GET_DIGEST_MISMATCH'):
            bundle.prepare(self.envelope, self.transport)

    def test_changed_inner_manifest_rejects_candidate(self):
        envelope = replace(self.envelope, package_manifest_sha256='f' * 64)
        self.policy['package_manifest_sha256'] = 'f' * 64
        envelope = replace(envelope, installation_policy_sha256=sha(bundle.encoded(self.policy)))
        with self.assertRaisesRegex(ContractError, 'BUILT_PACKAGE_MANIFEST_MISMATCH'):
            bundle.prepare(envelope, self.transport)

    def test_wrong_original_backup_is_rejected_before_preimage_reads(self):
        envelope = self.phase('rollback')
        self.backup['phase_backup_manifest.json'] += b' '
        with self.assertRaisesRegex(ContractError, 'BACKUP_GET_DIGEST_MISMATCH'):
            bundle.prepare(envelope, self.transport)
        self.assertEqual(['phase_backup_manifest.json'], [call[1] for call in self.transport.calls])

    def test_malicious_backup_storage_path_is_never_requested(self):
        manifest = json.loads(self.backup['backup_manifest.json'])
        manifest['files']['cars_ui.py']['stored'] = '../crm.db'
        self.backup['backup_manifest.json'] = bundle.encoded(manifest)
        phase = json.loads(self.backup['phase_backup_manifest.json'])
        phase['code_backup_manifest_sha256'] = sha(self.backup['backup_manifest.json'])
        self.backup['phase_backup_manifest.json'] = bundle.encoded(phase)
        with self.assertRaisesRegex(ContractError, 'BACKUP_SOURCE_BINDING'):
            bundle.prepare(self.phase('execute'), self.transport)
        self.assertNotIn('../crm.db', [call[1] for call in self.transport.calls])

    def test_rollback_keeps_pinned_code_commit_separate_from_fresh_authority(self):
        pinned = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD']).decode().strip()
        (self.root / 'fresh-state.txt').write_text('ROLLING_BACK fixture\n')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'durable state'],
                       check=True, capture_output=True)
        latest = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD']).decode().strip()
        subprocess.run(['git', '-C', str(self.root), 'checkout', '--detach', pinned], check=True, capture_output=True)
        result = bundle.prepare(self.phase('rollback'), self.transport)
        plan = json.loads(next(item.content for item in result.files if item.relative_path == bundle.PLAN_PATH))
        self.assertEqual(plan['authority']['main_commit'], latest)
        self.assertEqual(plan['authority']['code_source_commit'], pinned)
        self.assertEqual(plan['authority']['source_repository_root'], 'source_authority')
        self.assertNotEqual(latest, pinned)

    def test_builder_failure_does_not_expose_private_source_output(self):
        with patch.object(bundle.subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, b'1' * 40, b''),
                subprocess.CompletedProcess([], 1, b'private source bytes', b'private credentials')]):
            with self.assertRaisesRegex(ContractError, '^PRIVATE_RELEASE_BUILD_FAILED$'):
                bundle.prepare(self.envelope, self.transport)

    def test_private_workspace_and_source_file_permissions(self):
        original = bundle._build
        roots = []
        def inspect(recipe, sources, package):
            roots.append(sources.parent)
            self.assertEqual(0o700, sources.parent.stat().st_mode & 0o777)
            self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in sources.rglob('*')))
            original(recipe, sources, package)
        with patch.object(bundle, '_build', side_effect=inspect):
            bundle.prepare(self.envelope, self.transport)
        self.assertTrue(roots)
        self.assertFalse(roots[0].exists())


if __name__ == '__main__':
    unittest.main()
