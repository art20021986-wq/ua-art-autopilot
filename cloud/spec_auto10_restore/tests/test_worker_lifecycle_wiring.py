"""Worker recovery/fencing using the actual lifecycle helper in isolated files."""
import builtins
import importlib.util
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'runtime'))
import vin_spec_service as service

spec = importlib.util.spec_from_file_location('worker_lifecycle_fixture', HERE/'test_card_lifecycle.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class WorkerLifecycleWiringTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LifecycleTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.paths = service.MAIN_DB, service.SPEC_DB
        self.addCleanup(self.restore_paths)
        service.MAIN_DB, service.SPEC_DB = self.fixture.guard.DB, self.fixture.root/'worker-spec.db'
        with sqlite3.connect(service.MAIN_DB) as conn:
            for name, kind in (('vin', 'TEXT'), ('marka', 'TEXT'), ('model', 'TEXT'), ('god', 'INTEGER')):
                conn.execute('ALTER TABLE cars ADD COLUMN '+name+' '+kind)
            conn.execute("UPDATE cars SET vin='KNAGN4AD5F5067209',marka='Kia',model='K5',god=2015")
        service.ensure_schema()

    def restore_paths(self):
        service.MAIN_DB, service.SPEC_DB = self.paths

    def ready(self, card):
        return {'status': 'READY', 'facts': [{'field_key': 'length', 'display_value': '4855 мм',
                'label_ru': 'Длина', 'category': 'dimensions', 'unit': 'мм', 'confidence': .95,
                'source_domains': ['auto-data.net'], 'source_urls': ['https://www.auto-data.net/en/fixture']}],
                'sources': {'auto-data.net': {'status': 'PASS'}}}

    def collect(self):
        service.scan_new_vins()
        return service.process_one(enricher=self.ready)

    def crash_delete(self):
        self.fixture.guard.rebuild_catalog = lambda: (_ for _ in ()).throw(KeyboardInterrupt('fixture process loss'))
        with self.assertRaises(KeyboardInterrupt):
            fixtures.lifecycle.delete_card(1, guard=self.fixture.guard)
        self.assertEqual(self.fixture.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('APPLIED',)])

    def job(self, uid='UA-0001'):
        with service.connect_spec(True) as conn:
            return dict(conn.execute('SELECT * FROM vin_spec_jobs WHERE car_uid=? ORDER BY id DESC LIMIT 1', (uid,)).fetchone())

    def test_startup_recovers_interrupted_delete_before_thread_launch(self):
        self.crash_delete()
        with patch.object(service, '_worker', None), patch.object(service.threading, 'Thread') as thread:
            self.assertTrue(service.start_worker(lifecycle_guard=self.fixture.guard))
            thread.return_value.start.assert_called_once()
        self.assertEqual(self.fixture.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('ROLLED_BACK',)])
        self.assertEqual(len(self.fixture.rows()), 2)
        for root in self.fixture.guard.ROOTS:
            self.assertTrue((root/'UA-0001.html').exists())

    def test_sync_recovers_pending_delete_before_selecting_or_publishing_saved_job(self):
        self.collect()
        self.crash_delete()
        def reconcile(card, facts):
            self.assertEqual(card['car_id'], 1)
            self.assertTrue(facts)
            self.assertEqual(self.fixture.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('ROLLED_BACK',)])
            self.assertEqual(len(self.fixture.rows()), 2)
            return {'status': 'PASS', 'detail': 'isolated existing-page fixture'}
        result = service.sync_one(reconciler=reconcile, lifecycle_guard=self.fixture.guard)
        self.assertEqual(result['status'], 'PASS')

    def test_recovery_failure_blocks_cycle_and_startup_before_any_queue_work(self):
        with patch.object(service, 'recover_lifecycle_pending', side_effect=RuntimeError('fixture recovery conflict')):
            with patch.object(service, 'scan_new_vins') as scan, patch.object(service, 'sync_one') as sync:
                with self.assertLogs(service.LOGGER, level='ERROR'):
                    self.assertEqual(service.worker_cycle()['status'], 'ERROR')
                scan.assert_not_called(); sync.assert_not_called()
            with patch.object(service, '_worker', None), patch.object(service.threading, 'Thread') as thread:
                with self.assertLogs(service.LOGGER, level='ERROR'):
                    self.assertFalse(service.start_worker())
                thread.assert_not_called()

    def test_clean_archive_path_never_imports_production_guard(self):
        original_import = builtins.__import__
        def checked(name, *args, **kwargs):
            if name == 'publish_transaction_guard':
                self.fail('clean worker fixture imported production guard')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=checked):
            self.assertEqual(service.recover_lifecycle_pending(), {'status': 'PASS', 'recovered': []})
            self.assertEqual(service.scan_new_vins()['queued'], 2)

    def test_recreated_same_uid_and_vin_with_new_database_id_does_not_inherit_ready_job(self):
        self.collect()
        old = self.job()
        with sqlite3.connect(service.MAIN_DB) as conn:
            conn.execute('UPDATE cars SET id=9 WHERE id=1')
        self.assertEqual(service.scan_new_vins()['queued'], 1)
        new = self.job()
        self.assertEqual(new['id'], old['id'])
        self.assertEqual(new['car_id'], 9)
        self.assertEqual(new['status'], 'PENDING')
        self.assertNotEqual(new['input_hash'], old['input_hash'])
        self.assertEqual(service._visible_facts('UA-0001'), [])
        self.assertEqual(service._process_claimed(old, enricher=lambda _: self.fail('stale identity collected'))['status'], 'STALE_DISCARDED')
        self.assertIsNone(service.sync_one(reconciler=lambda *_: self.fail('old identity published')))

    def test_duplicate_uid_is_excluded_and_both_existing_queues_are_retired(self):
        self.collect()
        facts = service._visible_facts('UA-0001')
        with sqlite3.connect(service.MAIN_DB) as conn:
            conn.execute("INSERT INTO cars(id,auto_number,published,vin,marka,model,god) VALUES(9,'UA-0001',1,'KNAGN4AD5F5067209','Kia','K5',2015)")
        with self.assertLogs(service.LOGGER, level='WARNING'):
            scan = service.scan_new_vins()
        self.assertNotIn('UA-0001', scan['card_uids'])
        self.assertEqual((self.job()['status'], self.job()['site_sync_status']), ('SUPERSEDED', 'SUPERSEDED'))
        self.assertEqual(service._visible_facts('UA-0001'), facts)

    def test_completed_delete_tombstone_blocks_recreated_same_uid_vin_and_database_id(self):
        self.collect()
        before = self.fixture.rows('SELECT * FROM cars WHERE id=1')[0]
        with sqlite3.connect(service.MAIN_DB) as conn:
            columns = [row[1] for row in conn.execute('PRAGMA table_info(cars)')]
        self.assertTrue(fixtures.lifecycle.delete_card(1, guard=self.fixture.guard)[0])
        with sqlite3.connect(service.MAIN_DB) as conn:
            conn.execute('INSERT INTO cars('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', before)
        with self.assertLogs(service.LOGGER, level='WARNING'):
            scan = service.scan_new_vins()
        self.assertNotIn('UA-0001', scan['card_uids'])
        self.assertEqual((self.job()['status'], self.job()['site_sync_status']), ('SUPERSEDED', 'SUPERSEDED'))
        self.assertTrue(all(not (root/'UA-0001.html').exists() for root in self.fixture.guard.ROOTS))
        self.assertFalse(service.retry_card('UA-0001'))


if __name__ == '__main__':
    unittest.main()
