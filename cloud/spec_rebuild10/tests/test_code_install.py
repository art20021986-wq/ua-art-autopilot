"""Isolated exact-payload tests. Every authority receipt here is SYNTHETIC.

Set SPEC_CODE_PACKAGE and SPEC_CODE_DEPENDENCIES for a relocated private stage.
No test imports application code or acts on a production directory.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

from cloud.spec_rebuild10 import code_install as c
from cloud.spec_rebuild10 import data_install as d
from cloud.spec_rebuild10.tests import test_data_install as dt
from cloud.writer_coordination_001 import server_fence as fence


HERE = Path(__file__).resolve().parents[4]


def private_inputs():
    package = Path(os.environ.get('SPEC_CODE_PACKAGE', HERE / 'private-runtime/rebuild10-runtime-package-r2')).absolute()
    deps = os.environ.get('SPEC_CODE_DEPENDENCIES')
    paths = {n: Path(deps).absolute() / n for n in ('catalog_design_golden.html', 'catalog_design_guard.py', 'stranica.py')} if deps else {
        'catalog_design_golden.html': HERE / 'private-runtime/publisher-inputs-20260909T074856Z/catalog_design_golden.html',
        'catalog_design_guard.py': HERE / 'private-runtime/publisher-inputs-20260909T074529Z/catalog_design_guard.py',
        'stranica.py': HERE / 'private-runtime/publisher-inputs-20260909T074529Z/stranica.py'}
    if not (package / 'runtime-package.tar.gz').exists() or not all(p.exists() for p in paths.values()):
        raise unittest.SkipTest('Private exact r2 package/dependencies required; set SPEC_CODE_PACKAGE and SPEC_CODE_DEPENDENCIES')
    return package, paths


def prepare_code_root(root, manifest, paths):
    for name, source in paths.items():
        shutil.copy2(source, root / name)
    before = {}
    # The 29 afterimages are real; old preimages here are labeled synthetic.
    absent_old = {'car_number_allocator.py', 'card_lifecycle.py', 'card_shell.py', 'spec_publication.py'}
    for name in manifest['files']:
        path = root / name
        if name.startswith('spec_rebuild10/') or name == 'spec_rebuild10_bootstrap.py' or name in absent_old:
            before[name] = None
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('# SYNTHETIC BEFORE ' + name + '\n').encode())
            path.chmod(0o640)
            before[name] = d.file_hash(path)
    return before


class CodeInstallTests(unittest.TestCase):
    def setUp(self):
        self.package, deps = private_inputs()
        # Reuse the actual FenceLease and synthetic 32-page /18-row fixture,
        # without inheriting and silently running its independent test methods.
        self.fixture = dt.DataInstallTests('test_apply_all_32_and_year_then_readback_and_rollback')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        for key in ('root', 'payload', 'session', 'lease', 'control', 'base'):
            setattr(self, key, getattr(self.fixture, key))
        self.manifest, self.payload_code = c.inspect_package(self.package)
        self.before = prepare_code_root(self.root, self.manifest, deps)
        self.plan = c.make_install_plan(self.session, self.package, self.before,
            coordination_plan_sha256='d' * 64, fence_sha256=self.session['source_sha256'])
        self.combined_plan = c.make_combined_plan(self.plan, self.fixture.plan)

    def authority(self, plan, challenge, phase):
        return self.fixture.authority(plan, challenge, phase)

    def installer(self, verifier=None, cls=c.CodeInstall):
        return cls(self.lease, self.package, self.plan, verify_window=verifier or self.authority)

    def combined(self, verifier=None):
        return c.CombinedInstall(self.lease, self.package, self.payload, self.combined_plan,
                                 verify_window=verifier or self.authority)

    def assert_before(self):
        operation = self.installer()
        if operation.transaction.exists():
            operation._load_events()
        operation._all('before')
        self.fixture.assert_before()

    def crash_class(self, event, occurrence=1, exception=dt.InstallerInterrupted):
        class Crash(c.CodeInstall):
            count = 0
            def _append(inner, actual, **details):
                super()._append(actual, **details)
                if actual == event:
                    inner.count += 1
                    if inner.count == occurrence:
                        raise exception('synthetic interruption')
        return Crash

    def test_exact_29_real_payload_admission(self):
        self.assertEqual(len(self.payload_code), 29)
        self.assertEqual(self.manifest['manifest_sha256'], c.MANIFEST_SHA256)

    def test_real_payload_cycle_preserves_modes_and_borrowed_fds(self):
        operation = self.installer()
        original = {n: d.read(self.root / n) for n, h in self.before.items() if h}
        handles = list(self.lease.handles)
        with mock.patch('fcntl.flock', side_effect=AssertionError('double flock forbidden')):
            receipt = operation.apply()
            self.assertEqual(receipt['status'], 'CODE_LOCAL_INSTALLED')
            self.assertEqual(operation.read_terminal(), receipt)
            for name, raw in self.payload_code.items():
                self.assertEqual((self.root / name).read_bytes(), raw)
            operation.rollback_only()
        self.assertEqual(self.lease.handles, handles)
        self.lease._check()
        for name, item in original.items():
            current = d.read(self.root / name)
            self.assertEqual((current['sha256'], current['mode'], current['mtime_ns']), (item['sha256'], item['mode'], item['mtime_ns']))
        self.assert_before()

    def test_no_authority_no_mutation(self):
        with self.assertRaisesRegex(c.CodeInstallError, 'EXTERNAL_WRITER_VERIFICATION_REQUIRED'):
            self.installer(verifier=lambda *_: {}).apply()
        self.assert_before()

    def test_none_authority_is_not_positive_default(self):
        with self.assertRaisesRegex(c.CodeInstallError, 'EXTERNAL_WRITER_VERIFICATION_REQUIRED'):
            c.CodeInstall(self.lease, self.package, self.plan, verify_window=None).apply()
        self.assert_before()

    def test_stale_authority_refused(self):
        def stale(*args):
            proof = self.authority(*args)
            proof['issued_at'] -= 20
            return proof
        with self.assertRaisesRegex(c.CodeInstallError, 'WINDOW_PROOF_STALE'):
            self.installer(verifier=stale).apply()

    def test_archive_tamper_refused(self):
        target = self.base / 'bad-package'
        shutil.copytree(self.package, target)
        (target / 'runtime-package.tar.gz').write_bytes(b'foreign')
        with self.assertRaisesRegex(c.CodeInstallError, 'EXACT_R2_ARCHIVE_REQUIRED'):
            c.inspect_package(target)

    def test_manifest_tamper_refused(self):
        target = self.base / 'bad-package'
        shutil.copytree(self.package, target)
        value = json.loads((target / 'runtime-manifest.json').read_bytes())
        value['version'] = 'unapproved'
        (target / 'runtime-manifest.json').write_bytes(d.canonical(value))
        with self.assertRaisesRegex(c.CodeInstallError, 'EXACT_R2_MANIFEST_REQUIRED'):
            c.inspect_package(target)

    def test_missing_before_target_refused(self):
        value = dict(self.before)
        value.pop('db.py')
        with self.assertRaisesRegex(c.CodeInstallError, 'EXACT_BEFORE_29_REQUIRED'):
            c.make_install_plan(self.session, self.package, value, coordination_plan_sha256='d' * 64, fence_sha256=self.session['source_sha256'])

    def test_dependency_drift_blocks_apply(self):
        (self.root / 'stranica.py').write_bytes(b'foreign')
        with self.assertRaisesRegex(c.CodeInstallError, 'SHELL_DEPENDENCY_CHANGED'):
            self.installer().apply()

    def test_dependency_drift_blocks_all_rollback(self):
        operation = self.installer()
        operation.apply()
        (self.root / 'catalog_design_guard.py').write_bytes(b'foreign')
        hashes = {n: d.file_hash(self.root / n) for n in self.plan['after']}
        with self.assertRaisesRegex(c.CodeInstallError, 'SHELL_DEPENDENCY_CHANGED'):
            operation.rollback_only()
        self.assertEqual(hashes, {n: d.file_hash(self.root / n) for n in hashes})

    def test_unowned_new_directory_refused(self):
        (self.root / c.NEW_DIRECTORY).mkdir()
        with self.assertRaisesRegex(c.CodeInstallError, 'UNOWNED_RUNTIME_DIRECTORY'):
            self.installer().apply()

    def test_symlink_new_directory_refused(self):
        (self.root / c.NEW_DIRECTORY).symlink_to(self.payload)
        with self.assertRaises((c.CodeInstallError, d.DataInstallError)):
            self.installer().apply()

    def test_replaced_lock_refused(self):
        path = self.root / fence.LOCK_NAMES[0]
        old = self.root / 'old-lock'
        path.rename(old)
        path.write_bytes(b'new')
        with self.assertRaisesRegex(fence.FenceError, 'RESOURCE_LOCK_REPLACED'):
            self.installer().apply()

    def test_thread_mismatch_refused(self):
        operation = self.installer()
        errors = []
        def run():
            try:
                operation.apply()
            except Exception as error:
                errors.append(str(error))
        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        self.assertEqual(errors, ['SAME_LIVE_HOLDER_REQUIRED'])

    def test_quota_80_refused(self):
        def high(*args):
            proof = self.authority(*args)
            proof['storage_quota']['used_bytes'] = 8000000000
            return proof
        with self.assertRaisesRegex(c.CodeInstallError, 'HEAVY_DEPLOY_GATE_80'):
            self.installer(verifier=high).apply()
        self.assert_before()

    def test_interrupted_partial_code_recovers(self):
        with self.assertRaises(dt.InstallerInterrupted):
            self.installer(cls=self.crash_class('WRITE_DONE', 7)).apply()
        self.installer().rollback_only()
        self.assert_before()

    def test_interrupted_new_directory_recovers(self):
        with self.assertRaises(dt.InstallerInterrupted):
            self.installer(cls=self.crash_class('DIRECTORY_CREATED')).apply()
        self.installer().rollback_only()
        self.assert_before()

    def test_unrecorded_directory_creation_requires_external_recovery(self):
        operation = self.installer()
        original = operation._append
        def crash(event, **details):
            if event == 'DIRECTORY_CREATED':
                raise dt.InstallerInterrupted('before inode proof')
            original(event, **details)
        operation._append = crash
        with self.assertRaises(dt.InstallerInterrupted):
            operation.apply()
        with self.assertRaisesRegex(c.CodeInstallError, 'UNOWNED_RUNTIME_DIRECTORY'):
            self.installer().rollback_only()

    def test_interrupted_exclusive_link_recovers(self):
        with self.assertRaises(dt.InstallerInterrupted):
            self.installer(cls=self.crash_class('TEMP_LINKED')).apply()
        self.installer().rollback_only()
        self.assert_before()

    def test_foreign_untouched_code_blocks_entire_compensation(self):
        with self.assertRaises(dt.InstallerInterrupted):
            self.installer(cls=self.crash_class('WRITE_DONE', 1)).apply()
        (self.root / 'vin_spec_service.py').write_bytes(b'foreign')
        first = (self.root / 'ai_filter.py').read_bytes()
        with self.assertRaisesRegex(c.CodeInstallError, 'FOREIGN_WRITE_REFUSED'):
            self.installer().rollback_only()
        self.assertEqual((self.root / 'ai_filter.py').read_bytes(), first)

    def test_foreign_new_directory_entry_blocks_entire_compensation(self):
        operation = self.installer()
        operation.apply()
        (self.root / 'spec_rebuild10/foreign.txt').write_bytes(b'foreign')
        before = d.file_hash(self.root / 'db.py')
        with self.assertRaisesRegex(c.CodeInstallError, 'FOREIGN_RUNTIME_DIRECTORY_ENTRY'):
            operation.rollback_only()
        self.assertEqual(d.file_hash(self.root / 'db.py'), before)

    def test_changed_backup_blocks_entire_compensation(self):
        operation = self.installer()
        operation.apply()
        next((operation.transaction / 'backup').iterdir()).write_bytes(b'foreign')
        before = d.file_hash(self.root / 'db.py')
        with self.assertRaisesRegex(c.CodeInstallError, 'BACKUP_BYTES_CHANGED'):
            operation.rollback_only()
        self.assertEqual(d.file_hash(self.root / 'db.py'), before)

    def test_torn_journal_refused(self):
        operation = self.installer()
        operation.apply()
        with operation.journal_path.open('ab') as stream:
            stream.write(b'{')
        with self.assertRaisesRegex(c.CodeInstallError, 'JOURNAL_INCOMPLETE'):
            operation.rollback_only()

    def test_missing_code_terminal_finalizes_without_reinstall(self):
        operation = self.installer()
        operation.apply()
        (operation.transaction / 'terminal-CODE_LOCAL_INSTALLED.json').unlink()
        journal = d.file_hash(operation.journal_path)
        self.assertEqual(self.installer().finalize_terminal()['status'], 'CODE_LOCAL_INSTALLED')
        self.assertEqual(journal, d.file_hash(operation.journal_path))
        with self.assertRaisesRegex(c.CodeInstallError, 'SESSION_ALREADY_USED'):
            self.installer().apply()

    def test_combined_actual29_and_synthetic32_cycle_one_plan(self):
        seen = []
        def authority(plan, challenge, phase):
            self.assertEqual(plan, self.combined_plan)
            seen.append(phase)
            return self.authority(plan, challenge, phase)
        operation = self.combined(verifier=authority)
        with mock.patch('fcntl.flock', side_effect=AssertionError('double flock')):
            receipt = operation.apply()
            self.assertEqual(receipt['status'], 'COMBINED_LOCAL_INSTALLED')
            self.assertEqual(operation.read_terminal(), receipt)
            operation.rollback_only()
            operation.rollback_only()
        self.assertTrue(any(p.startswith('CODE:') for p in seen))
        self.assertTrue(any(p.startswith('DATA:') for p in seen))
        self.assertFalse(receipt['runtime_loaded_verified'])
        self.assert_before()

    def test_combined_data_failure_keeps_code_until_explicit_recovery(self):
        operation = self.combined()
        original = operation.data._append
        def fail(event, **details):
            original(event, **details)
            if event == 'WRITE_DONE':
                raise RuntimeError('injected data failure')
        operation.data._append = fail
        with self.assertRaisesRegex(c.CodeInstallError, 'COMBINED_OUTCOME_REQUIRES_DURABLE_RECOVERY'):
            operation.apply()
        self.assertEqual(d.file_hash(self.root / 'db.py'), self.plan['after']['db.py'])
        self.combined().rollback_only()
        self.assert_before()

    def test_combined_foreign_code_blocks_data_compensation(self):
        operation = self.combined()
        operation.apply()
        (self.root / 'spec_rebuild10/foreign.txt').write_bytes(b'foreign')
        data_hash = d.file_hash(self.root / 'site/UA-0001.html')
        with self.assertRaisesRegex(c.CodeInstallError, 'FOREIGN_RUNTIME_DIRECTORY_ENTRY'):
            operation.rollback_only()
        self.assertEqual(d.file_hash(self.root / 'site/UA-0001.html'), data_hash)
        with d.db_read(self.root / 'crm.db') as conn:
            self.assertEqual(d.digest(d.crm_rows(conn)), self.fixture.manifest['crm']['rows_after_sha256'])

    def test_combined_foreign_crm_blocks_code_compensation(self):
        operation = self.combined()
        operation.apply()
        with sqlite3.connect(str(self.root / 'crm.db')) as conn:
            conn.execute("UPDATE cars SET note='foreign' WHERE auto_number='UA-0018'")
        before = d.file_hash(self.root / 'db.py')
        with self.assertRaisesRegex(c.CodeInstallError, 'FOREIGN_CRM_WRITE_REFUSED'):
            operation.rollback_only()
        self.assertEqual(d.file_hash(self.root / 'db.py'), before)

    def test_combined_after_sql_commit_interruption_recovers(self):
        operation = self.combined()
        original = operation.data._append
        def crash(event, **details):
            original(event, **details)
            if event == 'SQL_COMMITTED':
                raise dt.InstallerInterrupted('after SQL commit')
        operation.data._append = crash
        with self.assertRaises(dt.InstallerInterrupted):
            operation.apply()
        self.combined().rollback_only()
        self.assert_before()

    def test_combined_missing_terminal_receipt_finalizes(self):
        operation = self.combined()
        operation.apply()
        (operation.transaction / 'terminal-COMBINED_LOCAL_INSTALLED.json').unlink()
        self.assertEqual(self.combined().finalize_terminal()['status'], 'COMBINED_LOCAL_INSTALLED')

    def test_combined_different_session_rejected(self):
        data_plan = json.loads(d.canonical(self.fixture.plan))
        data_plan['session']['epoch'] += 1
        value = dict(data_plan)
        value.pop('install_plan_sha256')
        data_plan['install_plan_sha256'] = d.digest(value)
        with self.assertRaisesRegex(c.CodeInstallError, 'ONE_EXACT_SESSION_REQUIRED'):
            c.make_combined_plan(self.plan, data_plan)


def actual_private_cycle(snapshot, payload, package, dependencies, *, before_source_dir=None, before_observation=None):
    """Relocatable real 32-page/database + exact29 afterimage copy-only exercise.

    Supply both before_source_dir and before_observation to validate and exercise
    the exact observed old source bytes. Without them old code is synthetic.
    Returns only redacted evidence and never imports source payload.
    """
    package, snapshot, payload, dependencies = [Path(p).absolute() for p in (package, snapshot, payload, dependencies)]
    manifest, _ = c.inspect_package(package)
    with tempfile.TemporaryDirectory(prefix='spec-combined-isolated-') as folder:
        base = Path(folder)
        root, control = base / 'root', base / 'control'
        shutil.copytree(snapshot, root)
        control.mkdir()
        (control / 'sessions').mkdir()
        session = {'repository': 'art20021986-wq/ua-art-autopilot', 'account': 'Carix', 'production_root': '/home/Carix',
                   'task_id': 'UA-ART-SPEC-REBUILD-10-001', 'expected_main': 'a' * 40, 'plan_sha256': 'b' * 64,
                   'run_id': '1', 'run_attempt': 1, 'nonce': 'c' * 64, 'epoch': 1,
                   'source_sha256': d.file_hash(Path(fence.__file__).absolute())}
        (control / 'sessions' / session['nonce']).mkdir()
        for name in fence.LOCK_NAMES:
            path = root / name
            if not path.exists():
                path.write_bytes(b'isolated existing lock inode')
        if before_source_dir is None and before_observation is None:
            before = prepare_code_root(root, manifest, {name: dependencies / name for name in manifest['unchanged_execution_dependency_pins']})
            preimage_label = 'SYNTHETIC'
        else:
            c.require(before_source_dir is not None and before_observation is not None, 'BOTH_REAL_BEFORE_INPUTS_REQUIRED')
            source = d.directory(Path(before_source_dir).absolute())
            observation = json.loads(Path(before_observation).read_bytes()) if not isinstance(before_observation, dict) else before_observation
            observation = observation.get('live_code_observation', observation)
            c.require(observation['runtime_manifest_sha256'] == c.MANIFEST_SHA256
                      and observation['new_runtime_directory_absent'] is True
                      and set(observation['files']) == set(manifest['files']) | set(manifest['unchanged_execution_dependency_pins']), 'EXACT_BEFORE_OBSERVATION_REQUIRED')
            before = {name: observation['files'][name] for name in manifest['files']}
            for name, expected in before.items():
                path = root / name
                c.require(not path.exists() and not path.is_symlink(), 'COPY_ROOT_HAS_UNEXPECTED_CODE')
                if expected is not None:
                    c.require(d.file_hash(source / name) == expected, 'REAL_BEFORE_SOURCE_CHANGED:' + name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / name, path)
                    c.require(d.file_hash(path) == expected, 'REAL_BEFORE_COPY_CHANGED')
                else:
                    candidate = source / name
                    c.require(not candidate.exists() and not candidate.is_symlink(), 'OBSERVED_ABSENT_SOURCE_PRESENT')
            for name, expected in manifest['unchanged_execution_dependency_pins'].items():
                c.require(observation['files'][name] == expected and d.file_hash(dependencies / name) == expected, 'DEPENDENCY_OBSERVATION_CHANGED')
                shutil.copy2(dependencies / name, root / name)
            preimage_label = 'EXACT_OBSERVED_PRIVATE_13_PRESENT_16_ABSENT'
        data_manifest = d.make_manifest(root, payload)
        data_plan = d.make_install_plan(session, payload, data_manifest, coordination_plan_sha256='d' * 64, fence_sha256=session['source_sha256'])
        code_plan = c.make_install_plan(session, package, before, coordination_plan_sha256='d' * 64, fence_sha256=session['source_sha256'])
        plan = c.make_combined_plan(code_plan, data_plan)
        lease = fence.FenceLease(root, control, session)
        lease.acquire()
        try:
            def synthetic_authority(plan, challenge, phase):
                now = time.time()
                return {'status': d.PROOF_STATUS, 'challenge': challenge, 'session': plan['session'],
                        'install_plan_sha256': plan['install_plan_sha256'], 'coordination_plan_sha256': plan['coordination_plan_sha256'],
                        'candidate_manifest_sha256': plan['manifest']['manifest_sha256'], 'issued_at': now, 'expires_at': now + 20,
                        'authorization_receipt_sha256': '1' * 64, 'pause_readback_sha256': '2' * 64, 'drain_receipt_sha256': '3' * 64,
                        'storage_quota': {'source': 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA', 'used_bytes': 1000000,
                                          'quota_bytes': 10000000000, 'observed_at': now, 'receipt_sha256': '4' * 64}}
            operation = c.CombinedInstall(lease, package, payload, plan, verify_window=synthetic_authority)
            with mock.patch('fcntl.flock', side_effect=AssertionError('double flock forbidden')):
                installed = operation.apply()
                operation.read_terminal()
                rolled_back = operation.rollback_only()
                operation.read_terminal()
            return {'status': 'PASS', 'authority': 'SYNTHETIC_ISOLATED_TEST_ONLY', 'code_preimages': preimage_label,
                    'code_afterimages': 'EXACT_PRIVATE_R2_29', 'data_fixture': 'REAL_PRIVATE_32_HTML_18_CRM_ROWS',
                    'runtime_manifest_sha256': c.MANIFEST_SHA256, 'archive_sha256': c.ARCHIVE_SHA256,
                    'code_installer_sha256': c.source_hash(), 'data_installer_sha256': d.file_hash(Path(d.__file__).absolute()),
                    'installed_status': installed['status'], 'rollback_status': rolled_back['status'],
                    'code_files': 29, 'html_files': 32, 'crm_rows_verified': 18, 'legacy_facts': 557,
                    'production_changed': False, 'runtime_loaded_verified': False, 'overall_gate_b': 'NOT_EVALUATED'}
        finally:
            lease.close()


if __name__ == '__main__':
    unittest.main()
