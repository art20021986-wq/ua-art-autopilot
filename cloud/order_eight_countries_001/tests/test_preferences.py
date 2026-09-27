"""V2 intake uses the real contract, WSGI boundary, repository and bot adapters."""
import copy
from datetime import datetime, timezone
from html import unescape
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from ua_order import bot_flow, bindings, crm, preferences
from ua_order.contract import Invalid, decode, digest, normalize
from ua_order.preference_summary import split_text
from ua_order.service import Principal
from ua_order.telegram import CustomerAdapter, CRMAdapter
from ua_order.auth import WebSessions
from ua_order.web import WebAdapter
from test_orders import OrderFixture
from test_bot import ROOT, STRINGS, CONSENT


def sample(catalog):
    return dict(schema_version=preferences.SCHEMA,request_id=str(uuid4()),config_version=catalog.version,
        preferences_version=preferences.directory()['version'],purchase_country_code='korea',purchase_country_other='',
        make='kia',make_other='',model_mode='selected',models=['K5','Sportage'],other_model='',
        budget=dict(mode='limit',max=20000,currency='USD'),vehicle_type='sedan',
        delivery_country='ukraine',delivery_city=dict(code='kyiv',other=''),customer_name='Тестовый клиент',
        contact=dict(method='telegram',value='@test_user'),year={'from':2015,'to':2022,'any':False},
        mileage=dict(max='109 353',any=False),fuel=['petrol','hybrid'],drive=['fwd'],engine={'from':1.5,'to':2.5},
        colours=['white','other'],colour_other='',purchase_timing='quarter',comment='Нужен белый автомобиль. https://example.test/car',
        priority={'year':'required','colours':'preferred'},lang='ru',source_path='/video/podbor.html',
        consent=dict(accepted=True,version='company-existing-v1'))


class PreferencesTest(OrderFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.data=sample(self.catalog);self.data['consent']['version']=self.service.consent_version

    def test_every_card_and_brand_has_consistent_structured_mapping(self):
        directory=preferences.directory()
        self.assertEqual(len(directory['makes']),68)
        self.assertGreater(sum(len(m['models']) for m in directory['makes'].values()),1200)
        for code,country in self.catalog.export()['countries'].items():
            for card in country['models']:
                preset=directory['card_presets'][card['key']]
                if card['key']=='classics-1980-1990':
                    self.assertNotIn('make',preset);self.assertEqual(preset['year']['from'],1980)
                else:
                    for model in preset['models']:self.assertIn(model,directory['makes'][preset['make']]['models'])
                self.assertFalse(set(preset)&{'budget','mileage','colours','delivery_country','customer_name'})
        self.assertEqual(set(directory['labels']['ru']),set(directory['labels']['uk']))
        self.assertEqual(set(directory['labels']['ru']),set(directory['labels']['ka']))

    def test_roundtrip_final_values_and_idempotent_retry(self):
        self.data.update(make='toyota',models=['Camry'])
        actor=Principal('web:test','site')
        first=self.service.submit(self.data,actor);second=self.service.submit(self.data,actor)
        self.assertEqual(first,second)
        stored=self.repo.detail(1)['data']
        self.assertEqual(stored['make'],'toyota');self.assertEqual(stored['mileage']['max'],109353)
        self.assertEqual(stored['colours'],['white','other'])
        self.assertEqual(stored['priority']['year'],'required')
        self.assertEqual(self.count('order_requests'),1);self.assertEqual(self.count('order_outbox'),1)

    def test_required_explicit_any_and_optional_empty(self):
        self.data.update(purchase_country_code='help',make='help',models=[],model_mode='help',
            budget=dict(mode='help',max=None,currency='USD'),vehicle_type='any',
            year={'from':None,'to':None,'any':True},mileage=dict(max=None,any=True),
            fuel=None,drive=None,engine=None,colours=None,purchase_timing=None,comment='')
        clean=self.service.normalize(self.data,Principal('web:test','site'))
        self.assertEqual(clean['priority'],{})
        for field in ('fuel','drive','engine','colours','purchase_timing'):self.assertIsNone(clean[field])
        for field,value in [('purchase_country_code',''),('make',''),('vehicle_type',''),('customer_name',''),('delivery_country','')]:
            bad=copy.deepcopy(self.data);bad[field]=value
            with self.subTest(field=field),self.assertRaises(Invalid):self.service.normalize(bad,Principal('web:test','site'))

    def test_manual_country_model_city_and_optional_other_colour(self):
        self.data.update(purchase_country_code='other',purchase_country_other='Швейцария',make='other',make_other='Morgan',model_mode='other',models=[],other_model='Plus Four',delivery_country='georgia',delivery_city={'code':'other','other':'Боржоми'})
        saved=self.service.submit(self.data,Principal('web:test','site'))
        view=crm.detail_view(self.repo.detail(1),self.catalog)
        for value in ['Швейцария','Morgan','Plus Four','Боржоми','Уточнить',saved['number']]:self.assertIn(value,view['text'])
        listing=crm.list_view(self.repo,self.catalog,menu_callback='v_start')
        self.assertIn('Швейцария',listing['buttons'][0][0][0])
        self.assertEqual(listing['buttons'][-1][-1][1],'v_start')

    def test_reject_invalid_ranges_enums_contacts_and_forged_fields(self):
        mutations=[('models',['Camry']),('models',['K5','K5']),('purchase_country_code','mars'),
            ('year',{'from':2023,'to':2020,'any':False}),('year',{'from':None,'to':None,'any':False}),
            ('year',{'from':datetime.now(timezone.utc).year+1,'to':None,'any':False}),
            ('mileage',{'max':109,'any':True}),('mileage',{'max':5000001,'any':False}),
            ('engine',{'from':0,'to':2}),('engine',{'from':2.123,'to':None}),
            ('fuel',['petrol','any']),('fuel',['electric']),('drive',['4WD']),
            ('delivery_country','usa'),('delivery_city',{'code':'tbilisi','other':''}),
            ('contact',{'method':'phone','value':'0991234567'}),('contact',{'method':'telegram','value':'@a'}),
            ('priority',{'condition':'required'}),('comment','x'*3001),('consent',{'accepted':1,'version':self.service.consent_version})]
        for field,value in mutations:
            bad=copy.deepcopy(self.data);bad[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(Invalid):normalize(bad,self.catalog,self.service.consent_version)
        bad=dict(self.data,condition='new')
        with self.assertRaises(Invalid):normalize(bad,self.catalog,self.service.consent_version)
        self.assertEqual(self.count('order_requests'),0)

    def test_mileage_exact_units_and_grouping(self):
        for value in ['109353','109 353','109.353','109,353','109\u00a0353','109\u202f353',109353]:self.assertEqual(preferences.integer(value,'mileage'),109353)
        for value in ['109.3','109,35','1 09 353','1.000,000','-1',True,float('nan'),[],{}]:
            with self.subTest(value=value),self.assertRaises(Invalid):preferences.integer(value,'mileage')
        self.assertEqual(preferences.integer('109','mileage'),109)
        self.assertEqual(preferences.integer('0','mileage'),0)

    def test_unicode_long_summaries_escape_without_truncation(self):
        self.data['comment']='<b>не HTML</b> '+('🚗'*2985)
        self.service.submit(self.data,Principal('web:test','site'));view=crm.detail_view(self.repo.detail(1),self.catalog)
        self.assertGreater(len(view['parts']),1)
        self.assertIn('&lt;b&gt;',view['text']);self.assertNotIn('<b>не HTML',view['text'])
        joined=''.join(unescape(p).split('\n',1)[1] for p in view['parts'])
        self.assertEqual(joined,unescape(view['text']))
        self.assertTrue(all(len(unescape(p).encode('utf-16-le'))//2<=4096 for p in view['parts']))
        for lang in ('ru','uk','ka'):
            draft=bot_flow.create(self.catalog,data=self.repo.detail(1)['data']);draft['step']='review';draft['data']['lang']=lang
            result=bot_flow.view(draft,self.catalog,STRINGS,CONSENT)
            self.assertEqual(''.join(result['parts']),result['text'])
            self.assertTrue(all(len(p.encode('utf-16-le'))//2<=4096 for p in result['parts']))

    def test_server_errors_keep_field_name_and_no_side_effects(self):
        sessions=WebSessions(b'offline-preference-session-secret');cookie=sessions.create()
        api=WebAdapter(self.service,sessions,origin='https://example.test',consent_text=CONSENT,allow_request=lambda *_:True)
        self.data['year']['from']=2030;raw=json.dumps(self.data).encode();status=[]
        env=dict(PATH_INFO='/api/orders/submit',REQUEST_METHOD='POST',CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(raw)),HTTP_ORIGIN='https://example.test',HTTP_COOKIE='ua_order_session='+cookie,HTTP_X_CSRF_TOKEN=sessions.csrf(cookie))
        env['wsgi.input']=io.BytesIO(raw)
        result=json.loads(b''.join(api(env,lambda s,h:status.append(s))))
        self.assertEqual(status,['400 Bad Request']);self.assertEqual(result['field'],'year');self.assertEqual(self.count('order_requests'),0)


class PreferencesHandoffTest(OrderFixture,unittest.IsolatedAsyncioTestCase):
    async def test_complete_v2_handoff_review_edit_confirm_and_owner_inbox(self):
        from telegram.ext import ApplicationHandlerStop
        data=sample(self.catalog);data['consent']['version']=self.service.consent_version;data['comment']='🚗'*3000
        token=self.service.handoff(data,Principal('web:test','site'))
        bot=SimpleNamespace(id=456,send_message=AsyncMock(return_value=SimpleNamespace(message_id=20)),edit_message_text=AsyncMock(),delete_message=AsyncMock())
        context=SimpleNamespace(user_data={},bot_data={},bot=bot)
        update=SimpleNamespace(effective_user=SimpleNamespace(id=123),effective_chat=SimpleNamespace(id=123,type='private'),effective_message=SimpleNamespace(text='/start or_'+token),callback_query=None,update_id=91)
        adapter=CustomerAdapter(self.service,STRINGS,CONSENT,media_root=ROOT/'web',allow_update=lambda _:True)
        with self.assertRaises(ApplicationHandlerStop):await adapter.start(update,context)
        state=context.user_data['order_flow'];self.assertEqual(state['data']['schema_version'],preferences.SCHEMA)
        self.assertEqual(state['data']['comment'],data['comment']);self.assertNotIn('other_model_extra',state['data'])
        original=copy.deepcopy(state['data'])
        bot_flow.transition(state,'edit','',self.catalog);self.assertEqual(state['step'],'edit_web')
        bot_flow.transition(state,'back','',self.catalog);self.assertEqual(state['data'],original)
        update.callback_query=SimpleNamespace(data=bot_flow.callback(state,'submit'),answer=AsyncMock());update.update_id=92
        with self.assertRaises(ApplicationHandlerStop):await adapter.callback(update,context)
        with self.assertRaises(ApplicationHandlerStop):await adapter.callback(update,context)
        self.assertEqual(self.count('order_requests'),1)
        self.assertEqual(self.repo.detail(1)['data'],original)
        jobs=[];client=SimpleNamespace(handlers={},bot=SimpleNamespace(send_message=AsyncMock()),job_queue=SimpleNamespace(get_jobs_by_name=lambda _:[],run_repeating=lambda fn,**kw:jobs.append(fn)))
        client.add_handler=lambda handler,group:client.handlers.setdefault(group,[]).append(handler)
        runtime=SimpleNamespace(service=self.service)
        inbox=bindings.owner_inbox(client,runtime,owner_id=789)
        self.assertFalse(inbox.authorize(update));update.effective_user.id=789;update.effective_chat.id=789;self.assertTrue(inbox.authorize(update))
        await jobs[0](None)
        calls=client.bot.send_message.call_args_list;self.assertGreater(len(calls),1)
        self.assertEqual({call.kwargs['chat_id'] for call in calls},{789})
        self.assertTrue(calls[-1].kwargs['reply_markup'])
        self.assertEqual(self.repo.notification_recipients_sent(original['request_id']),{789})
        await jobs[0](None);self.assertEqual(len(client.bot.send_message.call_args_list),len(calls))


if __name__=='__main__':unittest.main()
