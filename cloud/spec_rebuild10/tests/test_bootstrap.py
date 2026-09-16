"""Actual SQLite/provider/renderer tests. Authority and HTTP are synthetic."""
from contextlib import nullcontext
from types import SimpleNamespace
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from cloud.spec_rebuild10 import bootstrap as b, crm_bridge, render
from cloud.spec_rebuild10.store import SpecStore
from cloud.spec_rebuild10.tests.test_render import page, UID, VIN


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.crm = self.root / 'crm.db'
        self.spec = self.root / 'spec.db'
        self.now = time.time()
        db = sqlite3.connect(self.crm)
        db.execute('CREATE TABLE cars (id INTEGER, auto_number TEXT, vin TEXT, brand TEXT, model TEXT, year TEXT, published INTEGER, price TEXT, updated_at TEXT)')
        db.execute('INSERT INTO cars VALUES (1,?,?,?,?,?,?,?,?)',
            (UID, VIN, 'Kia', 'K5', '2017', 0, '10000', '2026-09-09T00:00:00+00:00'))
        db.commit(); db.close()
        self.rows = b.CrmRows(self.crm)
        self.before = self.rows(UID)
        with SpecStore(self.spec) as store:
            crm_bridge.CrmBridge(store).saved(self.before)
            store.set_manual_fact(UID, {'key':'length','value':'4900','unit':'mm'})
            self.facts = store.get_facts(UID)
            vehicle = store.get_vehicle(UID)
            self.ticket = crm_bridge.PublicationTicket(UID, 'publish', vehicle['identity_hash'],
                vehicle['revision'], store.facts_digest(UID), b.digest(self.before), 1, 'synthetic-plan')
        self.html = render.compose_page(page(), UID, self.facts)
        self.op = {**asdict(self.ticket), 'owner_manual_action':True, 'gate_b':'PASS',
            'route':'PASS','external_writers':'PASS','crm_row_before':self.before,
            'pages':[], 'readback':[{'kind':'primary','url':'https://www.uaart.com.ua/video/'+UID+'.html',
            'sha256':hashlib.sha256(self.html.encode()).hexdigest()}]}
        base='https://www.uaart.com.ua/video/'
        self.bodies={base+UID+'.html':self.html.encode(), base+UID+'-diag.html':b'<html>Diagnostic fixture</html>',
            base+'katalog.html':('<a href="'+UID+'.html">Car</a>').encode()}
        self.op['readback']=[{'kind':kind,'url':url,'sha256':hashlib.sha256(self.bodies[url]).hexdigest()}
            for kind,url in [('primary',base+UID+'.html'),('diagnostic',base+UID+'-diag.html'),('catalog',base+'katalog.html')]]
        self.plan_data = {'schema':'UA-ART-SPEC-REBUILD10-RUNTIME-PLAN-1','module':'spec_rebuild10',
            'not_before':self.now-10,'expires_at':self.now+300,'source_pins':b.RUNTIME_PINS,'operations':[self.op]}
        self.write_plan()

    def tearDown(self):
        self.temp.cleanup()

    def write_plan(self, authenticate=lambda *_:True):
        self.plan_path = self.root/'plan.json'
        self.plan_path.write_text(json.dumps(self.plan_data))
        self.plan = b.ExactPlan(self.plan_path,hashlib.sha256(self.plan_path.read_bytes()).hexdigest(),
            authenticate=authenticate,rows=self.rows,store_path=self.spec,clock=lambda:self.now)

    def update(self, **values):
        db=sqlite3.connect(self.crm)
        db.execute('UPDATE cars SET '+','.join(k+'=?' for k in values)+' WHERE id=1',tuple(values.values()))
        db.commit();db.close()

    def request(self):
        return {k:v for k,v in asdict(self.ticket).items() if k != 'plan_id'}

    def test_readonly_rows_complete_and_fresh(self):
        old=self.crm.read_bytes()
        self.assertEqual(self.rows.snapshot()['rows'],[self.before])
        self.assertEqual(old,self.crm.read_bytes())
        self.update(price='12000')
        self.assertEqual(self.rows(UID)['price'],'12000')

    def test_duplicate_uid_rejected_before_reconcile(self):
        db=sqlite3.connect(self.crm)
        db.execute('INSERT INTO cars SELECT 2,auto_number,vin,brand,model,year,published,price,updated_at FROM cars')
        db.commit();db.close()
        with self.assertRaisesRegex(b.BootstrapError,'DUPLICATE'):
            self.rows.snapshot()

    def test_sqlite_connection_cannot_write(self):
        with self.rows.connection() as db, self.assertRaises(sqlite3.OperationalError):
            db.execute('DELETE FROM cars')

    def test_plan_pass_text_is_not_authority(self):
        with self.assertRaisesRegex(b.BootstrapError,'AUTHENTICATED_OWNER'):
            self.write_plan(authenticate=lambda *_:False)

    def test_plan_changed_on_disk_rejected(self):
        self.plan_path.write_text('{}')
        with self.assertRaisesRegex(b.BootstrapError,'PLAN_CHANGED'):
            self.plan.readiness(self.request())

    def test_expired_plan_rejected(self):
        self.now+=400
        with self.assertRaisesRegex(b.BootstrapError,'EXPIRED'):
            self.plan.load()

    def test_exact_plan_readiness_then_business_change_rejected(self):
        self.assertEqual(self.plan.readiness(self.request())['plan_id'],'synthetic-plan')
        self.update(price='99999')
        with self.assertRaisesRegex(b.BootstrapError,'CRM_CHANGED'):
            self.plan.readiness(self.request())

    def test_owner_cannot_be_swapped(self):
        request=dict(self.request(),actor_id=2)
        with self.assertRaisesRegex(b.BootstrapError,'actor_id'):
            self.plan.readiness(request)

    def page_request(self):
        before=self.html
        after=before.replace('Original description','Approved description')
        req={'uid':UID,'plan_id':self.ticket.plan_id,'action':'publish','revision':self.ticket.revision,
            'facts_digest':self.ticket.facts_digest,'crm_row_sha256':b.digest(self.rows(UID)),
            'before_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'after_sha256':hashlib.sha256(after.encode()).hexdigest(),
            'render_facts_sha256':render.facts_digest(self.facts),
            'shell_assets_sha256':render.shell_guard.validate_shell_assets(before,after)['ordered_static_assets_sha256']}
        return req

    def test_page_hashes_must_exist_in_independent_plan(self):
        self.plan.readiness(self.request())
        with self.assertRaisesRegex(b.BootstrapError,'HTML_NOT_IN_APPROVED'):
            self.plan.page_change(self.page_request())

    def test_page_allows_exact_lifecycle_fields_and_rejects_price_race(self):
        req=self.page_request()
        self.op['pages']=[{k:req[k] for k in ('before_sha256','after_sha256','render_facts_sha256','shell_assets_sha256')}]
        self.write_plan(); self.plan.readiness(self.request())
        self.update(published=1,updated_at=datetime.fromtimestamp(self.now,timezone.utc).isoformat())
        req['crm_row_sha256']=b.digest(self.rows(UID))
        self.assertEqual(self.plan.page_change(req)['authorization'],'PASS')
        self.update(price='99999');req['crm_row_sha256']=b.digest(self.rows(UID))
        with self.assertRaisesRegex(b.BootstrapError,'UNAPPROVED_CRM_BUSINESS'):
            self.plan.page_change(req)

    def reader(self, body=None, status=200, url=None):
        def transport(target, **limits):
            self.assertEqual(limits,{'timeout_seconds':15,'max_bytes':b.MAX_FILE})
            return b.HttpReadback(url or target,status,self.bodies[target] if body is None else body)
        return b.PublicReadback(self.plan,self.spec,transport=transport)

    def test_actual_received_html_matches_facts_vin_and_exact_hash(self):
        self.assertTrue(self.reader().verify(self.ticket,asdict(self.ticket)))

    def test_stale_or_redirected_readback_rejected(self):
        for reader in (self.reader(body=b'old page'),self.reader(url='https://evil.invalid/')):
            with self.subTest(reader=reader),self.assertRaises(b.BootstrapError):
                reader.verify(self.ticket,asdict(self.ticket))

    def test_current_facts_changed_during_readback_rejected(self):
        with SpecStore(self.spec) as store:
            store.set_manual_fact(UID,{'key':'length','value':'1','unit':'mm'})
        with self.assertRaisesRegex(b.BootstrapError,'FACTS_CHANGED'):
            self.reader().verify(self.ticket,asdict(self.ticket))

    def test_no_worker_without_authentic_installation(self):
        worker=b.WorkerService(self.spec,self.rows,{}, {},lambda _:False)
        with self.assertRaisesRegex(Exception,'HANDOFF_REQUIRED'):
            worker.tick()

    def test_bounded_tick_reconciles_but_does_not_publish_or_consume_unconfigured_job(self):
        receipt={'module':'spec_rebuild10','old_workers_stopped':True,'exclusive_owner':True,'receipt_id':'SYNTHETIC'}
        worker=b.WorkerService(self.spec,self.rows,{},receipt,lambda _:True)
        report=worker.tick()
        self.assertEqual(report['worker']['status'],'BLOCKED_NO_PROVISIONED_COLLECTORS')
        self.assertEqual(self.rows(UID)['published'],0)
        with SpecStore(self.spec) as store:
            self.assertEqual(store.get_jobs(UID)[0]['attempts'],0)

    def test_worker_registers_once_and_never_spawns_daemon(self):
        receipt={'module':'spec_rebuild10','old_workers_stopped':True,'exclusive_owner':True,'receipt_id':'SYNTHETIC'}
        calls=[]
        def register(name,tick):
            calls.append((name,tick)); return {'registered':True,'worker':name,'receipt_id':'synthetic-register'}
        worker=b.WorkerService(self.spec,self.rows,{},receipt,lambda _:True,register=register)
        worker.start(); worker.start()
        self.assertEqual(len(calls),1)

    def test_invalid_runtime_source_never_imported(self):
        from cloud.spec_rebuild10.prepare_bootstrap import prepare
        for name in b.RUNTIME_PINS:
            (self.root/name).write_text('raise RuntimeError("must never execute")')
        with self.assertRaisesRegex(ValueError,'UNREVIEWED_RUNTIME_SOURCE'):
            prepare(self.root,self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_arbitrary_404_cannot_verify_real_withdrawal(self):
        from dataclasses import replace
        ticket=replace(self.ticket,action='hide')
        self.op['action']='hide'
        self.op['readback']=[{'kind':'primary','url':'https://www.uaart.com.ua/video/not-a-card','absent':True}]
        self.write_plan()
        with self.assertRaisesRegex(b.BootstrapError,'PRIMARY_DIAGNOSTIC_CATALOG'):
            self.reader(status=404).verify(ticket,asdict(ticket))

    def test_publication_requires_real_catalog_link(self):
        url='https://www.uaart.com.ua/video/katalog.html'
        self.bodies[url]=b'<html>No target car</html>'
        self.op['readback'][-1]['sha256']=hashlib.sha256(self.bodies[url]).hexdigest()
        self.write_plan()
        with self.assertRaisesRegex(b.BootstrapError,'CATALOG_VISIBILITY'):
            self.reader().verify(self.ticket,asdict(self.ticket))

    def synthetic_locked_adapter(self, transition):
        # Only route authority/functions are synthetic; the durable ledger and
        # current SQLite row checks below are the actual adapter implementation.
        adapter=b.LockedLifecycle.__new__(b.LockedLifecycle)
        adapter.root=self.root;adapter.rows=self.rows;adapter.plan=self.plan
        adapter.readback=self.reader();adapter.ledger_path=self.root/'operations.db'
        adapter.guard=SimpleNamespace(_exclusive_lock=nullcontext)
        adapter.lifecycle=SimpleNamespace(_transition=transition)
        adapter.publisher=SimpleNamespace(opublikovat=lambda *_:None)
        adapter._pins=lambda:None
        return adapter

    def test_unknown_lifecycle_outcome_is_durably_never_executed_twice(self):
        calls=[]
        def transition(*args,**kwargs):
            calls.append(args);raise RuntimeError('synthetic process interruption')
        adapter=self.synthetic_locked_adapter(transition)
        with self.assertRaisesRegex(RuntimeError,'interruption'):
            adapter(self.ticket,self.before)
        with self.assertRaisesRegex(b.BootstrapError,'PRIOR_OPERATION_REQUIRES'):
            adapter(self.ticket,self.before)
        self.assertEqual(len(calls),1)
        db=sqlite3.connect(adapter.ledger_path)
        self.assertEqual(db.execute('SELECT state FROM operations').fetchone()[0],'STARTED')
        db.close()

    def test_verified_replay_reads_receipt_after_crm_publication_change(self):
        adapter=self.synthetic_locked_adapter(lambda *_:self.fail('must not execute again'))
        receipt=asdict(self.ticket)
        with adapter._ledger() as db:
            db.execute('INSERT INTO operations VALUES(?,?,?)',(b.digest(asdict(self.ticket)),
                'VERIFIED',json.dumps(receipt)));db.commit()
        self.update(published=1)
        self.assertTrue(adapter(self.ticket,self.before)['ok'])

    def test_symlink_plan_rejected(self):
        link=self.root/'link.json';link.symlink_to(self.plan_path)
        with self.assertRaisesRegex(b.BootstrapError,'SYMLINK'):
            b.read_regular(link)


if __name__ == '__main__':
    unittest.main()
