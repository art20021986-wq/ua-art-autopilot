"""Meaningful local transaction/recovery checks. No provider/production access."""
from __future__ import annotations
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import remote_stage_a as worker
import publication_fence
import visibility_lifecycle as visibility
import ua_site_counters as counters

PACKAGE = Path(__file__).parent.resolve()
CAPTURE = Path(__file__).parent / 'fixtures'


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(worker, 'ROOT', self.root)
        self.root_patch.start()
        self.process_patch = patch.object(worker, 'process_inventory', return_value=[])
        self.process_patch.start()
        self.fence_patch = patch.object(publication_fence, 'publication_fence',
            side_effect=lambda **kwargs: publication_fence.PublicationFence(
                lock_path=self.root / '.ua_art_publish_transaction.lock', _test_only_path=True))
        self.fence_patch.start()
        for name in ['site', 'video', 'rezerv_publikacii']:
            (self.root / name).mkdir()
        for name in ['.start_safe.singleton.lock', '.ua_art_publish_transaction.lock']:
            (self.root / name).write_bytes(b'')
        for folder in ['site', 'video']:
            for name in ['index.html', 'katalog.html']:
                shutil.copyfile(CAPTURE / folder / name, self.root / folder / name)
            (self.root / folder / 'UA-0002.html').write_text('<html>WDD2452322J561014</html>')
            (self.root / folder / 'UA-0002-diag.html').write_text('<html>diagnostic</html>')
            (self.root / folder / 'UA-0002-abcdef.html').write_text('<html>old alias</html>')
            (self.root / folder / 'UA-0003.html').write_text('<html>Protected other listing</html>')
        self.sources = {}
        (self.root / 'video/sitemap.xml').write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '<url><loc>https://www.uaart.com.ua/video/UA-0002.html</loc></url>\n'
            '<url><loc>https://www.uaart.com.ua/video/UA-0003.html</loc></url>\n</urlset>')
        for name in ['db.py', 'cars_ui.py', 'publikaciya.py', 'stranica.py', 'start_safe.py', 'run_all.py']:
            data = ('# fixture source: ' + name).encode()
            (self.root / name).write_bytes(data)
            self.sources[name] = worker.sha(data)
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,publish_pending INTEGER,price_uah REAL,price_georgia REAL)')
            conn.execute("INSERT INTO cars VALUES(9,'UA-0003','OTHER',1,0,100,50)")
            conn.execute('CREATE TABLE media(id INTEGER PRIMARY KEY,car_id INTEGER,file_id TEXT)')
            conn.execute("INSERT INTO media VALUES(1,9,'protected-photo')")
            conn.execute('CREATE TABLE outbox(id INTEGER PRIMARY KEY,state TEXT)')
            conn.execute('CREATE TABLE audit(actor_id INTEGER, action TEXT, entity_type TEXT,entity_id INTEGER,old_value TEXT,created_at TEXT)')
            conn.execute("INSERT INTO audit VALUES(123,'card_delete','cars',8,'UA-0002','2026-09-20T15:51:00Z')")
        self.plan = self.make_plan()

    def tearDown(self):
        self.fence_patch.stop(); self.process_patch.stop(); self.root_patch.stop(); self.temp.cleanup()

    def make_plan(self):
        paths = [self.root / folder / name for folder in ['site', 'video'] for name in
                 ['index.html', 'katalog.html', 'UA-0002.html', 'UA-0002-diag.html', 'UA-0002-abcdef.html']]
        paths.append(self.root / 'video/sitemap.xml')
        return {'contract': worker.CONTRACT, 'version': 1, 'root': str(self.root), 'alwayson_id': 266084,
                'target': {'id': 8, 'auto_number': 'UA-0002', 'vin': worker.VIN},
                'nonce': 'fixture-nonce-001',
                'backup_dir': str(self.root / 'rezerv_publikacii' / 'UA0002-delete-fixture-nonce-001'),
                'package_sha256': {name: worker.sha((PACKAGE / name).read_bytes()) for name in worker.PACKAGE},
                'source_sha256': self.sources,
                'database_state_sha256': worker.sha(worker.encoded(worker.db_state())),
                'writers': {'reviewed': True, 'provider_snapshot_sha256': 'a'*64,
                            'allowed_python_cmdline_sha256': []},
                'home_modes': {'site/index.html': 'LEGACY_TILES', 'video/index.html': 'MODERN_COUNTERS'},
                'sitemaps': ['video/sitemap.xml'],
                'shared_surfaces': [{'path': folder + '/' + name, 'kind': kind}
                                    for folder in ['site', 'video'] for name, kind in
                                    [('index.html', 'HOME'), ('katalog.html', 'CATALOG')]],
                'public_preimage': {str(path.relative_to(self.root)): worker.fingerprint(path) for path in paths}}

    def transaction(self):
        return worker.Transaction(self.plan, worker.sha(worker.encoded(self.plan) + b'\n'), PACKAGE)

    def backup(self):
        tx = self.transaction()
        result = tx.execute('backup')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(worker.db_state(), worker.db_state(tx.backup / 'crm.snapshot.db'))
        return tx

    def assert_retired(self):
        self.assertNotIn('UA-0002', (self.root / 'video/sitemap.xml').read_text())
        self.assertIn('UA-0003', (self.root / 'video/sitemap.xml').read_text())
        for folder in ['site', 'video']:
            self.assertFalse(list((self.root / folder).glob('UA-0002*.html')))
            source = (self.root / folder / 'katalog.html').read_text()
            self.assertFalse(visibility.listing_present(source, 'UA-0002'))
            records, counts = counters.catalog_snapshot(source)
            original, _ = counters.catalog_snapshot((CAPTURE / folder / 'katalog.html').read_text())
            self.assertEqual(records, {key: value for key, value in original.items() if key != 'UA-0002'})
            self.assertEqual(counts['all'], len(original) - ('UA-0002' in original))
            self.assertEqual((self.root / folder / 'UA-0003.html').read_text(), '<html>Protected other listing</html>')

    def test_complete_and_idempotent_recovery(self):
        tx = self.backup()
        before = worker.db_state()
        result = tx.execute('install_verify')
        self.assertTrue(result['post_check_pass'])
        self.assertEqual(before, worker.db_state())
        self.assert_retired()
        # Fresh constructor after aliases were deleted must retain their binding.
        self.assertEqual(self.transaction().execute('recover')['status'], 'PASS')
        self.assert_retired()

    def test_resume_after_first_shared_write(self):
        tx = self.backup()
        original = visibility.atomic_bytes
        count = [0]
        def interrupted(path, data, mode, **kwargs):
            original(path, data, mode, **kwargs)
            if kwargs.get('forward', True):
                count[0] += 1
                if count[0] == 1:
                    raise RuntimeError('simulated process interruption')
        with patch.object(visibility, 'atomic_bytes', side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                tx.execute('install_verify')
        self.assertEqual(self.transaction().execute('recover')['status'], 'PASS')
        self.assert_retired()

    def test_resume_after_first_unlink(self):
        tx = self.backup()
        original = worker.sync_directory
        def interrupted(path):
            original(path)
            if Path(path) in {self.root / 'video', self.root / 'site'}:
                raise RuntimeError('simulated interruption after unlink')
        with patch.object(worker, 'sync_directory', side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                tx.execute('install_verify')
        self.assertEqual(self.transaction().execute('recover')['status'], 'PASS')
        self.assert_retired()

    def test_newer_operator_database_change_never_overwritten(self):
        tx = self.backup()
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute('UPDATE cars SET price_georgia=999 WHERE id=9')
        before = tx.public()
        with self.assertRaisesRegex(worker.Stop, 'DATABASE_STATE_DRIFT'):
            tx.execute('install_verify')
        self.assertEqual(before, tx.public())
        with sqlite3.connect(self.root / 'crm.db') as conn:
            self.assertEqual(conn.execute('SELECT price_georgia FROM cars WHERE id=9').fetchone()[0], 999)

    def test_foreign_list_change_during_recovery_preserved(self):
        tx = self.backup()
        original = visibility.atomic_bytes
        def interrupted(path, data, mode, **kwargs):
            original(path, data, mode, **kwargs)
            if kwargs.get('forward', True):
                raise RuntimeError('interruption')
        with patch.object(visibility, 'atomic_bytes', side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                tx.execute('install_verify')
        path = self.root / 'site' / 'katalog.html'
        changed = path.read_bytes().replace(b'</html>', b'<!-- NEW OPERATOR EDIT --></html>')
        path.write_bytes(changed)
        with self.assertRaisesRegex(visibility.VisibilityError, 'NEWER_PUBLIC_LIST_PRESERVED'):
            self.transaction().execute('recover')
        self.assertEqual(path.read_bytes(), changed)

    def test_late_alias_is_not_missed(self):
        tx = self.transaction()
        (self.root / 'site' / 'UA-0002-123456.html').write_text('new route')
        with self.assertRaisesRegex(worker.Stop, 'PUBLIC_ROUTE_SET_DRIFT'):
            tx.execute('backup')
        self.assertFalse(tx.backup.exists())

    def test_corrupt_backup_blocks_all_mutation(self):
        tx = self.backup()
        manifest = tx.manifest()
        stored = next(item['stored'] for item in manifest['files'].values() if item['exists'])
        (tx.backup / stored).write_bytes(b'corrupt')
        before = tx.public()
        with self.assertRaises(Exception):
            tx.execute('install_verify')
        self.assertEqual(before, tx.public())

    def test_published_target_requires_separate_review(self):
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute('INSERT INTO cars VALUES(?,?,?,?,?,?,?)', (8, 'UA-0002', worker.VIN, 1, 0, 1, 2))
        with self.assertRaisesRegex(worker.Stop, 'TARGET_ROW_PRESENT_STAGE_B_TOMBSTONE_REQUIRED'):
            self.transaction().execute('backup')

    def test_wrong_historical_id_is_never_deleted(self):
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute("INSERT INTO cars VALUES(8,'UA-0099','UNRELATED',0,0,1,2)")
        with self.assertRaisesRegex(worker.Stop, 'TARGET_IDENTITY_COLLISION'):
            self.transaction().execute('backup')

    def test_hidden_row_also_requires_stage_b_tombstone(self):
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute('INSERT INTO cars VALUES(?,?,?,?,?,?,?)', (8, 'UA-0002', worker.VIN, 0, 0, 1, 2))
        with self.assertRaisesRegex(worker.Stop, 'TARGET_ROW_PRESENT_STAGE_B_TOMBSTONE_REQUIRED'):
            self.transaction().execute('backup')

    def test_absent_row_without_actual_delete_event_is_not_enough(self):
        with sqlite3.connect(self.root / 'crm.db') as conn:
            conn.execute('DELETE FROM audit')
        with self.assertRaisesRegex(worker.Stop, 'TARGET_DELETE_AUDIT_EVENT_REQUIRED'):
            self.transaction().execute('backup')

    def test_hash_bound_page_with_wrong_vin_is_rejected(self):
        path = self.root / 'video' / 'UA-0002.html'
        path.write_text('<html>Different vehicle</html>')
        self.plan['public_preimage']['video/UA-0002.html'] = worker.fingerprint(path)
        with self.assertRaisesRegex(worker.Stop, 'HISTORICAL_PUBLIC_VIN_EVIDENCE_REQUIRED'):
            self.transaction().execute('backup')


if __name__ == '__main__':
    unittest.main(verbosity=2)
