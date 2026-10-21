"""Integration regression tests; no network, real SQLite commits in temp roots."""
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock
import remote_installer as ri
from test_ui_patch import fixture_source

class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name); self.work=self.root/'work'; self.work.mkdir()
        self.source=fixture_source().replace('    return hint\n',
            '    _, cid, field = update.callback_query.data.split(":")\n'
            '    context.user_data["car_wait"] = {"card_id": int(cid), "field": field}\n'
            '    return hint\n')
        (self.root/'cars_ui.py').write_text(self.source)
        self.site=self.root/'site'; self.site.mkdir(); (self.site/'index.html').write_text('unchanged website')
        with sqlite3.connect(self.root/'crm.db') as c:
            c.execute('CREATE TABLE cars (id INTEGER PRIMARY KEY, published INTEGER, price_uah INTEGER, model TEXT)')
            c.executemany('INSERT INTO cars VALUES (?,?,?,?)',[(1,0,20000,'test'),(2,1,50000,'catalogue')])
        patched,_=ri.patch_text(self.source)
        self.plan=dict(source_before_sha256=ri.sha(self.source.encode()),
                       source_after_sha256=ri.sha(patched.encode()),test_car_id=1,protected_paths=[str(self.site)])
        self.identity=dict(task_id=ri.TASK_ID,run_id='123',request_sha256='a'*64,
                           transaction_id='test-123',manifest_sha256='b'*64)
        self.installer=ri.Installer(self.root,self.work,self.identity,self.plan)
        # Exercise installer/database algorithms only; this is explicitly not
        # evidence of running source callbacks or a deployed Telegram bot.
        probe=mock.patch.object(ri,'verify_candidate_runtime',return_value={
            'status':'PASS','proof':'TEST_STUB_ONLY','live_bot_verified':False})
        probe.start(); self.addCleanup(probe.stop)

    def prices(self):
        with sqlite3.connect(self.root/'crm.db') as c:
            return c.execute('SELECT id,price_uah FROM cars ORDER BY id').fetchall()

    def columns(self):
        with sqlite3.connect(self.root/'crm.db') as c: return {r[1] for r in c.execute('PRAGMA table_info(cars)')}

    def test_backup_apply_roundtrip_and_exact_scoped_rollback(self):
        before=self.prices(); backup=self.installer.backup(); digest=backup['backup_manifest_sha256']
        self.assertNotIn('price_georgia',self.columns())
        installed=self.installer.install(digest)
        self.assertEqual(installed['db']['db_commit'],'PASS')
        self.assertEqual(installed['ui_runtime'],'NOT_VERIFIED')
        self.assertIn('price_georgia',self.columns()); self.assertEqual(self.prices(),before)
        verify=self.installer.verify(digest)
        self.assertEqual(verify['ui_callbacks']['status'],'PASS')
        self.assertEqual(verify['ui_runtime'],'NOT_VERIFIED')
        rolled=self.installer.rollback(digest)
        self.assertTrue(rolled['restored_exact']); self.assertEqual(self.prices(),before)
        self.assertNotIn('price_georgia',self.columns())
        self.assertEqual((self.root/'cars_ui.py').read_text(),self.source)
        self.assertEqual((self.site/'index.html').read_text(),'unchanged website')

    def test_protected_drift_refuses_before_schema_change(self):
        digest=self.installer.backup()['backup_manifest_sha256']
        (self.site/'index.html').write_text('external publisher update')
        with self.assertRaisesRegex(ri.InstallError,'PROTECTED_DRIFT'): self.installer.install(digest)
        self.assertNotIn('price_georgia',self.columns())
        self.assertEqual((self.site/'index.html').read_text(),'external publisher update')

    def test_missing_ui_proof_refuses_backup_and_all_live_changes(self):
        with mock.patch.object(ri,'verify_candidate_runtime',return_value={'status':'NOT_VERIFIED'}):
            with self.assertRaisesRegex(ri.InstallError,'CALLBACK_PREFLIGHT'): self.installer.backup()
        self.assertNotIn('price_georgia',self.columns()); self.assertFalse(self.installer.state_path.exists())

    def test_new_owner_ge_value_is_preserved_during_rollback(self):
        digest=self.installer.backup()['backup_manifest_sha256']; self.installer.install(digest)
        with sqlite3.connect(self.root/'crm.db') as c: c.execute('UPDATE cars SET price_georgia=17000 WHERE id=1')
        with self.assertRaisesRegex(ri.InstallError,'PRESERVE_NEW_GE_VALUES'): self.installer.rollback(digest)
        with sqlite3.connect(self.root/'crm.db') as c:
            self.assertEqual(c.execute('SELECT price_georgia FROM cars WHERE id=1').fetchone(),(17000,))

    def test_source_install_failure_rolls_back_only_own_changes(self):
        digest=self.installer.backup()['backup_manifest_sha256']
        original_atomic=ri.atomic
        def fail_source(path,data,mode=0o600):
            if path==self.root/'cars_ui.py': raise OSError('injected source install failure')
            return original_atomic(path,data,mode)
        with mock.patch.object(ri,'atomic',side_effect=fail_source):
            with self.assertRaisesRegex(OSError,'injected source'): self.installer.install(digest)
        self.assertEqual((self.root/'cars_ui.py').read_text(),self.source)
        self.assertNotIn('price_georgia',self.columns())
        self.assertEqual(self.prices(),[(1,20000),(2,50000)])

    def test_unpinned_plan_cannot_start(self):
        with self.assertRaisesRegex(ri.InstallError,'PINNED_PLAN_REQUIRED'):
            ri.Installer(self.root,self.work,self.identity,{})

    def test_missing_measurement_is_not_a_pass(self):
        with self.assertRaisesRegex(ri.InstallError,'MEASUREMENTS_INCOMPLETE'):
            ri.Installer.normalized_db({'status':'PASS','directions':{'price_uah':{},'price_georgia':{}}})

    def test_real_target_cannot_use_stub_as_live_acceptance(self):
        digest=self.installer.backup()['backup_manifest_sha256']
        with mock.patch.object(ri,'ROOT',self.root):
            with self.assertRaisesRegex(ri.InstallError,'LIVE_BOT_ACCEPTANCE_NOT_CONFIGURED'):
                self.installer.install(digest)
        self.assertNotIn('price_georgia',self.columns())
        self.assertEqual((self.root/'cars_ui.py').read_text(),self.source)

if __name__=='__main__': unittest.main()
