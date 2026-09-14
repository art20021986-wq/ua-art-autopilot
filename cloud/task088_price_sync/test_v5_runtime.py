"""Meaningful FINAL v5 operation tests; isolated DB/files and explicit fake authority."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest

from test_runtime import runtime as R, outbox as O, prices


class Crash(BaseException):
    pass


class V5RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'crm.sqlite'
        self.now = 1000000
        self.journal = self.root/'journals';self.journal.mkdir(mode=0o700)
        with sqlite3.connect(self.db) as conn:
            conn.executescript('''CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,
                published INTEGER,price_uah INTEGER,price_georgia INTEGER,description TEXT,status TEXT,updated_at TEXT);
                INSERT INTO cars VALUES(1,'UA-0001','VIN0001',1,20000,8000,'Keep first','korea','old');
                INSERT INTO cars VALUES(2,'UA-0002','VIN0002',1,9000,NULL,'Keep second','ferry','old');
                CREATE TABLE audit(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,field TEXT,
                    old_value TEXT,new_value TEXT,created_at TEXT);''')
            conn.execute('BEGIN IMMEDIATE');R.install(conn);conn.commit()
        self.cards={i:self.root/f'UA-{i:04d}.html' for i in (1,2)}
        for i,p in self.cards.items():
            p.write_text('<html><h1>Protected title</h1><img src="original.jpg"><div>VIN%04d</div>'%i+
                         prices.render_market_prices(self.row(i),require_car_id=True)+'<p>Extra specification</p></html>')
        self.catalog=self.root/'katalog.html'
        self.catalog.write_text('<html><nav>Protected counters:2</nav>'+''.join(
            '<article><a href="UA-%04d.html"><img src="car%d.jpg"></a>'%(i,i)+
            prices.render_market_prices(self.row(i),compact=True,require_car_id=True)+'</article>' for i in (1,2))+'</html>')
        self.home=self.root/'index.html';self.home.write_text('<html><nav>4 stages, 2 cars</nav></html>')
        self.url_paths={'https://example.test/'+p.name:p for p in (*self.cards.values(),self.catalog,self.home)}
        self.binding=R.Binding(db_path=self.db,publication_lock=self.root/'publish.lock',journal_root=self.journal,
            resolve_surfaces=self.surfaces,authorize=self.authorize,owner_chat_id=123,detail_url='https://example.test/report',
            owner_private_chat_verified=True,car_identities=((1,'UA-0001'),(2,'UA-0002')),
            read_public=lambda url:self.url_paths[url].read_bytes(),clock=lambda:self.now)
        self.worker=R.V5Worker(self.binding)
        self.sent=[]
        self.counter=0

    def row(self,car=1):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory=sqlite3.Row
            return dict(conn.execute('SELECT * FROM cars WHERE id=?',(car,)).fetchone())

    def surfaces(self,code):
        car=int(code[-4:])
        return (R.Surface('CARD',self.cards[car],'https://example.test/'+code+'.html'),
                R.Surface('CATALOG',self.catalog,'https://example.test/katalog.html'),
                R.Surface('HOME',self.home,'https://example.test/index.html',price_applicable=False))

    def authorize(self,event,surfaces):
        return {'canonical_task_id':'SYNTHETIC_TEST','canonical_claim_id':'TEST-CLAIM',
                'canonical_transaction_id':'TEST-TXN','gate_b_receipt_sha256':'a'*64,
                'event_key':event['event_key'],'claim_nonce':event['claim_nonce'],
                'allowed_paths':[str(s.path) for s in surfaces],'writer_fence_verified':True,'expires_ms':self.now+30000}

    def submit(self,field='price_georgia',value=18900,car=1,key=None,actor=700,chat=700):
        self.counter+=1
        key=key or hashlib.sha256(f'{self.counter}:{car}:{field}:{value}'.encode()).hexdigest()
        with sqlite3.connect(self.db) as conn:
            conn.execute('BEGIN IMMEDIATE')
            result=O.submit(conn,event_key=key,car_id=car,field=field,value=value,actor_id=actor,chat_id=chat,now_ms=self.now,
                provenance={'source':'SYNTHETIC_TEST','actor_id':actor,'chat_id':chat})
            conn.commit()
        return result

    def event(self,key):
        with sqlite3.connect(self.db) as conn:
            return O.get_operation(conn,key)

    def notices(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(f'SELECT chat_id,kind,state,body FROM {O.V5_NOTICES} ORDER BY created_ms,notice_key').fetchall()

    def audit(self,key,fact):
        with sqlite3.connect(self.db) as conn:
            row=conn.execute(f'SELECT payload_json FROM {O.V5_AUDIT} WHERE event_key=? AND fact=?',(key,fact)).fetchone()
            return json.loads(row[0]) if row else None

    def _set_fixture_stage(self, status, car=1):
        """Model an already completed, separate stage change before price input."""
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE cars SET status=? WHERE id=?', (status, car))
        row = self.row(car)
        for surface in self.surfaces(row['auto_number']):
            if not surface.price_applicable:
                continue
            text = surface.path.read_text()
            left, right = self.worker._span(text, surface, row['auto_number'])
            fragment = prices.render_market_prices(row, compact=surface.kind != 'CARD', require_car_id=True)
            surface.path.write_text(text[:left] + fragment + text[right:])

    def test_kyiv_ua_and_ge_edits_preserve_hidden_ge_and_all_protected_data(self):
        self._set_fixture_stage('ua_arrived')
        protected = {surface.path: self.worker._protected_hash(surface.path.read_bytes(), surface, 'UA-0001')
                     for surface in self.surfaces('UA-0001')}
        untouched_car = self.cards[2].read_bytes()
        initial = self.row()
        first = self.submit(field='price_uah', value=24500)
        self.worker.tick()
        self.assertEqual(self.event(first['event_key'])['state'], 'COMPLETED')
        self.assertEqual((self.row()['price_uah'], self.row()['price_georgia']), (24500, 8000))
        after_ua = {surface.path: surface.path.read_bytes() for surface in self.surfaces('UA-0001')}
        second = self.submit(value=18900)
        self.worker.tick()
        self.assertEqual(self.event(second['event_key'])['state'], 'COMPLETED')
        self.assertEqual((self.row()['price_uah'], self.row()['price_georgia']), (24500, 18900))
        self.assertEqual({k: v for k, v in self.row().items() if k not in ('price_uah', 'price_georgia', 'updated_at')},
                         {k: v for k, v in initial.items() if k not in ('price_uah', 'price_georgia', 'updated_at')})
        for surface in self.surfaces('UA-0001'):
            self.assertEqual(surface.path.read_bytes(), after_ua[surface.path])
            self.assertEqual(self.worker._protected_hash(surface.path.read_bytes(), surface, 'UA-0001'),
                             protected[surface.path])
            if surface.price_applicable:
                text = surface.path.read_text()
                left, right = self.worker._span(text, surface, 'UA-0001')
                parsed = R._Prices(text[left:right])
                self.assertEqual(parsed.values, [('ukraine', 'price_uah', '24500', 'USD')])
                self.assertNotIn('🇬🇪', text[left:right])
                self.assertNotIn('Рустави', text[left:right])
        self.assertEqual(self.cards[2].read_bytes(), untouched_car)
        self.assertEqual(self.audit(second['event_key'], 'DB_COMMITTED')['details']['after']['price_georgia'], 18900)
        self.assertTrue(self.audit(second['event_key'], 'DB_READBACK')['details']['separate_connection'])
        self.assertEqual(len(self.notices()), 2)

    def test_kyiv_restart_uses_committed_stage_snapshot_without_reintroducing_ge(self):
        self._set_fixture_stage('ua_arrived')
        event = self.submit(field='price_uah', value=24500)
        original = self.worker._commit_selected_price
        def crash(*args):
            original(*args)
            raise Crash()
        self.worker._commit_selected_price = crash
        with self.assertRaises(Crash):
            self.worker.process_operation(event['event_key'])
        self.assertEqual(self.event(event['event_key'])['state'], 'DB_COMMITTED')
        result = R.V5Worker(self.binding).tick()
        completed = self.event(event['event_key'])
        self.assertEqual(completed['state'], 'COMPLETED', result)
        self.assertEqual(json.loads(completed['after_json'])['status'], 'ua_arrived')
        for surface in self.surfaces('UA-0001'):
            if surface.price_applicable:
                source = surface.path.read_text()
                left, right = self.worker._span(source, surface, 'UA-0001')
                self.assertEqual([v[0] for v in R._Prices(source[left:right]).values], ['ukraine'])
        self.assertEqual(self.row()['price_georgia'], 8000)

    def test_kyiv_and_georgia_concurrent_price_operations_keep_distinct_market_visibility(self):
        self._set_fixture_stage('ua_arrived', car=1)
        self._set_fixture_stage('ge_to_kyiv', car=2)
        one = self.submit(field='price_uah', value=24500, car=1)
        two = self.submit(value=7500, car=2)
        self.worker.tick()
        self.assertEqual([self.event(e['event_key'])['state'] for e in (one, two)], ['COMPLETED'] * 2)
        catalog = self.catalog.read_text()
        for car, expected in ((1, ['ukraine']), (2, ['ukraine', 'georgia'])):
            code = f'UA-{car:04d}'
            left, right = R.fragment_span(catalog, kind='CATALOG', code=code)
            self.assertEqual([v[0] for v in R._Prices(catalog[left:right]).values], expected)
        self.assertEqual(self.row(1)['price_georgia'], 8000)
        self.assertEqual(self.row(2)['price_uah'], 9000)

    def test_kyiv_snapshot_mismatch_or_public_ge_cannot_pass_semantic_verification(self):
        self._set_fixture_stage('ua_arrived')
        event = self.submit(field='price_uah', value=24500)
        self.worker.tick()
        event = self.event(event['event_key'])
        source = self.cards[1].read_text()
        left, right = R.fragment_span(source, kind='CARD', code='UA-0001')
        R.semantic_fragment(source[left:right], 'UA-0001', event)
        wrong = prices.render_market_prices(dict(self.row(), status='ge_waiting'), require_car_id=True)
        with self.assertRaisesRegex(R.SyncError, 'PRICE_SEMANTICS_MISMATCH'):
            R.semantic_fragment(wrong, 'UA-0001', event)
        for mutation in ({'auto_number': 'UA-0099'}, {'id': 2}, {'vin': 'WRONG'}, {'price_georgia': None}):
            altered = dict(event, after_json=json.dumps(dict(json.loads(event['after_json']), **mutation)))
            with self.assertRaisesRegex(R.SyncError, 'V5_RENDER_DB_SNAPSHOT_MISMATCH'):
                self.worker._desired(altered, self.surfaces('UA-0001')[0])
        snapshot = json.loads(event['after_json']); del snapshot['status']
        with self.assertRaisesRegex(R.SyncError, 'V5_RENDER_DB_SNAPSHOT_MISMATCH'):
            self.worker._desired(dict(event, after_json=json.dumps(snapshot)), self.surfaces('UA-0001')[0])
        with self.assertRaisesRegex(R.SyncError, 'V5_RENDER_DB_SNAPSHOT_REQUIRED'):
            self.worker._desired(dict(event, after_json=None), self.surfaces('UA-0001')[0])
        missing_snapshot = dict(event); del missing_snapshot['after_json']
        with self.assertRaisesRegex(R.SyncError, 'V5_RENDER_DB_SNAPSHOT_REQUIRED'):
            self.worker._desired(missing_snapshot, self.surfaces('UA-0001')[0])

    def test_four_conscious_changes_fully_complete_fifo_and_preserve_ua(self):
        values=[18000,18500,18300,18900]
        events=[self.submit(value=v) for v in values]
        self.assertEqual(self.row()['price_georgia'],8000)
        self.assertEqual([e['state'] for e in events],['QUEUED']*4)
        for e,expected in zip(events,values):
            result=self.worker.tick()
            self.assertEqual(self.event(e['event_key'])['state'],'COMPLETED',result)
            self.assertEqual(self.row()['price_georgia'],expected)
            self.assertEqual(self.row()['price_uah'],20000)
            self.assertIn('data-ua-value="%d"'%expected,self.cards[1].read_text())
            self.assertIsNotNone(self.audit(e['event_key'],'DB_READBACK'))
        self.assertEqual(len(self.notices()),4)
        self.assertEqual(self.home.read_text(),'<html><nav>4 stages, 2 cars</nav></html>')

    def test_ua_then_ge_serialized_without_cross_write(self):
        ua=self.submit(field='price_uah',value=24500);ge=self.submit(value=18900)
        self.worker.tick()
        self.assertEqual((self.row()['price_uah'],self.row()['price_georgia']),(24500,8000))
        self.assertEqual(self.event(ge['event_key'])['state'],'QUEUED')
        self.worker.tick()
        self.assertEqual((self.row()['price_uah'],self.row()['price_georgia']),(24500,18900))
        self.assertEqual(self.audit(ge['event_key'],'DB_COMMITTED')['details']['before']['price_uah'],24500)

    def test_same_value_new_operation_is_not_deduplicated(self):
        first=self.submit(value=8000);second=self.submit(value=8000)
        self.worker.tick();self.worker.tick()
        self.assertNotEqual(first['event_key'],second['event_key'])
        self.assertEqual([self.event(e['event_key'])['state'] for e in (first,second)],['COMPLETED']*2)

    def test_replay_completed_operation_has_no_duplicate_effects(self):
        event=self.submit();key=event['event_key'];self.worker.tick()
        with sqlite3.connect(self.db) as conn:
            counts=conn.execute(f'SELECT COUNT(*) FROM {O.V5_AUDIT}').fetchone()[0]
        self.assertTrue(self.worker.process_operation(key)['replay'])
        self.submit(key=key)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {O.V5_AUDIT}').fetchone()[0],counts)
        self.assertEqual(len(self.notices()),1)

    def test_parallel_cars_have_no_shared_or_db_lock_during_http(self):
        one=self.submit();two=self.submit(field='price_uah',value=9500,car=2)
        barrier=threading.Barrier(2);seen=set();guard=threading.Lock()
        def public(url):
            thread=threading.get_ident()
            if '/UA-' in url:
                with guard:
                    first=thread not in seen;seen.add(thread)
                if first:
                    barrier.wait(timeout=3)
                    # Both executors are now inside HTTP. Serialize only the
                    # probes so they cannot contend with one another's test DB
                    # transaction; neither application worker is writing here.
                    with guard:
                        with sqlite3.connect(self.db,timeout=0) as conn:
                            conn.execute('BEGIN IMMEDIATE');conn.rollback()
                        with self.worker.lock():
                            pass
                    barrier.wait(timeout=3)
            return self.url_paths[url].read_bytes()
        self.worker=R.V5Worker(replace(self.binding,read_public=public))
        result=self.worker.tick()
        self.assertEqual(len(seen),2,result)
        self.assertEqual([self.event(e['event_key'])['state'] for e in (one,two)],['COMPLETED']*2,result)
        self.assertEqual(self.row(2)['price_uah'],9500)
        self.assertIn('data-ua-value="18900"',self.catalog.read_text())
        self.assertIn('data-ua-value="9500"',self.catalog.read_text())

    def test_restart_after_committed_claim_resumes_without_reentry(self):
        event=self.submit();key=event['event_key']
        with sqlite3.connect(self.db) as conn:
            conn.execute('BEGIN IMMEDIATE');O.claim_operation(conn,event_key=key,nonce='b'*64,now_ms=self.now);conn.commit()
        R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')
        self.assertEqual(self.event(key)['claim_nonce'],'b'*64)

    def test_restart_after_each_durable_execution_checkpoint(self):
        for method,phase in (('_commit_selected_price','DB_COMMITTED'),('_publish','SITE_PUBLISHED'),('_verify','VERIFIED')):
            with self.subTest(phase=phase):
                event=self.submit(value=18100+self.counter);key=event['event_key']
                worker=R.V5Worker(self.binding);original=getattr(worker,method)
                def crash(*args,_original=original):
                    _original(*args);raise Crash()
                setattr(worker,method,crash)
                with self.assertRaises(Crash):worker.process_operation(key)
                self.assertEqual(self.event(key)['state'],phase)
                result=R.V5Worker(self.binding).tick()
                self.assertEqual(self.event(key)['state'],'COMPLETED',result)
                with sqlite3.connect(self.db) as conn:
                    self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {O.V5_AUDIT} WHERE event_key=? AND fact=?',
                                                 (key,'DB_COMMITTED')).fetchone()[0],1)

    def test_verified_restart_rechecks_site_before_success(self):
        event=self.submit();key=event['event_key'];original=self.worker._verify
        def crash(*args):original(*args);raise Crash()
        self.worker._verify=crash
        with self.assertRaises(Crash):self.worker.process_operation(key)
        self.cards[1].write_text(self.cards[1].read_text().replace('Protected title','Unexpected title'))
        R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'VERIFIED')
        self.assertEqual(self.event(key)['blocked'],1)
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))

    def test_partial_local_switch_crash_resumes_without_repeating_db_commit(self):
        event=self.submit();key=event['event_key'];original=R._atomic_write;hits=[]
        def crash(path,*args,**kwargs):
            original(path,*args,**kwargs)
            if path==self.cards[1]:hits.append(path);raise Crash()
        R._atomic_write=crash
        try:
            with self.assertRaises(Crash):self.worker.process_operation(key)
        finally:R._atomic_write=original
        self.assertEqual(self.event(key)['state'],'DB_COMMITTED')
        R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')
        self.assertEqual(self.audit(key,'DB_COMMITTED')['details']['old_value'],8000)
        self.assertEqual(hits,[self.cards[1]])

    def test_authority_failure_cannot_mutate_db_or_site(self):
        event=self.submit();key=event['event_key'];before=self.row();html=self.cards[1].read_bytes()
        self.worker=R.V5Worker(replace(self.binding,authorize=lambda *args:{}))
        self.worker.tick()
        self.assertEqual(self.row(),before);self.assertEqual(self.cards[1].read_bytes(),html)
        self.assertEqual(self.event(key)['blocked'],1)
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))

    def test_public_failure_is_not_success_and_rechecks_checkpoint(self):
        event=self.submit();key=event['event_key']
        def offline(url):raise OSError('offline')
        R.V5Worker(replace(self.binding,read_public=offline)).tick()
        self.assertEqual(self.event(key)['state'],'SITE_PUBLISHED')
        self.assertEqual(self.event(key)['blocked'],0)
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))
        self.now+=10000;R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')
        self.assertEqual(self.audit(key,'DB_COMMITTED')['details']['old_value'],8000)

    def test_success_receipt_sent_once_to_initiating_operator(self):
        event=self.submit(chat=701);key=event['event_key'];self.worker.tick()
        sent=self.sent
        class Bot:
            async def send_message(self,**kwargs):sent.append(kwargs);return SimpleNamespace(message_id=len(sent))
        asyncio.run(self.worker.deliver_notices(Bot()));asyncio.run(self.worker.deliver_notices(Bot()))
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['chat_id'],701)
        self.assertIn('✅ Завершено. Цена Грузии UA-0001: 18 900 $.',sent[0]['text'])
        self.assertEqual(self.notices()[0][2],'SENT')
        self.assertEqual(self.audit(key,'TELEGRAM_SUCCESS_SENT')['details']['message_id'],1)

    def test_ambiguous_telegram_delivery_never_replays_execution_or_dispatch(self):
        event=self.submit();key=event['event_key'];self.worker.tick();sent=self.sent
        class Bot:
            async def send_message(self,**kwargs):sent.append(kwargs);raise TimeoutError('ack lost')
        asyncio.run(self.worker.deliver_notices(Bot()));asyncio.run(R.V5Worker(self.binding).deliver_notices(Bot()))
        self.assertEqual(len(sent),1);self.assertEqual(self.notices()[0][2],'AMBIGUOUS')
        self.assertEqual(self.event(key)['state'],'COMPLETED')

    def test_missing_ge_stays_nullable_and_preserves_ua(self):
        event=self.submit(value=None);self.worker.tick()
        self.assertIsNone(self.row()['price_georgia']);self.assertEqual(self.row()['price_uah'],20000)
        self.assertIn('Цена уточняется',self.cards[1].read_text());self.assertNotIn('>0 $<',self.cards[1].read_text())
        self.assertEqual(self.event(event['event_key'])['state'],'COMPLETED')

    def test_protected_html_change_after_db_commit_is_not_adopted_as_baseline(self):
        event=self.submit();key=event['event_key'];original=self.worker._publish
        def changed(*args):
            self.cards[1].write_text(self.cards[1].read_text().replace('original.jpg','UNEXPECTED.jpg'))
            return original(*args)
        self.worker._publish=changed
        self.worker.tick()
        self.assertEqual(self.event(key)['state'],'DB_COMMITTED')
        self.assertEqual(self.event(key)['blocked'],1)
        self.assertIn('original.jpg',(self.journal/('v5_'+key)/'0.before').read_text())
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))

    def test_existing_unselected_site_price_mismatch_blocks_before_db_mutation(self):
        original=prices.render_market_prices(self.row(),require_car_id=True)
        wrong=prices.render_market_prices(dict(self.row(),price_uah=19999),require_car_id=True)
        self.cards[1].write_text(self.cards[1].read_text().replace(original,wrong))
        before=self.row();event=self.submit();self.worker.tick()
        self.assertEqual(self.row(),before)
        self.assertIn('data-ua-value="19999"',self.cards[1].read_text())
        self.assertEqual(self.event(event['event_key'])['last_error'],'V5_EXISTING_SITE_PRICE_DIFFERS_FROM_DB')

    def test_unauthorized_other_car_public_price_cannot_hide_in_shared_mask(self):
        event=self.submit();key=event['event_key']
        old=prices.render_market_prices(self.row(2),compact=True,require_car_id=True)
        wrong=prices.render_market_prices(dict(self.row(2),price_uah=999999),compact=True,require_car_id=True)
        def public(url):
            data=self.url_paths[url].read_text()
            return (data.replace(old,wrong) if 'katalog' in url else data).encode()
        R.V5Worker(replace(self.binding,read_public=public)).tick()
        self.assertNotEqual(self.event(key)['state'],'COMPLETED')
        self.assertEqual(self.event(key)['last_error'],'V5_UNAUTHORIZED_OTHER_CAR_PRICE_VERSION')
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))

    def test_control_stop_recovers_only_after_fresh_authorization(self):
        event=self.submit();key=event['event_key'];before=self.row()
        def halted(*args):raise R.SyncError('CONTROL_BLOCKS_PRICE_PUBLICATION')
        R.V5Worker(replace(self.binding,authorize=halted)).tick()
        self.assertEqual(self.row(),before);self.assertEqual(self.event(key)['blocked'],0)
        self.now+=10000
        R.V5Worker(replace(self.binding,authorize=halted)).tick()
        self.assertEqual(self.row(),before)
        self.now+=10000;R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')

    def test_expired_authority_lease_rolls_back_before_db_commit(self):
        event=self.submit();key=event['event_key'];before=self.row()
        def short_lease(*args):
            proof=self.authorize(*args);proof['expires_ms']=self.now+2;return proof
        worker=R.V5Worker(replace(self.binding,authorize=short_lease));original=worker._journal
        def slow(*args):
            result=original(*args);self.now+=5;return result
        worker._journal=slow;worker.tick()
        self.assertEqual(self.row(),before)
        self.assertEqual(self.event(key)['state'],'CLAIMED')
        self.assertEqual(self.event(key)['last_error'],'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')

    def test_public_price_lag_reverifies_without_repeating_db_update(self):
        stale=self.cards[1].read_bytes();event=self.submit();key=event['event_key']
        def public(url):return stale if 'UA-0001' in url else self.url_paths[url].read_bytes()
        R.V5Worker(replace(self.binding,read_public=public)).tick()
        self.assertEqual(self.event(key)['last_error'],'V5_PUBLIC_PRICE_NOT_CONVERGED')
        self.assertEqual(self.event(key)['blocked'],0)
        self.now+=10000;R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')
        self.assertEqual(self.audit(key,'DB_COMMITTED')['details']['old_value'],8000)

    def test_checkpoint_versions_and_receipt_follow_full_verification(self):
        event=self.submit();key=event['event_key'];original=self.worker._verify
        def crash_before_verify(*args):raise Crash()
        self.worker._verify=crash_before_verify
        with self.assertRaises(Crash):self.worker.process_operation(key)
        self.assertEqual(self.event(key)['state'],'SITE_PUBLISHED')
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))
        committed=self.audit(key,'DB_COMMITTED')['details'];readback=self.audit(key,'DB_READBACK')['details']
        self.assertEqual(committed['record_version_before'],R.digest(R.json_bytes(committed['before'])))
        self.assertEqual(committed['record_version_after'],readback['row_sha256'])
        self.assertEqual(committed['schema_sha256'],readback['schema_sha256'])
        self.assertEqual(committed['operation_sequence'],event['sequence'])
        R.V5Worker(self.binding).tick()
        self.assertEqual(self.event(key)['state'],'COMPLETED')
        with sqlite3.connect(self.db) as conn:
            facts=[r[0] for r in conn.execute(f'SELECT fact FROM {O.V5_AUDIT} WHERE event_key=? ORDER BY audit_id',(key,))]
        self.assertLess(facts.index('DB_COMMITTED'),facts.index('DB_READBACK'))
        self.assertLess(facts.index('DB_READBACK'),facts.index('VERIFIED'))
        self.assertLess(facts.index('VERIFIED'),facts.index('COMPLETED'))
        self.assertEqual([(r[1],r[2]) for r in self.notices()],[('SUCCESS','PENDING')])

    def test_postcommit_schema_drift_fails_independent_readback(self):
        event=self.submit();key=event['event_key'];original=self.worker._db_readback
        mutated=[]
        def changed_schema(*args,**kwargs):
            if not mutated:
                with sqlite3.connect(self.db) as conn:conn.execute('CREATE TABLE unexpected_drift(value TEXT)')
                mutated.append(True)
            return original(*args,**kwargs)
        self.worker._db_readback=changed_schema;self.worker.tick()
        self.assertEqual(self.event(key)['state'],'DB_COMMITTED')
        self.assertEqual(self.event(key)['last_error'],'V5_DB_RECORD_OR_SCHEMA_VERSION_MISMATCH')
        self.assertFalse(any(row[1]=='SUCCESS' for row in self.notices()))


if __name__=='__main__':unittest.main()
