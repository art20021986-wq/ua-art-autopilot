"""Isolated real FenceLease tests; fixture authority is never production evidence."""
import hashlib
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

from cloud.spec_rebuild10 import data_install as d
from cloud.writer_coordination_001 import server_fence as fence


class InstallerInterrupted(BaseException):
    pass


class DataInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root, self.payload, self.control = [self.base / n for n in ('root', 'payload', 'control')]
        for path in (self.root, self.payload, self.control, self.root / 'video', self.root / 'site', self.payload / 'candidate', self.payload / 'candidate' / 'video', self.payload / 'candidate' / 'site', self.control / 'sessions'):
            path.mkdir()
        for name in fence.LOCK_NAMES:
            (self.root / name).write_bytes(b'existing reviewed inode')
        self.session = {'repository': 'art20021986-wq/ua-art-autopilot', 'account': 'Carix', 'production_root': '/home/Carix',
                        'task_id': 'UA-ART-SPEC-REBUILD-10-001', 'expected_main': 'a' * 40, 'plan_sha256': 'b' * 64,
                        'run_id': '1', 'run_attempt': 1, 'nonce': 'c' * 64, 'epoch': 1,
                        'source_sha256': d.sha(Path(fence.__file__).read_bytes())}
        (self.control / 'sessions' / self.session['nonce']).mkdir()
        for name in d.PAGES:
            (self.root / name).write_text('<html>before ' + name + '</html>')
            (self.payload / 'candidate' / name).write_text('<html>after ' + name + ' <a href="#additional-specification">spec</a></html>')
        with sqlite3.connect(str(self.root / 'crm.db')) as conn:
            conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,year TEXT,note TEXT)')
            for n, uid in enumerate(d.UIDS + d.DRAFTS, 1):
                conn.execute('INSERT INTO cars VALUES(?,?,?,?,?,?)', (n, uid, 'KNAGS416BHA14' + ('1028' if n == 16 else f'{n:04d}'), int(n <= 16), '1999' if n == 16 else '2018', 'owner note ' + uid))
        with sqlite3.connect(str(self.root / 'vin_specs_task111_v3.db')) as conn:
            for table, fields in d.SPEC_FIELDS.items():
                names = fields.split(',')
                conn.execute('CREATE TABLE ' + table + '(' + ','.join(n + ' TEXT' for n in names) + ')')
                for n in range(557):
                    values = [f'UA-{(n % 16) + 1:04d}', 'field-' + str(n)] + ['value'] * (len(names) - 2)
                    conn.execute('INSERT INTO ' + table + ' VALUES(' + ','.join('?' for _ in names) + ')', values)
        with sqlite3.connect(str(self.payload / 'spec-rebuild.db')) as conn:
            conn.execute('CREATE TABLE facts(uid TEXT,key TEXT)')
            conn.executemany('INSERT INTO facts VALUES(?,?)', [(f'UA-{(n % 16) + 1:04d}', str(n)) for n in range(557)])
            conn.execute('CREATE TABLE vehicles(uid TEXT,published INTEGER,tombstoned INTEGER)')
            conn.executemany('INSERT INTO vehicles VALUES(?,?,0)', [(uid, 1) for uid in d.UIDS] + [(uid, 0) for uid in d.DRAFTS])
        self.manifest = d.make_manifest(self.root, self.payload)
        self.plan = d.make_install_plan(self.session, self.payload, self.manifest, coordination_plan_sha256='d' * 64, fence_sha256=self.session['source_sha256'])
        self.lease = fence.FenceLease(self.root, self.control, self.session)
        self.lease.acquire()

    def tearDown(self):
        self.lease.close()
        self.temp.cleanup()

    def authority(self, plan, challenge, phase):
        now = time.time()
        return {'status': d.PROOF_STATUS, 'challenge': challenge, 'session': plan['session'],
                'install_plan_sha256': plan['install_plan_sha256'], 'coordination_plan_sha256': plan['coordination_plan_sha256'],
                'candidate_manifest_sha256': plan['manifest']['manifest_sha256'], 'issued_at': now, 'expires_at': now + 20,
                'authorization_receipt_sha256': '1' * 64, 'pause_readback_sha256': '2' * 64, 'drain_receipt_sha256': '3' * 64,
                'storage_quota': {'source': 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA', 'used_bytes': 1000000,
                                  'quota_bytes': 10000000000, 'observed_at': now, 'receipt_sha256': '4' * 64}}

    def installer(self, cls=d.DataInstall, verifier=None):
        return cls(self.lease, self.payload, self.plan, verify_window=verifier or self.authority)

    def assert_before(self):
        with d.db_read(self.root / 'crm.db') as conn:
            self.assertEqual(d.digest(d.crm_rows(conn)), self.manifest['crm']['rows_before_sha256'])
        for name, item in self.manifest['files'].items():
            self.assertEqual(d.file_hash(self.root / name), item['before_sha256'])
        self.assertEqual(d.spec_snapshot(self.root / 'vin_specs_task111_v3.db'), self.manifest['legacy_spec'])
        for name in d.DRAFT_PAGES:
            self.assertFalse((self.root / name).exists())

    def crash_class(self, event, occurrence=1, exception=InstallerInterrupted):
        class Crash(d.DataInstall):
            count = 0
            fired = False
            def _append(inner, actual, **details):
                super()._append(actual, **details)
                if actual == event:
                    inner.count += 1
                    if inner.count == occurrence and not inner.fired:
                        inner.fired = True
                        raise exception('injected isolated process failure')
        return Crash

    def test_apply_all_32_and_year_then_readback_and_rollback(self):
        installer = self.installer()
        handles = list(self.lease.handles)
        with mock.patch('fcntl.flock', side_effect=AssertionError('installer must borrow existing fds')):
            receipt = installer.apply()
            self.assertEqual(receipt['status'], 'DATA_LOCAL_COMMITTED')
            self.assertEqual(installer.read_terminal(), receipt)
            result = installer.rollback_only()
            self.assertEqual(result['status'], 'DATA_ROLLED_BACK_READBACK')
        self.assertEqual(self.lease.handles, handles)
        self.lease._check()
        self.assertFalse(receipt['tasks_resumed'])
        self.assertFalse(receipt['runtime_loaded_verified'])
        self.assert_before()

    def test_no_authority_no_transaction_or_data_writes(self):
        with self.assertRaisesRegex(d.DataInstallError, 'EXTERNAL_WRITER_VERIFICATION_REQUIRED'):
            self.installer(verifier=lambda *_: {}).apply()
        self.assertFalse((self.lease.directory / 'spec-rebuild10-data').exists())
        self.assert_before()

    def test_repeat_apply_refused_read_terminal_is_idempotent(self):
        installer = self.installer()
        first = installer.apply()
        before = d.file_hash(installer.journal_path)
        with self.assertRaisesRegex(d.DataInstallError, 'SESSION_ALREADY_USED'):
            installer.apply()
        self.assertEqual(installer.read_terminal(), first)
        self.assertEqual(d.file_hash(installer.journal_path), before)

    def test_partial_write_exception_compensates(self):
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.installer(self.crash_class('WRITE_DONE', 3, RuntimeError)).apply()
        self.assert_before()
        self.assertEqual(self.installer().read_terminal()['status'], 'DATA_ROLLED_BACK_READBACK')

    def test_installer_interruption_mid_pages_recovers_from_durable_backup(self):
        with self.assertRaises(InstallerInterrupted):
            self.installer(self.crash_class('WRITE_DONE', 8)).apply()
        self.assertNotEqual(d.file_hash(self.root / 'site/UA-0001.html'), self.manifest['files']['site/UA-0001.html']['before_sha256'])
        self.installer().rollback_only()
        self.assert_before()

    def test_installer_interruption_before_sql_commit_recovers(self):
        with self.assertRaises(InstallerInterrupted):
            self.installer(self.crash_class('BEFORE_SQL_COMMIT')).apply()
        with d.db_read(self.root / 'crm.db') as conn:
            self.assertEqual(d.digest(d.crm_rows(conn)), self.manifest['crm']['rows_before_sha256'])
        self.installer().rollback_only()
        self.assert_before()

    def test_installer_interruption_after_sql_commit_recovers(self):
        with self.assertRaises(InstallerInterrupted):
            self.installer(self.crash_class('SQL_COMMITTED')).apply()
        with d.db_read(self.root / 'crm.db') as conn:
            self.assertEqual(d.digest(d.crm_rows(conn)), self.manifest['crm']['rows_after_sha256'])
        self.installer().rollback_only()
        self.assert_before()

    def test_foreign_page_blocks_all_rollback_without_overwrite(self):
        with self.assertRaises(InstallerInterrupted):
            self.installer(self.crash_class('WRITE_DONE', 8)).apply()
        changed = self.root / 'video/UA-0001.html'
        changed.write_bytes(b'foreign writer content')
        before = {n: d.file_hash(self.root / n) for n in self.manifest['files']}
        with self.assertRaisesRegex(d.DataInstallError, 'FOREIGN_WRITE_REFUSED'):
            self.installer().rollback_only()
        self.assertEqual({n: d.file_hash(self.root / n) for n in before}, before)
        self.assertEqual(changed.read_bytes(), b'foreign writer content')

    def test_foreign_crm_edit_after_commit_blocks_rollback(self):
        self.installer().apply()
        with sqlite3.connect(str(self.root / 'crm.db')) as conn:
            conn.execute("UPDATE cars SET note='foreign edit' WHERE auto_number='UA-0017'")
        before = {n: d.file_hash(self.root / n) for n in self.manifest['files']}
        with self.assertRaisesRegex(d.DataInstallError, 'FOREIGN_CRM_WRITE_REFUSED'):
            self.installer().rollback_only()
        self.assertEqual({n: d.file_hash(self.root / n) for n in before}, before)

    def test_authority_loss_retains_intent_and_requires_recovery(self):
        count = 0
        def verifier(plan, challenge, phase):
            nonlocal count
            if phase.startswith('BEFORE_WRITE:'):
                count += 1
            if count >= 3:
                return {}
            return self.authority(plan, challenge, phase)
        with self.assertRaisesRegex(d.DataInstallError, 'ROLLBACK_BLOCKED_TASKS_REMAIN_PAUSED'):
            self.installer(verifier=verifier).apply()
        self.assertTrue(self.lease.held)
        self.assertTrue((self.control / 'active-intent.json').exists())
        self.installer().rollback_only()
        self.assert_before()

    def test_changed_candidate_rejected_before_mutation(self):
        (self.payload / 'candidate' / 'site/UA-0001.html').write_text('tampered')
        with self.assertRaisesRegex(d.DataInstallError, 'CANDIDATE_CHANGED'):
            self.installer()
        self.assert_before()

    def test_changed_legacy_spec_refuses_install(self):
        with sqlite3.connect(str(self.root / 'vin_specs_task111_v3.db')) as conn:
            conn.execute("UPDATE additional_specification SET field_value='changed' WHERE field_key='field-0'")
        with self.assertRaisesRegex(d.DataInstallError, 'LEGACY_SPEC_CHANGED'):
            self.installer().apply()
        self.assertFalse((self.lease.directory / 'spec-rebuild10-data').exists())

    def test_lock_replacement_invalidates_real_lease(self):
        lock = self.root / fence.LOCK_NAMES[0]
        lock.unlink()
        lock.write_bytes(b'foreign inode')
        with self.assertRaisesRegex(fence.FenceError, 'RESOURCE_LOCK_REPLACED'):
            self.installer().apply()
        self.assert_before()

    def test_quota_80_refuses_before_backup(self):
        def verifier(plan, challenge, phase):
            result = self.authority(plan, challenge, phase)
            result['storage_quota']['used_bytes'] = 8000000000
            return result
        with self.assertRaisesRegex(d.DataInstallError, 'HEAVY_DEPLOY_GATE_80'):
            self.installer(verifier=verifier).apply()
        self.assert_before()

    def test_symlink_target_refused(self):
        path = self.root / 'video/UA-0001.html'
        path.unlink()
        path.symlink_to(self.root / 'site/UA-0001.html')
        with self.assertRaises(OSError):
            self.installer().apply()

    def test_published_draft_drift_refused(self):
        with sqlite3.connect(str(self.root / 'crm.db')) as conn:
            conn.execute("UPDATE cars SET published=1 WHERE auto_number='UA-0017'")
        with self.assertRaisesRegex(d.DataInstallError, 'CRM_FULL_ROWS_CHANGED'):
            self.installer().apply()
        self.assertFalse((self.lease.directory / 'spec-rebuild10-data').exists())

    def test_truncated_journal_refuses_recovery(self):
        installer = self.installer(self.crash_class('WRITE_DONE', 2))
        with self.assertRaises(InstallerInterrupted):
            installer.apply()
        with installer.journal_path.open('ab') as stream:
            stream.write(b'{')
        with self.assertRaisesRegex(d.DataInstallError, 'JOURNAL_INCOMPLETE'):
            self.installer().rollback_only()

    def test_existing_new_store_wal_refused_before_install(self):
        (self.root / 'spec-rebuild.db-wal').write_bytes(b'foreign WAL')
        with self.assertRaisesRegex(d.DataInstallError, 'DATABASE_SIDECAR_PRESENT'):
            self.installer().apply()
        self.assertFalse((self.lease.directory / 'spec-rebuild10-data').exists())

    def test_foreign_new_store_wal_prevents_rollback_and_terminal_acceptance(self):
        self.installer().apply()
        (self.root / 'spec-rebuild.db-wal').write_bytes(b'foreign WAL')
        before = {n: d.file_hash(self.root / n) for n in self.manifest['files']}
        for operation in (self.installer().rollback_only, self.installer().read_terminal):
            with self.assertRaisesRegex(d.DataInstallError, 'DATABASE_SIDECAR_PRESENT'):
                operation()
        self.assertEqual({n: d.file_hash(self.root / n) for n in before}, before)

    def test_missing_commit_receipt_can_be_finalized_without_replaying(self):
        installer = self.installer(self.crash_class('DATA_LOCAL_COMMITTED'))
        with self.assertRaises(InstallerInterrupted):
            installer.apply()
        journal_before = d.file_hash(installer.journal_path)
        result = self.installer().finalize_terminal()
        self.assertEqual(result['status'], 'DATA_LOCAL_COMMITTED')
        self.assertEqual(d.file_hash(installer.journal_path), journal_before)

    def test_missing_rollback_receipt_can_be_finalized_without_replaying(self):
        self.installer().apply()
        installer = self.installer(self.crash_class('DATA_ROLLED_BACK_READBACK'))
        with self.assertRaises(InstallerInterrupted):
            installer.rollback_only()
        journal_before = d.file_hash(installer.journal_path)
        result = self.installer().rollback_only()
        self.assertEqual(result['status'], 'DATA_ROLLED_BACK_READBACK')
        self.assertEqual(d.file_hash(installer.journal_path), journal_before)
        self.assert_before()

    def test_new_sqlite_inode_during_authority_check_refused(self):
        def verifier(plan, challenge, phase):
            result = self.authority(plan, challenge, phase)
            other = self.root / 'replacement.db'
            shutil.copyfile(self.root / 'crm.db', other)
            os.replace(other, self.root / 'crm.db')
            return result
        with self.assertRaisesRegex(d.DataInstallError, 'DATABASE_INODE_CHANGED'):
            self.installer(verifier=verifier).apply()
        self.assertFalse((self.lease.directory / 'spec-rebuild10-data').exists())

    def test_python310_authorizer_semantics_full_install_and_rollback(self):
        # CPython <3.11 accepts None as the callback but then fails authorization.
        # Reproduce its observable behavior even when tests run under newer Python.
        disabled_calls = []
        class Python310Connection(sqlite3.Connection):
            def set_authorizer(connection, callback):
                if callback is None:
                    disabled_calls.append(True)
                    return super().set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
                return super().set_authorizer(callback)
        original_connect = sqlite3.connect
        def legacy_connect(*args, **kwargs):
            kwargs['factory'] = Python310Connection
            return original_connect(*args, **kwargs)
        with mock.patch.object(d.sqlite3, 'connect', side_effect=legacy_connect):
            operation = self.installer()
            self.assertEqual(operation.apply()['status'], 'DATA_LOCAL_COMMITTED')
            self.assertEqual(operation.read_terminal()['status'], 'DATA_LOCAL_COMMITTED')
            self.assertEqual(operation.rollback_only()['status'], 'DATA_ROLLED_BACK_READBACK')
            self.assertEqual(operation.read_terminal()['status'], 'DATA_ROLLED_BACK_READBACK')
        self.assertEqual(disabled_calls, [])
        self.assert_before()

    def test_authorizer_remains_restrictive_after_year_update(self):
        operation = self.installer()
        connection = sqlite3.connect(str(self.root / 'crm.db'), isolation_level=None)
        try:
            connection.execute('BEGIN IMMEDIATE')
            operation._write_year(connection)
            operation._crm(connection, 'after')
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("UPDATE cars SET note='unapproved' WHERE auto_number='UA-0016'")
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DELETE FROM cars WHERE auto_number='UA-0017'")
            connection.rollback()
        finally:
            connection.close()
        self.assert_before()

    def test_thread_transfer_refused(self):
        installer, errors = self.installer(), []
        def other():
            try:
                installer.apply()
            except d.DataInstallError as error:
                errors.append(str(error))
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
        self.assertEqual(errors, ['SAME_LIVE_HOLDER_REQUIRED'])
        self.assert_before()


if __name__ == '__main__':
    unittest.main()
