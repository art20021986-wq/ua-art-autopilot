import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from urllib.parse import urlencode
from uuid import uuid4

from ua_order.auth import Unauthorized, WebSessions, telegram_user
from ua_order.catalog import Catalog, COUNTRIES
from ua_order.contract import Conflict, Invalid, decode
from ua_order.crm import detail_view, list_view
from ua_order.legacy import deep_link, draft
from ua_order.repository import NotFound, Repository
from ua_order.service import OrderService, Principal
from ua_order.web import WebAdapter

CONFIG = Path(__file__).resolve().parents[2] / 'ua_order_ge_8country_guard_016/country_models.json'


class OrderFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 10000
        self.catalog = Catalog(CONFIG)
        self.repo = Repository(Path(self.tmp.name) / 'order_requests.db', clock=lambda:self.now)
        self.repo.initialize()
        self.service = OrderService(self.catalog, self.repo, 'test-consent-v1')
        self.user = Principal('web:test-session', 'site')
        self.data = dict(schema_version='ua_order_request.v1', request_id=str(uuid4()),
                         config_version=self.catalog.version, purchase_country_code='korea',
                         model='kia-k5', other_model='', budget={'code':'b2','currency':'USD'},
                         vehicle_type='k1', delivery_country='Україна', delivery_city='Київ',
                         customer_name='Тестовий клієнт', contact={'phone':'+380 (99) 000-00-00'},
                         comment='VIN-like text stays inert: TESTVIN0000000001', lang='uk',
                         source_path='/video/podbor.html', consent={'accepted':True,'version':'test-consent-v1'})

    def count(self, table):
        with self.repo.connection() as db:
            return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


class OrdersTest(OrderFixture, unittest.TestCase):
    def test_catalog_all_countries_languages_models(self):
        seen = 0
        for country in COUNTRIES:
            for model in self.catalog.country(country)['models']:
                for lang in ('uk','ru','ka'):
                    data = dict(self.data, request_id=str(uuid4()), purchase_country_code=country,
                                model=model['key'], lang=lang)
                    self.assertEqual(self.service.submit(data,self.user)['status'], 'saved')
                seen += 1
        self.assertEqual(seen,40)
        altered=self.catalog.export(); altered['countries']['usa']['models'].pop()
        self.assertEqual(len(altered['countries']['uae']['models']),5)
        self.assertEqual(len(self.catalog.country('usa')['models']),5)

    def test_concurrent_duplicate_creates_one_request_and_outbox(self):
        with ThreadPoolExecutor(max_workers=10) as executor:
            results=list(executor.map(lambda _:self.service.submit(copy.deepcopy(self.data),self.user),range(10)))
        self.assertEqual(len({r['number'] for r in results}),1)
        self.assertEqual(self.count('order_requests'),1)
        self.assertEqual(self.count('order_outbox'),1)

    def test_lost_response_and_restart_returns_same_receipt(self):
        first=self.service.submit(self.data,self.user)
        restarted=OrderService(self.catalog,Repository(self.repo.path),'test-consent-v1')
        self.assertEqual(restarted.submit(self.data,self.user),first)
        self.assertEqual(self.count('order_outbox'),1)

    def test_same_id_changed_payload_and_other_owner_conflict(self):
        self.service.submit(self.data,self.user)
        with self.assertRaises(Conflict):
            self.service.submit(dict(self.data,comment='changed'),self.user)
        with self.assertRaises(Conflict):
            self.service.submit(self.data,Principal('web:another','site'))

    def test_event_replay_does_not_create_second_request(self):
        actor=Principal('telegram:123','telegram_bot','bot1:887')
        self.service.submit(self.data,actor)
        self.service.submit(self.data,actor)
        with self.assertRaises(Conflict):
            self.service.submit(dict(self.data,request_id=str(uuid4())),actor)
        self.assertEqual(self.count('order_events'),1)

    def test_outbox_insert_failure_rolls_back_request(self):
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER abort_outbox BEFORE INSERT ON order_outbox BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.submit(self.data,self.user)
        self.assertEqual(self.count('order_requests'),0)

    def test_notification_failure_and_expired_lease(self):
        self.service.submit(self.data,self.user)
        first=self.repo.claim_notification()
        self.assertIsNone(self.repo.claim_notification())
        self.now+=61
        second=self.repo.claim_notification()
        self.assertNotEqual(first['lease'],second['lease'])
        self.repo.finish_notification(first,delivered=True)
        self.repo.finish_notification(second,delivered=False)
        self.assertIsNone(self.repo.claim_notification())
        self.now+=61
        self.assertIsNone(self.repo.claim_notification())  # second attempt backs off for 120 seconds
        self.now+=60
        third=self.repo.claim_notification()
        self.repo.finish_notification(third,delivered=True)
        self.assertIsNone(self.repo.claim_notification())
        self.assertEqual(self.count('order_requests'),1)

    def test_handoff_expiry_and_first_telegram_user_binding(self):
        token=self.service.handoff(self.data,self.user)
        self.assertLessEqual(len('or_'+token),64)
        data=self.repo.redeem_draft(token,'telegram:42')
        self.assertEqual(data['model'],'kia-k5')
        self.assertEqual(data['contact']['phone'],'+380990000000')
        self.assertEqual(self.repo.redeem_draft(token,'telegram:42'),data)
        with self.assertRaises(NotFound): self.repo.redeem_draft(token,'telegram:43')
        self.now+=1800
        with self.assertRaises(NotFound): self.repo.redeem_draft(token,'telegram:42')
        self.assertEqual(self.count('order_requests'),0)

    def test_receipt_authorization(self):
        first=self.service.submit(self.data,self.user)
        self.assertEqual(self.repo.receipt_for_owner(self.data['request_id'],self.user.owner),first)
        with self.assertRaises(NotFound): self.repo.receipt_for_owner(self.data['request_id'],'web:someone')

    def test_no_inventory_tables_or_modified_existing_database(self):
        self.service.submit(self.data,self.user)
        with self.repo.connection() as db:
            names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('cars',names);self.assertNotIn('clients',names)
        other=Path(self.tmp.name)/'other';other.mkdir()
        p=other/'order_requests.db'
        with sqlite3.connect(p) as db: db.execute('CREATE TABLE cars(id INTEGER)')
        before=p.read_bytes()
        with self.assertRaises(ValueError): Repository(p).initialize()
        self.assertEqual(p.read_bytes(),before)

    def test_crm_flat_list_pagination_and_html_escape(self):
        for index in range(22):
            self.service.submit(dict(self.data,request_id=str(uuid4()),customer_name=f'<Name {index}>'),self.user)
        view=list_view(self.repo,self.catalog)
        self.assertEqual(len(view['buttons']),22)
        self.assertIn('Name 21',view['buttons'][0][0][0])
        self.assertTrue(all('model' not in b[1] for row in view['buttons'] for b in row))
        text=detail_view(self.repo.detail(22),self.catalog)['text']
        self.assertIn('&lt;Name 21&gt;',text);self.assertNotIn('<Name',text)

    def test_contract_rejects_invalid_and_server_fields(self):
        changes=[{'channel':'site'}, {'source_event_id':'forged'}, {'delivery_city':'x'},
                 {'purchase_country_code':'unknown'}, {'model':'lexus-tx'},
                 {'other_model':'Mercedes'}, {'customer_name':5}, {'contact':{}},
                 {'consent':{'accepted':False,'version':'test-consent-v1'}},
                 {'lang':'ge'}, {'source_path':'https://bad.example'}, {'comment':'x'*2001}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(Invalid):
                self.service.submit(dict(self.data,**change),self.user)
        self.assertEqual(self.count('order_requests'),0)

    def test_strict_json_rejects_duplicate_oversize_and_nonobjects(self):
        for raw in (b'{"t":1,"t":2}',b'{}'*9000,b'[]',b'{"a":NaN}'):
            with self.assertRaises(Invalid):decode(raw)

    def test_legacy_is_draft_preserves_comment_once(self):
        result=draft({'t':'podbor','s':'korea','b':'b2','k':'k1','m':'',
                      'mo':'Kia K5 · хочет: hello','txt':'hello'},self.catalog)
        self.assertEqual(result['model'],'kia-k5');self.assertEqual(result['comment'],'hello')
        self.assertNotIn('hello',result['other_model'])
        self.assertNotIn('consent',result)
        self.assertEqual(self.count('order_requests'),0)
        with self.assertRaises(Invalid): self.service.submit(result,self.user)
        with self.assertRaises(Invalid): draft({'t':'podbor','s':'korea','m':'Kia K5','mo':'Toyota'},self.catalog)

    def test_all_old_country_links_and_no_silent_country_fallback(self):
        for country in COUNTRIES:
            self.assertEqual(deep_link('z_'+country+'_b2_k1')['purchase_country_code'],country)
        self.assertIsNone(deep_link('z_nope'))
        self.assertIsNone(deep_link('z_korea_b99'))


class AuthTest(unittest.TestCase):
    def test_signed_telegram_data_tampering_expiry_and_duplicates(self):
        token='test-bot-token'
        values={'auth_date':'1000','user':json.dumps({'id':42}),'query_id':'test'}
        secret=hmac.digest(b'WebAppData',token.encode(),'sha256')
        sig=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(values.items())).encode(),hashlib.sha256).hexdigest()
        raw=urlencode(dict(values,hash=sig))
        self.assertEqual(telegram_user(raw,token,now=1020),42)
        for bad,now in ((raw.replace('1000','2000'),1020),(raw,10000),(raw+'&auth_date=1000',1020)):
            with self.assertRaises(Unauthorized): telegram_user(bad,token,now=now)

    def test_web_session_csrf_tampering_and_expiry(self):
        now=[1000];auth=WebSessions(b'x'*32,clock=lambda:now[0])
        cookie=auth.create();self.assertTrue(auth.verify(cookie).startswith('web:'))
        auth.check_csrf(cookie,auth.csrf(cookie))
        with self.assertRaises(Unauthorized):auth.check_csrf(cookie,'bad')
        with self.assertRaises(Unauthorized):auth.verify(cookie+'x')
        now[0]+=86401
        with self.assertRaises(Unauthorized):auth.verify(cookie)


class WebTest(OrderFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.auth=WebSessions(b'only-for-tests___________________')
        self.cookie=self.auth.create()
        self.api=WebAdapter(self.service,self.auth,origin='https://example.test',
                            consent_text={k:'TEST CONSENT' for k in ('uk','ru','ka')},
                            allow_request=lambda e,p:True)

    def call(self,path='/api/orders/submit',**overrides):
        raw=json.dumps(self.data).encode()
        env=dict(PATH_INFO=path,REQUEST_METHOD='POST',CONTENT_TYPE='application/json',
                 CONTENT_LENGTH=str(len(raw)),HTTP_ORIGIN='https://example.test',
                 HTTP_COOKIE='ua_order_session='+self.cookie,HTTP_X_CSRF_TOKEN=self.auth.csrf(self.cookie))
        env['wsgi.input']=io.BytesIO(raw);env.update(overrides)
        result=[]
        body=b''.join(self.api(env,lambda s,h:result.append((s,h))))
        return int(result[0][0].split()[0]),json.loads(body),dict(result[0][1])

    def test_http_commit_conflict_origin_csrf_and_limits(self):
        status,result,headers=self.call()
        self.assertEqual(status,200);self.assertEqual(result['status'],'saved')
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.data['comment']='edited'
        self.assertEqual(self.call()[0],409)
        self.assertEqual(self.call(HTTP_ORIGIN='https://other.test')[0],403)
        self.assertEqual(self.call(HTTP_X_CSRF_TOKEN='bad')[0],403)
        self.assertEqual(self.call(CONTENT_LENGTH='20000')[0],413)

    def test_http_receipt_does_not_expose_foreign_request(self):
        self.call()
        self.cookie=self.auth.create()
        status,_,_=self.call('/api/orders/receipt',REQUEST_METHOD='GET',QUERY_STRING='request_id='+self.data['request_id'])
        self.assertEqual(status,404)

    def test_miniapp_receipt_uses_verified_telegram_identity_after_reload(self):
        token='test-bot-token'
        self.api.bot_token=token
        values={'auth_date':str(int(time.time())),'user':json.dumps({'id':42})}
        secret=hmac.digest(b'WebAppData',token.encode(),'sha256')
        signature=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(values.items())).encode(),hashlib.sha256).hexdigest()
        init_data=urlencode(dict(values,hash=signature))
        status,receipt,_=self.call(HTTP_X_TELEGRAM_INIT_DATA=init_data)
        self.assertEqual(status,200)
        query='request_id='+self.data['request_id']
        self.assertEqual(self.call('/api/orders/receipt',REQUEST_METHOD='GET',QUERY_STRING=query)[0],404)
        status,recovered,_=self.call('/api/orders/receipt',REQUEST_METHOD='GET',QUERY_STRING=query,
                                     HTTP_X_TELEGRAM_INIT_DATA=init_data)
        self.assertEqual(status,200);self.assertEqual(recovered,receipt)


if __name__=='__main__': unittest.main()
