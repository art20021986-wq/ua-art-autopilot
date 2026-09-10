"""Actual outbox, SQLite, rendering and local files; synthetic route authority/HTTP."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from cloud.spec_rebuild10 import bootstrap, crm_bridge, render
from cloud.spec_rebuild10.store import SpecStore
from cloud.spec_rebuild10.sync import SpecSync, SyncOutbox
from cloud.spec_rebuild10.tests.test_render import page, UID, VIN


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.crm=self.root/'crm.db'; self.spec=self.root/'spec.db'; self.outbox=self.root/'sync.db'
        db=sqlite3.connect(self.crm)
        db.execute('CREATE TABLE cars(id INTEGER, auto_number TEXT, vin TEXT, brand TEXT, model TEXT, year TEXT,published INTEGER,price TEXT)')
        db.execute('INSERT INTO cars VALUES(1,?,?,?,?,?,?,?)',(UID,VIN,'Kia','K5','2017',1,'10000'))
        db.commit();db.close()
        self.rows=bootstrap.CrmRows(self.crm)
        with SpecStore(self.spec) as store:
            crm_bridge.CrmBridge(store).saved(self.rows(UID))
            store.set_manual_fact(UID,{'key':'length','value':'4900','unit':'mm'})
            self.old_facts=store.get_facts(UID)
            vehicle=store.get_vehicle(UID)
            receipt={'uid':UID,'revision':vehicle['revision'],'identity_hash':vehicle['identity_hash'],
                'facts_digest':store.facts_digest(UID),'receipt_id':'SYNTHETIC-initial-readback','status':'PASS',
                'route_id':'SYNTHETIC-installed16','verified_at':'2026-09-09T00:00:00Z',
                'page_url':'https://www.uaart.com.ua/video/'+UID+'.html',
                'specification_visible':True,'single_vin':True,'shell_preserved':True}
            store.mark_publication_verified(UID,vehicle['revision'],receipt)
        self.old_html=render.compose_page(page(),UID,self.old_facts).encode()
        for folder in ('video','site'):
            path=self.root/folder; path.mkdir()
            (path/(UID+'.html')).write_bytes(self.old_html)
            (path/(UID+'-diag.html')).write_bytes(b'<html>Unchanged diagnostics</html>')
            (path/'katalog.html').write_text('<a href="'+UID+'.html">Car</a>')
        self.lock=threading.RLock();self.writes=[];self.authorizations=[]
        self.guard=SimpleNamespace(_exclusive_lock=self.exclusive,_atomic=self.atomic)
        self.runtime=SimpleNamespace(root=self.root,guard=self.guard,_pins=lambda:None)
        self.service=SpecSync(self.spec,self.rows,self.runtime,self.outbox,
            authorize_sync=self.authorize,transport=self.transport)
        self.accept_more()

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def exclusive(self):
        with self.lock:
            yield

    def authorize(self,plan,phase):
        self.authorizations.append((plan,phase))
        self.assertEqual(plan['scope'],'EXISTING_PUBLISHED_SPEC_REGION_ONLY')
        copy=dict(plan);value=copy.pop('plan_sha256')
        self.assertEqual(bootstrap.digest(copy),value)
        self.assertFalse(plan['first_publication'])
        return True  # Explicitly synthetic controller, never production evidence.

    def atomic(self,path,data,mode=None):
        with SpecStore(self.spec) as store:
            facts=store.get_facts(UID)
        render.validate_page(data.decode(),UID,facts,previous=path.read_text())
        self.writes.append(str(path));path.write_bytes(data)

    def transport(self,url,**limits):
        self.assertEqual(limits,{'timeout_seconds':15,'max_bytes':bootstrap.MAX_FILE})
        path=self.root/urlsplit(url).path.lstrip('/')
        return bootstrap.HttpReadback(url,200,path.read_bytes())

    def accept_more(self):
        with SpecStore(self.spec) as store:
            store.set_manual_fact(UID,{'key':'width','value':'1860','unit':'mm'})

    def update(self,**values):
        db=sqlite3.connect(self.crm)
        db.execute('UPDATE cars SET '+','.join(k+'=?' for k in values)+' WHERE id=1',tuple(values.values()))
        db.commit();db.close()

    def primary(self,folder='video'):
        return self.root/folder/(UID+'.html')

    def states(self):
        db=sqlite3.connect(self.outbox)
        result=db.execute('SELECT state FROM spec_sync ORDER BY rowid').fetchall()
        db.close();return [row[0] for row in result]

    def test_durable_dedup_of_same_accepted_generation(self):
        first=self.service.enqueue_changed();second=self.service.enqueue_changed()
        self.assertEqual(first,second);self.assertEqual(self.states(),['READY'])
        self.assertEqual(self.writes,[])

    def test_initial_pending_page_is_filled_automatically_without_owner_action(self):
        # Fresh publication of an empty specification, followed by acceptance
        # of a fact. Only the existing automatic sync is invoked afterwards.
        self.spec.unlink()
        with SpecStore(self.spec) as store:
            crm_bridge.CrmBridge(store).saved(self.rows(UID))
            vehicle=store.get_vehicle(UID)
            receipt={'uid':UID,'revision':vehicle['revision'],'identity_hash':vehicle['identity_hash'],
                'facts_digest':store.facts_digest(UID),'receipt_id':'SYNTHETIC-pending-readback',
                'status':'PASS','route_id':'SYNTHETIC-owner-publish','verified_at':'2026-09-10T00:00:00Z',
                'page_url':'https://www.uaart.com.ua/video/'+UID+'.html',
                'specification_visible':True,'single_vin':True,'shell_preserved':True}
            store.mark_publication_verified(UID,vehicle['revision'],receipt)
        pending=render.compose_page(page(),UID,[])
        for folder in ('video','site'):
            self.primary(folder).write_text(pending)
        catalog=(self.root/'video'/'katalog.html').read_bytes()
        self.accept_more()
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'VERIFIED')
        for folder in ('video','site'):
            filled=self.primary(folder).read_text()
            self.assertIn('1860',filled)
            self.assertNotIn('data-spec-status="PENDING"',filled)
            self.assertEqual(render._without_block(filled),render._without_block(pending))
        self.assertEqual((self.root/'video'/'katalog.html').read_bytes(),catalog)
        self.assertEqual(self.service.tick()['sync']['status'],'IDLE')

    def test_two_page_spec_only_sync_updates_real_verified_snapshot_once(self):
        original_catalog=(self.root/'video'/'katalog.html').read_bytes()
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'VERIFIED');self.assertEqual(result['page_writes'],2)
        for folder in ('video','site'):
            current=self.primary(folder).read_text()
            self.assertIn('1860',current);self.assertEqual(current.count(VIN),1)
            self.assertEqual(render._without_block(current),render._without_block(self.old_html.decode()))
        self.assertEqual((self.root/'video'/'katalog.html').read_bytes(),original_catalog)
        with SpecStore(self.spec) as store:
            self.assertEqual(store.get_publication_snapshot(UID)['facts_digest'],store.facts_digest(UID))
        self.assertEqual(self.service.tick()['sync']['status'],'IDLE')
        self.assertEqual(len(self.writes),2)

    def test_drafts_17_18_never_enqueue_or_publish(self):
        for uid in ('UA-0017','UA-0018'):
            self.update(auto_number=uid,published=0)
            with SpecStore(self.spec) as store:
                crm_bridge.CrmBridge(store).saved(self.rows(uid))
                store.set_manual_fact(uid,{'key':'length','value':'4900','unit':'mm'})
            self.assertEqual(self.service.enqueue_changed()['queued'],[])
        self.assertEqual(self.writes,[])

    def test_legacy_crm_published_flag_without_verified_store_is_insufficient(self):
        with SpecStore(self.spec) as store:
            store.set_published(UID,False)
        self.assertEqual(self.service.enqueue_changed()['queued'],[])
        self.assertEqual(self.writes,[])

    def test_fresh_crm_change_cancels_stale_generation(self):
        self.service.enqueue_changed();self.update(price='12000')
        result=self.service.run_once()
        self.assertEqual(result['status'],'STALE_CANCELLED');self.assertEqual(self.writes,[])

    def test_identity_change_cancels_stale_generation(self):
        self.service.enqueue_changed();self.update(year='2018')
        with SpecStore(self.spec) as store:
            crm_bridge.CrmBridge(store).saved(self.rows(UID))
        self.assertEqual(self.service.run_once()['status'],'STALE_CANCELLED')
        self.assertEqual(self.writes,[])

    def test_hidden_card_is_not_recreated_by_pending_sync(self):
        self.service.enqueue_changed();self.update(published=0)
        self.primary().unlink()
        self.assertEqual(self.service.run_once()['status'],'STALE_CANCELLED')
        self.assertFalse(self.primary().exists())

    def test_missing_authority_makes_zero_html_writes(self):
        self.service.authorize=lambda *_:False
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'FAILED_REVIEW_REQUIRED')
        self.assertEqual(self.writes,[]);self.assertEqual(self.primary().read_bytes(),self.old_html)
        self.assertEqual(self.service.run_once()['status'],'BLOCKED_SYNC_RECONCILIATION_REQUIRED')

    def test_failure_second_page_rolls_back_exact_first_and_keeps_facts(self):
        def failing(path,data,mode=None):
            if path.parent.name=='site':raise OSError('synthetic second-file failure')
            self.atomic(path,data,mode)
        self.guard._atomic=failing
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'FAILED_REVIEW_REQUIRED')
        for folder in ('video','site'):self.assertEqual(self.primary(folder).read_bytes(),self.old_html)
        with SpecStore(self.spec) as store:
            self.assertEqual(len(store.get_facts(UID)),2)
            self.assertNotEqual(store.get_publication_snapshot(UID)['facts_digest'],store.facts_digest(UID))
        self.assertTrue(list((self.root/'rezerv_publikacii'/'SPEC_REBUILD10_SYNC').glob('*/manifest.json')))

    def test_stale_public_readback_rolls_back_both_local_pages(self):
        self.service.transport=lambda url,**_:bootstrap.HttpReadback(url,200,b'stale cache')
        result=self.service.tick()['sync'];self.assertEqual(result['status'],'FAILED_REVIEW_REQUIRED')
        for folder in ('video','site'):self.assertEqual(self.primary(folder).read_bytes(),self.old_html)
        self.assertEqual(self.states(),['FAILED_REVIEW_REQUIRED'])
        writes=len(self.writes);self.service.tick();self.assertEqual(len(self.writes),writes)

    def test_rollback_never_overwrites_someone_elses_new_page(self):
        foreign=b'<html>External owner edit must remain</html>'
        def failing(url,**kwargs):
            self.primary('site').write_bytes(foreign)
            return bootstrap.HttpReadback(url,200,b'stale')
        self.service.transport=failing
        result=self.service.tick()['sync']
        self.assertEqual(result['error'],'SYNC_ROLLBACK_CONCURRENT_CHANGE')
        self.assertEqual(self.primary('site').read_bytes(),foreign)

    def test_restart_does_not_repeat_started_outbox(self):
        self.service.enqueue_changed()
        outbox=SyncOutbox(self.outbox);self.assertEqual(outbox.claim()['status'],'CLAIMED');outbox.close()
        self.assertEqual(self.service.run_once()['status'],'BLOCKED_SYNC_RECONCILIATION_REQUIRED')
        self.assertEqual(self.writes,[])

    def test_hidden_fact_cannot_disappear_automatically_from_existing_html(self):
        with SpecStore(self.spec) as store:
            store.set_hidden(UID,'length',True)
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'FAILED_REVIEW_REQUIRED')
        self.assertEqual(self.writes,[])

    def test_protected_catalog_change_stops_and_preserves_external_edit(self):
        original=self.guard._atomic
        def change_catalog(path,data,mode=None):
            original(path,data,mode)
            if path.parent.name=='site':(self.root/'video'/'katalog.html').write_text('external catalogue edit')
        self.guard._atomic=change_catalog
        result=self.service.tick()['sync']
        self.assertEqual(result['error'],'SYNC_PROTECTED_SURFACE_CHANGED')
        self.assertEqual((self.root/'video'/'katalog.html').read_text(),'external catalogue edit')
        for folder in ('video','site'):self.assertEqual(self.primary(folder).read_bytes(),self.old_html)


    def test_replace_then_error_is_included_in_exact_rollback(self):
        def replace_then_error(path,data,mode=None):
            self.atomic(path,data,mode)
            if path.parent.name=='site':raise OSError('synthetic error after os.replace')
        self.guard._atomic=replace_then_error
        result=self.service.tick()['sync']
        self.assertEqual(result['status'],'FAILED_REVIEW_REQUIRED')
        for folder in ('video','site'):self.assertEqual(self.primary(folder).read_bytes(),self.old_html)

    def test_all_rollback_postimages_checked_before_any_compensation(self):
        foreign=b'<html>Foreign first-written page</html>'
        def failure(url,**kwargs):
            self.primary('video').write_bytes(foreign)
            return bootstrap.HttpReadback(url,200,b'bad')
        self.service.transport=failure
        result=self.service.tick()['sync']
        self.assertEqual(result['error'],'SYNC_ROLLBACK_CONCURRENT_CHANGE')
        self.assertEqual(self.primary('video').read_bytes(),foreign)
        # Site is first in reverse rollback order; it must not be restored before
        # the later video preflight discovers the foreign page.
        self.assertIn(b'1860',self.primary('site').read_bytes())

    def test_receipt_commit_then_error_never_restores_pages_behind_receipt(self):
        original=SpecStore.mark_publication_verified
        def commit_then_error(store,*args,**kwargs):
            original(store,*args,**kwargs)
            raise RuntimeError('synthetic post-commit failure')
        with patch.object(SpecStore,'mark_publication_verified',commit_then_error):
            result=self.service.tick()['sync']
        self.assertEqual(result['error'],'SYNC_RECEIPT_COMMIT_REQUIRES_RECONCILIATION')
        for folder in ('video','site'):self.assertIn(b'1860',self.primary(folder).read_bytes())
        with SpecStore(self.spec) as store:
            self.assertEqual(store.get_publication_snapshot(UID)['facts_digest'],store.facts_digest(UID))
        self.assertTrue(self.service.blocked())

    def test_unrelated_sqlite_database_remains_untouched(self):
        db=sqlite3.connect(self.outbox);db.execute('CREATE TABLE private_data(x)');db.commit();db.close()
        before=self.outbox.read_bytes()
        with self.assertRaisesRegex(bootstrap.BootstrapError,'UNRELATED_DATABASE'):
            SyncOutbox(self.outbox)
        self.assertEqual(self.outbox.read_bytes(),before)

    def test_hardlink_and_open_inode_swap_rejected(self):
        db=SyncOutbox(self.outbox);db.close()
        alias=self.root/'alias.db';os.link(self.outbox,alias)
        with self.assertRaisesRegex(bootstrap.BootstrapError,'FILE_CHANGED_OR_LINKED'):
            SyncOutbox(self.outbox)
        alias.unlink();db=SyncOutbox(self.outbox)
        replacement=self.root/'replacement.db';replacement.write_bytes(self.outbox.read_bytes())
        os.replace(replacement,self.outbox)
        with self.assertRaisesRegex(bootstrap.BootstrapError,'FILE_CHANGED_OR_LINKED'):
            db.claim()
        db.close()

    def test_worker_tick_automatically_syncs_accepted_facts_once(self):
        receipt={'module':'spec_rebuild10','old_workers_stopped':True,'exclusive_owner':True,'receipt_id':'SYNTHETIC'}
        worker=bootstrap.WorkerService(self.spec,self.rows,{},receipt,lambda _:True)
        bootstrap.attach_public_sync(worker,self.runtime,self.outbox,
            authorize_sync=self.authorize,transport=self.transport)
        result=worker.tick()
        self.assertEqual(result['public_sync']['sync']['status'],'VERIFIED')
        self.assertEqual(len(self.writes),2)
        self.assertEqual(worker.tick()['public_sync']['sync']['status'],'IDLE')
        self.assertEqual(len(self.writes),2)

    def test_supplier_failure_does_not_block_previously_accepted_site_update(self):
        receipt={'module':'spec_rebuild10','old_workers_stopped':True,'exclusive_owner':True,'receipt_id':'SYNTHETIC'}
        worker=bootstrap.WorkerService(self.spec,self.rows,{},receipt,lambda _:True)
        bootstrap.attach_public_sync(worker,self.runtime,self.outbox,
            authorize_sync=self.authorize,transport=self.transport)
        with patch('cloud.spec_rebuild10.worker.SpecWorker.run_once',
                   return_value={'status':'RETRY_SCHEDULED','publication_performed':False}):
            result=worker.tick()
        self.assertEqual(result['worker']['status'],'RETRY_SCHEDULED')
        self.assertEqual(result['public_sync']['sync']['status'],'VERIFIED')
        self.assertEqual(len(self.writes),2)


if __name__=='__main__':unittest.main()
