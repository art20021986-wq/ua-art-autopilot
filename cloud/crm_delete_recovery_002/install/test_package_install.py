"""Offline installation mechanics with real SQLite WAL and real flock locks."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from package_install import (Package, FixtureInstallTransaction, ExistingLocksLease,
    TASK, SUPERVISOR_ID, SUPERVISOR_COMMAND, application_schema, encoded, sha)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root, self.stage, self.journal = (self.base / name for name in ('root', 'package', 'journal'))
        for folder in (self.root, self.stage, self.journal):
            folder.mkdir(mode=0o700)
        self.originals = {name: ('VALUE = %r\n' % name).encode()
                          for name in ('db.py', 'run_all.py', 'start_safe.py', 'publication_fence.py',
                                       'cars_ui.py', 'publikaciya.py')}
        for name, raw in self.originals.items():
            (self.root / name).write_bytes(raw)
        for name in ('.start_safe.singleton.lock', '.ua_art_publish_transaction.lock'):
            (self.root / name).touch(mode=0o600)
        self.conn = sqlite3.connect(self.root / 'crm.db')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA wal_autocheckpoint=0')
        self.conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,price INTEGER,note TEXT)')
        self.conn.execute("INSERT INTO cars VALUES (8,12000,'original')")
        self.conn.commit()
        self.schema_sha = application_schema(self.conn)
        self.schema_source = Path(__file__).resolve().parent.parent / 'deletion_core/deletion_state.py'
        (self.stage / 'schema.py').write_bytes(self.schema_source.read_bytes())
        self.manifest = {
            'format': 1, 'task': TASK, 'root': '/home/Carix',
            'supervisor': {'id': SUPERVISOR_ID, 'command': SUPERVISOR_COMMAND},
            'application_schema_sha256': self.schema_sha,
            'source_guards': {name: sha(self.originals[name]) for name in
                              ('db.py', 'run_all.py', 'start_safe.py', 'publication_fence.py')},
            'deletion_schema': {'payload': 'schema.py', 'sha256': sha(self.schema_source.read_bytes())},
            'files': [],
        }
        config = encoded(dict(version=1, application_schema_sha256=self.schema_sha,
            source_sha256=self.manifest['source_guards'], shared={}, shared_routes={},
            direct_route_prefixes={'video': [], 'site': []}, writers_receipt_sha256='a' * 64))
        (self.stage / 'runtime.json').write_bytes(config)
        self.manifest['runtime_config'] = dict(destination='ua_crm_deletion_state/runtime.json',
            payload='runtime.json', payload_sha256=sha(config), before_sha256=None)
        for name, role in [('cars_ui.py', 'entrypoint'), ('publikaciya.py', 'writer'),
                           ('ua_delete_runtime.py', 'helper'), ('ua_crm_deletion_core/__init__.py', 'helper')]:
            raw = ('INSTALLED = %r\n' % name).encode()
            payload = 'payload-' + name.replace('/', '-')
            (self.stage / payload).write_bytes(raw)
            self.manifest['files'].append(dict(destination=name,
                before_sha256=sha(self.originals[name]) if name in self.originals else None,
                payload=payload, payload_sha256=sha(raw), role=role))
        self.package = self.load_package()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def load_package(self):
        raw = encoded(self.manifest)
        (self.stage / 'manifest.json').write_bytes(raw)
        return Package(self.stage, sha(raw))

    def lease(self):
        # A fixture has no provider supervisor. The real lock operations remain
        # unchanged; the process inventory is isolated for deterministic tests.
        return ExistingLocksLease(self.root, inventory=lambda: [])

    def transaction(self, **kwargs):
        return FixtureInstallTransaction(self.package, self.root, self.journal, **kwargs)

    def test_default_validation_never_claims_production_ready(self):
        before = sorted(path.name for path in self.root.iterdir())
        report = self.package.report()
        self.assertEqual('OFFLINE_VALIDATED', report['status'])
        self.assertFalse(report['production_ready'])
        self.assertEqual('cars_ui.py', report['install_order'][-1])
        self.assertTrue(report['runtime_payload_missing'])
        self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))

    def test_payload_hash_and_manifest_hash_are_enforced(self):
        with self.assertRaisesRegex(RuntimeError, 'MANIFEST_HASH_MISMATCH'):
            Package(self.stage, '0' * 64)
        item = self.manifest['files'][0]
        (self.stage / item['payload']).write_bytes(b'changed=True\n')
        with self.assertRaisesRegex(RuntimeError, 'PAYLOAD_HASH_MISMATCH'):
            self.load_package()

    def test_runtime_source_pin_must_match_actual_release_after_image(self):
        config = json.loads((self.stage / 'runtime.json').read_bytes())
        config['source_sha256']['cars_ui.py'] = sha(self.originals['cars_ui.py'])
        raw = encoded(config)
        (self.stage / 'runtime.json').write_bytes(raw)
        self.manifest['runtime_config']['payload_sha256'] = sha(raw)
        with self.assertRaisesRegex(RuntimeError, 'RUNTIME_SOURCE_RELEASE_BINDING_MISMATCH:cars_ui.py'):
            self.load_package()

    def test_current_source_drift_refuses_before_backup(self):
        (self.root / 'cars_ui.py').write_bytes(b'operator_change=True\n')
        tx = self.transaction()
        with self.lease() as lease, self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED:cars_ui.py'):
            tx.backup(lease)
        self.assertFalse(tx.folder.exists())

    def test_backup_captures_uncheckpointed_wal_and_checksums(self):
        self.conn.execute("UPDATE cars SET price=12500,note='WAL commit' WHERE id=8")
        self.conn.commit()
        self.assertGreater((self.root / 'crm.db-wal').stat().st_size, 0)
        tx = self.transaction()
        with self.lease() as lease:
            manifest = tx.backup(lease)
        with closing(sqlite3.connect(tx.folder / manifest['database_file'])) as copied:
            self.assertEqual((12500, 'WAL commit'), copied.execute('SELECT price,note FROM cars').fetchone())
            self.assertEqual([('ok',)], copied.execute('PRAGMA integrity_check').fetchall())
        self.assertEqual(sha((tx.folder / manifest['database_file']).read_bytes()), manifest['database_sha256'])
        for name, item in manifest['files'].items():
            if item['stored']:
                self.assertEqual(sha((self.root / name).read_bytes()), sha((tx.folder / item['stored']).read_bytes()))

    def test_additive_schema_and_atomic_dependency_order(self):
        events = []
        tx = self.transaction(fault=lambda stage, name: events.append((stage, name)))
        with self.lease() as lease:
            tx.backup(lease)
            result = tx.apply(lease)
        self.assertEqual('OFFLINE_CODE_INSTALL_PASS', result['status'])
        self.assertEqual('cars_ui.py', [name for phase, name in events if phase == 'file_replaced'][-1])
        self.assertEqual((8, 12000, 'original'), self.conn.execute('SELECT * FROM cars').fetchone())
        self.assertEqual(self.schema_sha, application_schema(self.conn))
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'ua_delete_intents', 'ua_delete_jobs', 'ua_delete_confirmations'} <= tables)
        self.assertFalse(result['production_restart_verified'])
        config_path = self.root / 'ua_crm_deletion_state/runtime.json'
        self.assertEqual(0, config_path.stat().st_mode & 0o077)
        self.assertEqual(0, config_path.parent.stat().st_mode & 0o077)
        self.assertLess(events.index(('runtime_config_written', 'ua_crm_deletion_state/runtime.json')),
                        events.index(('file_replaced', 'cars_ui.py')))

    def test_partial_install_code_rollback_preserves_new_operator_data(self):
        def fault(phase, name):
            if phase == 'file_replaced' and name == 'publikaciya.py':
                raise RuntimeError('simulated process interruption')
        tx = self.transaction(fault=fault)
        with self.lease() as lease:
            tx.backup(lease)
            with self.assertRaisesRegex(RuntimeError, 'simulated process interruption'):
                tx.apply(lease)
            self.conn.execute("UPDATE cars SET price=14000,note='new operator work' WHERE id=8")
            self.conn.commit()
            result = tx.rollback_code(lease)
        self.assertFalse(result['database_restored'])
        self.assertEqual((14000, 'new operator work'), self.conn.execute('SELECT price,note FROM cars').fetchone())
        for name in ('cars_ui.py', 'publikaciya.py'):
            self.assertEqual(self.originals[name], (self.root / name).read_bytes())
        self.assertFalse((self.root / 'ua_delete_runtime.py').exists())
        self.assertEqual(3, self.conn.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'ua_delete_%' AND type='table'").fetchone()[0])

    def test_rollback_refuses_to_overwrite_newer_code_before_any_effect(self):
        tx = self.transaction()
        with self.lease() as lease:
            tx.backup(lease)
            tx.apply(lease)
            (self.root / 'cars_ui.py').write_bytes(b'operator=True\n')
            before = (self.root / 'publikaciya.py').read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'NEWER_CODE_PRESERVED:cars_ui.py'):
                tx.rollback_code(lease)
            self.assertEqual(before, (self.root / 'publikaciya.py').read_bytes())

    def test_unverified_backup_and_changed_database_block_install(self):
        tx = self.transaction()
        with self.lease() as lease:
            manifest = tx.backup(lease)
            self.conn.execute('UPDATE cars SET price=15000 WHERE id=8')
            self.conn.commit()
            with self.assertRaisesRegex(RuntimeError, 'DATABASE_CHANGED_AFTER_BACKUP'):
                tx.apply(lease)
            self.assertEqual(self.originals['cars_ui.py'], (self.root / 'cars_ui.py').read_bytes())
            (tx.folder / manifest['files']['cars_ui.py']['stored']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError, 'BACKUP_SOURCE_HASH_MISMATCH'):
                tx.rollback_code(lease)

    def test_live_busy_singleton_cannot_be_declared_quiescent(self):
        fd = os.open(self.root / '.start_safe.singleton.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError), self.lease():
                pass
        finally:
            os.close(fd)

    def test_unknown_process_or_changed_lock_inode_refuses(self):
        with self.assertRaisesRegex(RuntimeError, 'UNREVIEWED_ACTIVE_PYTHON_PROCESS'):
            with ExistingLocksLease(self.root, inventory=lambda: [{'pid': 999, 'command_sha256': 'a' * 64}]):
                pass
        with self.lease() as lease:
            path = self.root / '.start_safe.singleton.lock'
            path.unlink()
            path.touch()
            with self.assertRaisesRegex(RuntimeError, 'LOCK_INODE_CHANGED'):
                lease.assert_held()

    def test_asynchronous_shutdown_waits_for_actual_existing_lock(self):
        fd = os.open(self.root / '.start_safe.singleton.lock', os.O_RDWR)
        timer = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            timer = threading.Timer(.03, lambda: fcntl.flock(fd, fcntl.LOCK_UN))
            timer.start()
            with ExistingLocksLease(self.root, inventory=lambda: [], timeout=.5) as lease:
                lease.assert_held()
                self.assertFalse(timer.is_alive())
        finally:
            if timer is not None:
                timer.join()
            os.close(fd)

    def test_public_paths_and_wsgi_are_not_private_install_targets(self):
        for destination in ('video/page.py', '../unsafe.py', '/var/www/www_uaart_com_ua_wsgi.py'):
            self.manifest['files'][0]['destination'] = destination
            with self.assertRaises(RuntimeError):
                self.load_package()

    def test_wsgi_payload_can_be_validated_separately_without_install(self):
        payload = b'application = None\n'
        (self.stage / 'route.py').write_bytes(payload)
        self.manifest['route_patch'] = dict(destination='/var/www/www_uaart_com_ua_wsgi.py',
            before_sha256='b' * 64, payload='route.py', payload_sha256=sha(payload), role='route')
        package = self.load_package()
        self.assertTrue(package.report()['separate_wsgi_payload_validated'])
        self.assertNotIn('/var/www/www_uaart_com_ua_wsgi.py', package.order())

    def test_engine_cannot_target_production(self):
        # Use the fixture as the mocked exact production root; never create or
        # touch the actual /home/Carix directory to prove this boundary.
        with mock.patch('package_install.PRODUCTION_ROOT', self.root):
            with self.assertRaisesRegex(RuntimeError, 'PRODUCTION_LIFECYCLE_NOT_IMPLEMENTED'):
                self.transaction()

    def test_rollback_after_install_restores_entrypoint_and_keeps_config_audit(self):
        tx = self.transaction()
        with self.lease() as lease:
            tx.backup(lease)
            tx.apply(lease)
            config_path = self.root / 'ua_crm_deletion_state/runtime.json'
            config_before = config_path.read_bytes()
            result = tx.rollback_code(lease)
        self.assertEqual('cars_ui.py', result['restored'][0])
        self.assertEqual(config_before, config_path.read_bytes())
        self.assertEqual(self.originals['cars_ui.py'], (self.root / 'cars_ui.py').read_bytes())

    def test_rollback_after_durable_deletion_refuses_old_unguarded_code(self):
        tx = self.transaction()
        with self.lease() as lease:
            tx.backup(lease)
            tx.apply(lease)
            self.conn.execute('''INSERT INTO ua_delete_intents
                (operation_id,car_id,car_code,vin,actor_id,snapshot,snapshot_sha256,
                 expected_snapshot,expected_snapshot_sha256,plan,plan_sha256,backup_sha256,state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                ('operation', 8, 'UA-0002', 'VIN', 123, '{}', 'a'*64, '{}', 'a'*64,
                 '{}', 'a'*64, 'b'*64, 'REQUESTED'))
            self.conn.commit()
            before = (self.root / 'cars_ui.py').read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'FORWARD_RECOVERY_REQUIRED'):
                tx.rollback_code(lease)
            self.assertEqual(before, (self.root / 'cars_ui.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
