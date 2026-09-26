"""Only Stage3 absent-anchor start and guarded activation; no live credentials."""
import ast
import asyncio
from pathlib import Path
import os
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_binding import BindingV5Tests, binding as B, runtime as R
from test_cars_ui_hook import CarsHookTests, confirmations
from test_v5_runtime import V5RuntimeTests
import patch_cars_ui

class UnconfiguredStartupTests(unittest.TestCase):
    def setUp(self):
        previous=R._crm_activation; R._crm_activation=None
        self.addCleanup(setattr,R,'_crm_activation',previous)
        self.f=BindingV5Tests('runTest');self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
    def app(self,bot_id=123):
        return SimpleNamespace(bot=SimpleNamespace(id=bot_id),bot_data={'unrelated':'preserved'},post_init=None)
    def test_absent_anchor_preserves_existing_application_without_binding_or_jobs(self):
        self.f.anchor.unlink(); app=self.app();before=self.f.db.read_bytes()
        self.assertIsNone(B.bootstrap_if_configured(app,anchor_path=self.f.anchor,test_root=self.f.root))
        self.assertIsNone(app.post_init);self.assertNotIn(R.BINDING_KEY,app.bot_data)
        self.assertEqual(app.bot_data['unrelated'],'preserved')
        self.assertEqual(app.bot_data[R.REGISTRATION_KEY]['state'],'NOT_CONFIGURED')
        self.assertFalse(app.bot_data[R.REGISTRATION_KEY]['worker_jobs_registered'])
        self.assertEqual(self.f.db.read_bytes(),before);self.assertIs(R.activation_available(),False)
        with self.assertRaisesRegex(R.SyncError,'PRICE_SYNC_RUNTIME_NOT_CONFIGURED'):R.require_crm_price_ready()
        with self.assertRaisesRegex(R.SyncError,'PRICE_SYNC_RUNTIME_NOT_CONFIGURED'):R.require_crm_publication_ready()
    def test_existing_invalid_or_broken_symlink_anchor_still_hard_fails(self):
        for mode in ('malformed','directory','broken_symlink'):
            with self.subTest(mode=mode):
                self.f.anchor.unlink(missing_ok=True)
                if mode=='malformed':self.f.anchor.write_text('{');self.f.anchor.chmod(0o600)
                elif mode=='directory':self.f.anchor.mkdir(mode=0o700)
                else:self.f.anchor.symlink_to(self.f.root/'missing-anchor')
                try:
                    with self.assertRaises((B.BindingError,ValueError)):
                        B.bootstrap_if_configured(self.app(),anchor_path=self.f.anchor,test_root=self.f.root)
                    self.assertIs(R.activation_available(),False)
                finally:
                    if self.f.anchor.is_dir() and not self.f.anchor.is_symlink():self.f.anchor.rmdir()
                    else:self.f.anchor.unlink(missing_ok=True)
    def test_real_validated_binding_becomes_ready_only_after_verified_post_init(self):
        app=self.app();calls=[]
        async def previous(app):calls.append(R.activation_available())
        app.post_init=previous
        bound=B.bootstrap_if_configured(app,anchor_path=self.f.anchor,test_root=self.f.root)
        self.assertIsInstance(bound,R.Binding);self.assertIs(R.activation_available(),False)
        asyncio.run(app.post_init(app));self.assertEqual(calls,[False])
        self.assertIs(R.activation_available(),True);R.require_crm_price_ready()
        self.assertFalse(app.bot_data[R.REGISTRATION_KEY]['worker_jobs_registered'])
        wrong=self.app(bot_id=999)
        B.bootstrap_if_configured(wrong,anchor_path=self.f.anchor,test_root=self.f.root)
        with self.assertRaisesRegex(B.BindingError,'RUNNING_CRM_BOT_IDENTITY_MISMATCH'):asyncio.run(wrong.post_init(wrong))
        self.assertIs(R.activation_available(),False)
    def test_readiness_is_pid_bound_and_unregistered_installer_gets_no_runtime_grant(self):
        self.assertIsNone(R.activation_available());R.require_crm_publication_ready()
        with self.assertRaisesRegex(R.SyncError,'PRICE_SYNC_RUNTIME_NOT_CONFIGURED'):R.require_crm_price_ready()
        app=self.app();B.bootstrap_if_configured(app,anchor_path=self.f.anchor,test_root=self.f.root);asyncio.run(app.post_init(app))
        pid=os.getpid()
        with patch.object(R.os,'getpid',return_value=pid+1):
            self.assertIs(R.activation_available(),False)
            with self.assertRaisesRegex(R.SyncError,'PRICE_SYNC_RUNTIME_NOT_CONFIGURED'):R.require_crm_publication_ready()
    def test_actual_generated_register_keeps_base_handlers_but_skips_new_worker_jobs(self):
        source=Path(os.environ['TASK088_CARS_UI_SOURCE']).read_text()
        patched=patch_cars_ui.patch_source(source);tree=ast.parse(patched)
        node=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register'][-1]
        self.f.anchor.unlink();app=self.app();calls=[]
        app.add_handler=lambda *a,**k:calls.append('confirmation_handler')
        def base(application):
            self.assertIs(R.activation_available(),False);calls.append('existing_base_handlers')
        def optional(application,anchor_path):
            self.assertEqual(str(anchor_path),'/home/Carix/.uaart_price_sync_anchor.json')
            return B.bootstrap_if_configured(application,anchor_path=self.f.anchor,test_root=self.f.root)
        ns={'_TASK088_PRICE_SYNC_BASE_REGISTER':base,'_task088_price_confirmation':object(),
            'CallbackQueryHandler':lambda *a,**kw:object()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-generated-register>','exec'),ns)
        with patch.dict(sys.modules,{'uaart_price_sync_runtime':R,'uaart_price_sync_binding':SimpleNamespace(bootstrap_if_configured=optional)}),patch.object(R,'register',side_effect=AssertionError('MUST_NOT_REGISTER_WORKERS')):
            ns['register'](app)
        self.assertEqual(calls,['existing_base_handlers','confirmation_handler']);self.assertNotIn(R.BINDING_KEY,app.bot_data)
    def test_price_and_confirmation_cannot_write_queue_or_data_until_configured(self):
        CarsHookTests.setUpClass();f=CarsHookTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        # An existing pending confirmation remains intact while unconfigured.
        _,answer=f.edit(value='245');proposal=confirmations.get(f.db,answer.confirmation)
        before=tuple(f.db.execute('SELECT * FROM cars').fetchall());audit=tuple(f.db.execute('SELECT * FROM audit').fetchall())
        R.mark_crm_unconfigured(self.app())
        with patch.dict(sys.modules,{'uaart_price_sync_runtime':R}):
            self.assertFalse(f.edit(identity=(700,51,901))[0]);self.assertFalse(f.edit(cid=29,identity=(700,52,902))[0])
            self.assertFalse(f.edit(value='245',identity=(700,53,903))[0]);f.callback(answer,'yes');f.callback(answer,'no')
        self.assertEqual(f.events(),[]);self.assertEqual(tuple(f.db.execute('SELECT * FROM cars').fetchall()),before)
        self.assertEqual(tuple(f.db.execute('SELECT * FROM audit').fetchall()),audit)
        self.assertEqual(confirmations.get(f.db,answer.confirmation),proposal)
        self.assertEqual(f.db.execute('SELECT count(*) FROM '+confirmations.TABLE).fetchone()[0],1)
    def test_direct_or_inherited_worker_cannot_mutate_claims_files_or_send_until_ready(self):
        f=V5RuntimeTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
        event=f.submit();before=f.db.read_bytes()
        files={str(p.relative_to(f.root)):p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
        sent=[]
        async def send_message(**kwargs):sent.append(kwargs);return SimpleNamespace(message_id=1)
        bot=SimpleNamespace(send_message=send_message)
        for mode in ('unconfigured','inherited'):
            with self.subTest(mode=mode):
                R._crm_activation=(os.getpid() if mode=='unconfigured' else os.getpid()-1, mode=='inherited')
                for action in (lambda:f.worker.process_operation(event['event_key']),
                               lambda:f.worker.reconcile_hidden_operation(event['event_key']),
                               f.worker.tick,f.worker.queue_daily,f.worker.queue_daily_unavailable,
                               lambda:f.worker.record_runtime_failure(R.SyncError('TEST_FAILURE')),
                               lambda:asyncio.run(f.worker.deliver_notices(bot))):
                    with self.assertRaisesRegex(R.SyncError,'PRICE_SYNC_RUNTIME_NOT_CONFIGURED'):action()
                self.assertEqual(f.db.read_bytes(),before)
                self.assertEqual({str(p.relative_to(f.root)):p.read_bytes() for p in f.root.rglob('*') if p.is_file()},files)
                self.assertEqual(sent,[])
    def test_registered_callbacks_wait_for_real_bot_post_init(self):
        app=self.app();callbacks=[]
        app.job_queue=SimpleNamespace(get_jobs_by_name=lambda name:[],
            run_repeating=lambda callback,**kw:callbacks.append(callback),
            run_daily=lambda callback,**kw:callbacks.append(callback))
        B.bootstrap_if_configured(app,anchor_path=self.f.anchor,test_root=self.f.root)
        worker=R.register(app)
        self.assertEqual(len(callbacks),2);self.assertIs(R.activation_available(),False)
        self.assertTrue(app.bot_data[R.REGISTRATION_KEY]['worker_jobs_registered'])
        with (patch.object(worker,'tick',side_effect=AssertionError('EARLY_WORKER')),
             patch.object(worker,'queue_daily',side_effect=AssertionError('EARLY_DAILY')),
             patch.object(worker,'deliver_notices',side_effect=AssertionError('EARLY_NOTICE'))):
            for callback in callbacks:asyncio.run(callback(SimpleNamespace(bot=app.bot)))
        asyncio.run(app.post_init(app));self.assertIs(R.activation_available(),True)
        self.assertTrue(app.bot_data[R.REGISTRATION_KEY]['worker_jobs_registered'])

if __name__=='__main__':unittest.main()
