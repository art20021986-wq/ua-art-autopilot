import asyncio
import contextlib
import os
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cars_publication_patch import apply_to_candidate, START, END, HELPERS
import test_writer_guard as guard_fixture
from ua_delete_public_guard import DeletedPublicationRefused, vin_key


class HandlerStop(Exception):
    pass


class PublicationWorkerTests(unittest.TestCase):
    setUpClass = classmethod(guard_fixture.WriterGuardTests.setUpClass.__func__)
    fence = guard_fixture.WriterGuardTests.fence
    require = guard_fixture.WriterGuardTests.require
    tombstone = guard_fixture.WriterGuardTests.tombstone

    def setUp(self):
        guard_fixture.WriterGuardTests.setUp(self)
        source = os.environ.get('UA_TEST_CARS_SOURCE')
        if not source:
            raise RuntimeError('UA_TEST_CARS_SOURCE must point to exact reviewed cars_ui.py')
        self.original = Path(source).read_bytes()
        self.candidate = apply_to_candidate(self.original)
        text = self.candidate.decode()
        self.block = text[text.index(START):text.index(END)+len(END)]
        with sqlite3.connect(self.db) as c:
            c.execute('ALTER TABLE cars ADD status TEXT')
            c.execute('ALTER TABLE cars ADD publish_pending INTEGER')
            c.execute('ALTER TABLE cars ADD updated_at TEXT')
            c.execute('ALTER TABLE cars ADD price INTEGER')
            c.execute("UPDATE cars SET published=0,status='kr_ready',publish_pending=0,price=100 WHERE id=3")
        self.audit=[]
        @contextlib.contextmanager
        def connect():
            c=sqlite3.connect(self.db)
            c.row_factory=sqlite3.Row
            try:
                with c:
                    yield c
            finally:
                c.close()
        self.connect=connect
        def card_of(cid):
            with connect() as c:
                row=c.execute('SELECT * FROM cars WHERE id=?',(cid,)).fetchone()
                return dict(row) if row else None
        self.read=card_of
        self.ns={'db':SimpleNamespace(connect=connect,now=lambda:'now',
                      log_action=lambda *args:self.audit.append(args)),
                 'card_of':card_of,'log':SimpleNamespace(exception=lambda *a,**k:None),
                 'S':SimpleNamespace(missing_required=lambda row:[]),
                 'Update':object,'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object),
                 'ApplicationHandlerStop':HandlerStop,
                 'InlineKeyboardButton':lambda text,**kwargs:SimpleNamespace(text=text,**kwargs),
                 'InlineKeyboardMarkup':lambda rows:rows}
        fake_public=SimpleNamespace(publication_fence=lambda **kwargs:self.fence())
        fake_guard=SimpleNamespace(require_current=self.guard.require_current,vin_key=vin_key)
        with patch.dict(sys.modules,{'publication_fence':fake_public,'ua_delete_public_guard':fake_guard}):
            exec(compile(self.block,'<actual-patched-toggle>','exec'),self.ns)
            exec(HELPERS,self.ns)

    def worker(self,publisher):
        return self.ns['_delete_toggle_publication_worker'](3,self.read(3),1,123,publisher)

    def test_worker_refuses_rollback_after_newer_operator_change(self):
        def publish(code):
            self.require()
            self.assertEqual(self.read(3)['published'],1)
            with self.connect() as c:
                c.execute("UPDATE cars SET status='operator_new_stage',price=999 WHERE id=3")
            return False,'publisher validation failed'
        result=self.worker(SimpleNamespace(opublikovat=publish))
        self.assertEqual(result,(False,'publisher validation failed',False))
        row=self.read(3)
        self.assertEqual(row['published'],1)
        self.assertEqual(row['status'],'operator_new_stage')
        self.assertEqual(row['price'],999)
        self.assertEqual([item[5:] for item in self.audit],[(0,1)])

    def test_failed_hide_preserves_concurrent_sale_and_unpublication(self):
        with self.connect() as c:
            c.execute('UPDATE cars SET published=1 WHERE id=3')
        def rebuild():
            self.require()
            self.assertEqual(self.read(3)['published'],0)
            with self.connect() as c:
                c.execute("UPDATE cars SET status='sold',published=0,updated_at='operator_newer' WHERE id=3")
            return False,'catalog failed'
        result=self.ns['_delete_toggle_publication_worker'](
            3,self.read(3),0,123,SimpleNamespace(obnovit_katalog=rebuild))
        self.assertEqual(result,(False,'catalog failed',False))
        row=self.read(3)
        self.assertEqual((row['status'],row['published'],row['updated_at']),('sold',0,'operator_newer'))
        self.assertEqual([item[5:] for item in self.audit],[(1,0)])

    def test_failed_initial_cas_never_rolls_back_another_operators_write(self):
        original=self.ns['_delete_set_published']
        def race(identity,expected,desired,actor_id,**kwargs):
            with self.connect() as c:
                c.execute('UPDATE cars SET published=1 WHERE id=3')
            return original(identity,expected,desired,actor_id,**kwargs)
        self.ns['_delete_set_published']=race
        calls=[]
        result=self.worker(SimpleNamespace(opublikovat=lambda code:calls.append(code)))
        self.assertFalse(result[0])
        self.assertTrue(result[2])
        self.assertEqual(self.read(3)['published'],1)
        self.assertEqual(self.audit,[])
        self.assertEqual(calls,[])

    def test_initial_cas_refuses_concurrent_sale_with_same_published_value(self):
        original=self.ns['_delete_set_published']
        def race(identity,expected,desired,actor_id,**kwargs):
            with self.connect() as c:
                c.execute("UPDATE cars SET status='sold',published=0,updated_at='operator_newer' WHERE id=3")
            return original(identity,expected,desired,actor_id,**kwargs)
        self.ns['_delete_set_published']=race
        calls=[]
        result=self.worker(SimpleNamespace(opublikovat=lambda code:calls.append(code)))
        self.assertFalse(result[0])
        self.assertTrue(result[2])
        row=self.read(3)
        self.assertEqual((row['status'],row['published']),('sold',0))
        self.assertEqual((self.audit,calls),([],[]))

    def test_retired_admission_never_changes_db_or_calls_publisher(self):
        self.tombstone(code='UA-0003',car_id=3,vin='VIN3')
        before=self.read(3)
        calls=[]
        with self.assertRaises(DeletedPublicationRefused):
            self.worker(SimpleNamespace(opublikovat=lambda code:calls.append(code)))
        self.assertEqual(self.read(3),before)
        self.assertEqual(calls,[])
        self.assertEqual(self.audit,[])

    def test_late_rollback_cannot_modify_accepted_deletion_snapshot(self):
        preimage={'published':1,'status':'old','publish_pending':1}
        self.tombstone(code='UA-0003',car_id=3,vin='VIN3')
        before=self.read(3)
        restored=self.ns['_ua083_restore_publish_preimage'](3,preimage,123,
                    expected_written={'published':0},identity=before)
        self.assertFalse(restored)
        self.assertEqual(self.read(3),before)
        self.assertEqual(self.audit,[])

    def test_deletion_waits_until_failed_publish_has_finished_rollback(self):
        started,admitted=threading.Event(),threading.Event()
        seen=[]
        def retire():
            started.set()
            with self.fence():
                seen.append(self.read(3)['published'])
                self.tombstone(code='UA-0003',car_id=3,vin='VIN3')
            admitted.set()
        thread=threading.Thread(target=retire)
        def publish(code):
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(admitted.wait(.05))
            return False,'failed'
        self.assertEqual(self.worker(SimpleNamespace(opublikovat=publish)),(False,'failed',True))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(seen,[0])
        self.assertTrue(admitted.is_set())

    def test_missing_expected_write_refuses_legacy_broad_restore(self):
        before=self.read(3)
        stale={'published':1,'status':'stale stage','publish_pending':1}
        self.assertFalse(self.ns['_ua083_restore_publish_preimage'](3,stale,123))
        self.assertEqual(self.read(3),before)

    def test_telegram_failure_after_success_does_not_undo_publication(self):
        messages=[]
        async def reply(text,**kwargs):
            # User-visible network awaits run after worker released its lease.
            with self.assertRaises(self.fence_module.FenceError):
                self.require()
            messages.append(text)
            if len(messages)==1:
                raise RuntimeError('network failed after commit')
        query=SimpleNamespace(data='car_pub:3',from_user=SimpleNamespace(id=123),
                              message=SimpleNamespace(reply_text=reply))
        async def staff(update):
            return query,{'role':'owner'}
        self.ns.update(_ua099_require_staff=staff,_ua099_card=lambda cid:self.read(cid),
                       _ua099_uid=lambda row:row['auto_number'],
                       _ua_emergency_schedule_spec=lambda code:None)
        publisher=SimpleNamespace(opublikovat=lambda code:(True,'published'))
        with patch.dict(sys.modules,{'publikaciya':publisher}):
            with self.assertRaises(HandlerStop):
                asyncio.run(self.ns['toggle_publish'](SimpleNamespace(callback_query=query),SimpleNamespace()))
        self.assertEqual(self.read(3)['published'],1)
        self.assertEqual(len(self.audit),1)
        self.assertIn('выполнена',messages[-1])
        self.assertNotIn('Выполнен откат',messages[-1])

    def test_composition_preserves_prior_changes_and_binds_target_block(self):
        prior=b'# approved preceding patch\n'+self.original+b'\n# approved following patch\n'
        after=apply_to_candidate(prior)
        self.assertTrue(after.startswith(b'# approved preceding patch\n'))
        self.assertTrue(after.endswith(b'\n# approved following patch\n'))
        changed=self.original.replace(b'    preimage = _ua083_publish_preimage(card)\n',
                                      b'    preimage = _ua083_publish_preimage(card) # changed\n',1)
        with self.assertRaisesRegex(ValueError,'BLOCK_HASH_REQUIRED'):
            apply_to_candidate(changed)
        with self.assertRaisesRegex(ValueError,'UNPATCHED'):
            apply_to_candidate(after)


if __name__=='__main__':
    unittest.main()
