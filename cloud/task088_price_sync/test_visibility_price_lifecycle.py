"""Visibility lifecycle tests: isolated SQLite and real temporary public files."""
import contextlib
from dataclasses import replace
import re
import sqlite3
import unittest
from unittest.mock import patch
from test_v5_runtime import V5RuntimeTests, Crash, R, O
import patch_guard

class VisibilityPriceTests(unittest.TestCase):
    def setUp(self):
        self.f = V5RuntimeTests('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.configure()
    def configure(self):
        self.f.binding=replace(self.f.binding,resolve_identity=self.identity,verify_hidden=self.hidden)
        self.f.worker=R.V5Worker(self.f.binding)
    def identity(self,car):
        return {k:self.f.row(car)[k] for k in ('id','auto_number','vin','published')}
    def hidden(self,event,row):
        code=row['auto_number']
        if code and (self.f.cards[row['id']].exists() or code in self.f.catalog.read_text() or code in self.f.home.read_text()):
            raise R.SyncError('TEST_RETIRED_VIEWS_REQUIRED')
        facts=dict(car_id=row['id'],published=0,row_sha256=R.digest(R.json_bytes(row)),public_projection='NOT_APPLICABLE',
                   retired_public_views_verified=True,verification_scope='ISOLATED_LOCAL_FILE_ABSENCE')
        return dict(facts,visibility_receipt_sha256=R.digest(R.json_bytes(facts)))
    def retire(self,incomplete=False):
        with sqlite3.connect(self.f.db) as conn:
            conn.execute('UPDATE cars SET published=0 WHERE id=1')
            if incomplete: conn.execute('UPDATE cars SET auto_number=NULL,vin=NULL,price_uah=NULL,price_georgia=NULL WHERE id=1')
        self.f.cards[1].unlink(missing_ok=True)
        self.f.catalog.write_text(re.sub(r'<article>.*?UA-0001\.html.*?</article>','',self.f.catalog.read_text(),count=1))
    def guard(self):
        ns=dict(contextlib=contextlib,sqlite3=sqlite3,DB=self.f.db,PublishError=R.SyncError)
        exec(patch_guard.HELPER,ns); return ns['_task088_price_quiescence']
    def test_incomplete_draft_ge_ua_empty_ge_fifo_without_publication(self):
        self.retire(True)
        before=tuple(p.read_bytes() for p in (self.f.catalog,self.f.home,self.f.cards[2]))
        for field,value in [('price_georgia',8000),('price_uah',15000),('price_georgia',None)]:
            event=self.f.submit(field=field,value=value); result=self.f.worker.process_operation(event['event_key'])
            self.assertEqual(self.f.event(event['event_key'])['state'],'COMPLETED',result)
            proof=self.f.audit(event['event_key'],'DATA_VERIFIED')['details']
            self.assertEqual(proof['public_projection'],'NOT_APPLICABLE'); self.assertEqual(proof['site_verification'],'NOT_APPLICABLE')
            self.assertIsNone(self.f.audit(event['event_key'],'SITE_PUBLISHED')); self.assertIsNone(self.f.audit(event['event_key'],'VERIFIED'))
        self.assertEqual((self.f.row()['price_uah'],self.f.row()['price_georgia']),(15000,None))
        self.assertEqual(before,tuple(p.read_bytes() for p in (self.f.catalog,self.f.home,self.f.cards[2])))
        self.assertFalse(self.f.cards[1].exists())
        with self.guard()(): pass
    def test_public_complete_then_draft_edit_allows_rebuild_and_keeps_history(self):
        first=self.f.submit(value=10000); self.assertEqual(self.f.worker.process_operation(first['event_key'])['state'],'COMPLETED')
        old=self.f.audit(first['event_key'],'VERIFIED'); self.retire()
        second=self.f.submit(value=12000); result=self.f.worker.process_operation(second['event_key'])
        self.assertEqual(self.f.event(second['event_key'])['state'],'COMPLETED',result)
        self.assertEqual(self.f.audit(first['event_key'],'VERIFIED'),old)
        with self.guard()(): pass
        with sqlite3.connect(self.f.db) as conn: conn.execute('UPDATE cars SET price_georgia=12500 WHERE id=1')
        with self.assertRaisesRegex(R.SyncError,'UNTRACKED_CRM_PRICE_CHANGE'):
            with self.guard()(): pass
    def test_withdrawal_at_every_saved_checkpoint_without_price_replay(self):
        original_fixture=self.f
        for checkpoint in ('QUEUED','CLAIMED','DB_COMMITTED','SITE_PUBLISHED','VERIFIED'):
            with self.subTest(checkpoint=checkpoint):
                self.f=V5RuntimeTests('runTest'); self.f.setUp(); self.configure(); f=self.f
                try:
                    event=f.submit(value=14000)
                    if checkpoint=='CLAIMED':
                        with sqlite3.connect(f.db) as conn:
                            conn.execute('BEGIN IMMEDIATE'); O.claim_operation(conn,event_key=event['event_key'],nonce='e'*64,now_ms=f.now)
                    elif checkpoint not in ('QUEUED','CLAIMED'):
                        method={'DB_COMMITTED':'_commit_selected_price','SITE_PUBLISHED':'_publish','VERIFIED':'_verify'}[checkpoint]
                        original=getattr(f.worker,method)
                        def crash(*args): original(*args); raise Crash()
                        with patch.object(f.worker,method,crash),self.assertRaises(Crash): f.worker.process_operation(event['event_key'])
                    self.assertEqual(f.event(event['event_key'])['state'],checkpoint); self.retire()
                    result=R.V5Worker(f.binding).process_operation(event['event_key'])
                    self.assertEqual(f.event(event['event_key'])['state'],'COMPLETED',result)
                    with sqlite3.connect(f.db) as conn: self.assertEqual(conn.execute('SELECT count(*) FROM audit').fetchone()[0],1)
                    self.assertEqual(f.row()['price_georgia'],14000); self.assertFalse(f.cards[1].exists())
                    with self.guard()(): pass
                finally: f.doCleanups(); self.f=original_fixture
    def test_stale_public_files_cannot_receive_false_hidden_completion(self):
        event=self.f.submit(value=14000)
        with sqlite3.connect(self.f.db) as conn: conn.execute('UPDATE cars SET published=0 WHERE id=1')
        self.f.worker.process_operation(event['event_key']); actual=self.f.event(event['event_key'])
        self.assertEqual(actual['state'],'DB_COMMITTED'); self.assertEqual(actual['blocked'],1)
        self.assertEqual(actual['last_error'],'TEST_RETIRED_VIEWS_REQUIRED'); self.assertIsNone(self.f.audit(event['event_key'],'DATA_VERIFIED'))
    def test_hidden_completion_rechecks_authority_expiry_after_file_observation(self):
        self.retire(); event=self.f.submit(value=14000); calls=[]
        def hidden(event,row):
            proof=self.hidden(event,row); calls.append(1)
            if len(calls)==2: self.f.now+=40000
            return proof
        worker=R.V5Worker(replace(self.f.binding,verify_hidden=hidden))
        worker.process_operation(event['event_key']); actual=self.f.event(event['event_key'])
        self.assertEqual(actual['state'],'DB_COMMITTED')
        self.assertEqual(actual['last_error'],'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
        self.assertIsNone(self.f.audit(event['event_key'],'DATA_VERIFIED'))
        self.assertIsNone(self.f.audit(event['event_key'],'COMPLETED'))
        self.assertEqual(self.f.row()['price_georgia'],14000)

    def test_blocked_old_public_view_reconciles_same_operation_after_actual_retirement(self):
        event=self.f.submit(value=14000)
        with sqlite3.connect(self.f.db) as conn: conn.execute('UPDATE cars SET published=0 WHERE id=1')
        self.f.worker.process_operation(event['event_key']); blocked=self.f.event(event['event_key'])
        self.assertEqual(blocked['blocked'],1)
        # A repeated ordinary message does not rewrite failure history.
        self.assertTrue(self.f.worker.process_operation(event['event_key'])['blocked'])
        self.retire()
        result=self.f.worker.reconcile_hidden_operation(event['event_key'])
        self.assertEqual(result['state'],'COMPLETED',result)
        completed=self.f.event(event['event_key'])
        self.assertEqual(completed['claim_nonce'],blocked['claim_nonce'])
        self.assertEqual(completed['db_committed_ms'],blocked['db_committed_ms'])
        self.assertIsNotNone(self.f.audit(event['event_key'],'HIDDEN_RECOVERY_VERIFIED'))
        with sqlite3.connect(self.f.db) as conn: self.assertEqual(conn.execute('SELECT count(*) FROM audit').fetchone()[0],1)
        with self.guard()(): pass

    def test_newer_untracked_price_survives_and_gets_bounded_diagnosis(self):
        event=self.f.submit(value=14000); original=self.f.worker._commit_selected_price
        def crash(*args): original(*args); raise Crash()
        with patch.object(self.f.worker,'_commit_selected_price',crash),self.assertRaises(Crash): self.f.worker.process_operation(event['event_key'])
        self.retire()
        with sqlite3.connect(self.f.db) as conn: conn.execute('UPDATE cars SET price_georgia=19000 WHERE id=1')
        self.f.worker.process_operation(event['event_key']); actual=self.f.event(event['event_key'])
        self.assertEqual(actual['state'],'DB_COMMITTED'); self.assertEqual(actual['blocked'],1)
        self.assertEqual(actual['last_error'],'V5_NEWER_PRICE_PRESERVED_RECONCILIATION_REQUIRED')
        self.assertEqual(self.f.worker.tick(),{'processed':[]}); self.assertEqual(self.f.row()['price_georgia'],19000)
    def test_public_temp_fsync_expiry_blocks_replace_and_fresh_resume_preserves_db_commit(self):
        event=self.f.submit(value=14000); before=self.f.cards[1].read_bytes(),self.f.catalog.read_bytes()
        original_write=R._atomic_write; original_fsync=R.os.fsync; active=[]; expired=[]
        def atomic(path,data,*args,**kwargs):
            if path==self.f.cards[1]: active.append(True)
            try: return original_write(path,data,*args,**kwargs)
            finally:
                if path==self.f.cards[1]: active.pop()
        def fsync(fd):
            result=original_fsync(fd)
            if active and not expired:
                expired.append(True); self.f.now+=40000
            return result
        with patch.object(R,'_atomic_write',atomic),patch.object(R.os,'fsync',fsync):
            self.f.worker.process_operation(event['event_key'])
        stalled=self.f.event(event['event_key'])
        self.assertEqual(stalled['state'],'DB_COMMITTED')
        self.assertEqual(stalled['last_error'],'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
        self.assertEqual(before,(self.f.cards[1].read_bytes(),self.f.catalog.read_bytes()))
        self.assertIsNone(self.f.audit(event['event_key'],'SITE_PUBLISHED'))
        self.f.now=stalled['next_attempt_ms']
        resumed=R.V5Worker(self.f.binding).process_operation(event['event_key'])
        self.assertEqual(resumed['state'],'COMPLETED',resumed)
        self.assertEqual(self.f.event(event['event_key'])['claim_nonce'],stalled['claim_nonce'])
        with sqlite3.connect(self.f.db) as conn: self.assertEqual(conn.execute('SELECT count(*) FROM audit').fetchone()[0],1)

    def test_expiry_after_last_replace_does_not_commit_site_checkpoint(self):
        event=self.f.submit(value=14000); original=R._atomic_write; expired=[]
        def atomic(path,data,*args,**kwargs):
            result=original(path,data,*args,**kwargs)
            if path==self.f.catalog and not expired:
                expired.append(True); self.f.now+=40000
            return result
        with patch.object(R,'_atomic_write',atomic): self.f.worker.process_operation(event['event_key'])
        stalled=self.f.event(event['event_key'])
        self.assertEqual(stalled['state'],'DB_COMMITTED')
        self.assertEqual(stalled['last_error'],'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
        self.assertIsNone(self.f.audit(event['event_key'],'SITE_PUBLISHED'))
        self.f.now=stalled['next_attempt_ms']
        # Existing desired fragments are reconciled, not blindly rewritten.
        def no_public_replace(path,data,*args,**kwargs):
            self.assertNotIn(path,(self.f.cards[1],self.f.catalog))
            return original(path,data,*args,**kwargs)
        with patch.object(R,'_atomic_write',no_public_replace):
            result=R.V5Worker(self.f.binding).process_operation(event['event_key'])
        self.assertEqual(result['state'],'COMPLETED',result)
        with sqlite3.connect(self.f.db) as conn: self.assertEqual(conn.execute('SELECT count(*) FROM audit').fetchone()[0],1)

    def test_site_checkpoint_audit_work_cannot_commit_after_authority_expiry(self):
        event=self.f.submit(value=14000); original=O.audit_operation
        def audit(conn,key,fact,payload,now):
            result=original(conn,key,fact,payload,now)
            if fact=='SITE_PUBLISHED': self.f.now+=40000
            return result
        with patch.object(O,'audit_operation',audit): self.f.worker.process_operation(event['event_key'])
        stalled=self.f.event(event['event_key'])
        self.assertEqual(stalled['state'],'DB_COMMITTED')
        self.assertEqual(stalled['last_error'],'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
        self.assertIsNone(self.f.audit(event['event_key'],'SITE_PUBLISHED'))
        self.assertEqual(self.f.row()['price_georgia'],14000)

    def test_public_switch_reserves_database_against_visibility_race(self):
        event=self.f.submit(value=14000); attempts=[]; original=R._atomic_write
        def atomic(path,data,*args,**kwargs):
            if path in (self.f.cards[1],self.f.catalog):
                with sqlite3.connect(self.f.db,timeout=0) as conn:
                    with self.assertRaises(sqlite3.OperationalError): conn.execute('UPDATE cars SET published=0 WHERE id=1')
                attempts.append(str(path))
            return original(path,data,*args,**kwargs)
        with patch.object(R,'_atomic_write',atomic): result=self.f.worker.process_operation(event['event_key'])
        self.assertEqual(self.f.event(event['event_key'])['state'],'COMPLETED',result)
        self.assertEqual(len(attempts),2); self.assertEqual(self.f.row()['published'],1)
    def test_completed_draft_replay_after_identity_assignment_does_not_write(self):
        self.retire(True); event=self.f.submit(value=8000)
        self.assertEqual(self.f.worker.process_operation(event['event_key'])['state'],'COMPLETED'); old=self.f.event(event['event_key'])
        with sqlite3.connect(self.f.db) as conn: conn.execute("UPDATE cars SET auto_number='UA-0001',vin='VIN0001',published=1,price_uah=15000,price_georgia=19000 WHERE id=1")
        self.assertEqual(self.f.submit(value=8000,key=event['event_key']),old)
        self.assertTrue(self.f.worker.process_operation(event['event_key'])['replay']); self.assertEqual(self.f.row()['price_georgia'],19000)
        with sqlite3.connect(self.f.db) as conn: self.assertEqual(conn.execute('SELECT count(*) FROM audit').fetchone()[0],1)
    def test_blank_draft_identity_assigned_before_commit_still_has_valid_rebuild_proof(self):
        self.retire(True); event=self.f.submit(value=8000)
        with sqlite3.connect(self.f.db) as conn: conn.execute("UPDATE cars SET auto_number='UA-0001',vin='VIN0001' WHERE id=1")
        result=self.f.worker.process_operation(event['event_key'])
        self.assertEqual(self.f.event(event['event_key'])['state'],'COMPLETED',result)
        with self.guard()(): pass

if __name__=='__main__':unittest.main()
