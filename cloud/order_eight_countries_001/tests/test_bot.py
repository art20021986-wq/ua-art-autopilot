import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from ua_order import bot_flow
from ua_order.catalog import COUNTRIES
from ua_order.contract import Invalid
from ua_order.telegram import CustomerAdapter, CRMAdapter, _menu
from test_orders import OrderFixture

ROOT=Path(__file__).resolve().parents[1]
STRINGS=json.loads((ROOT/'strings.json').read_text())
CONSENT={k:'TEST CONSENT ONLY' for k in ('uk','ru','ka')}


class BotFlowTest(OrderFixture,unittest.TestCase):
    def test_country_model_photo_budget_and_back_preserve_independent_fields(self):
        state=bot_flow.create(self.catalog,data={'delivery_city':'Київ'})
        menu=bot_flow.view(state,self.catalog,STRINGS,CONSENT)
        self.assertEqual([len(r) for r in menu['buttons'][:4]],[2,2,2,2])
        bot_flow.transition(state,'country','korea',self.catalog)
        bot_flow.transition(state,'model','0',self.catalog)
        self.assertEqual(state['data']['model'],'kia-k5')
        bot_flow.transition(state,'back','',self.catalog)
        bot_flow.transition(state,'back','',self.catalog)
        bot_flow.transition(state,'country','georgia',self.catalog)
        self.assertEqual(state['data']['model'],'')
        self.assertEqual(state['data']['delivery_city'],'Київ')
        self.assertEqual(state['data']['purchase_country_code'],'georgia')

    def test_all_country_model_language_callbacks_fit_telegram_limit(self):
        for country in COUNTRIES:
            for lang in ('uk','ru','ka'):
                state=bot_flow.create(self.catalog,data={'lang':lang})
                bot_flow.transition(state,'country',country,self.catalog)
                view=bot_flow.view(state,self.catalog,STRINGS,CONSENT)
                self.assertEqual(len(view['buttons'][:5]),5)
                for row in view['buttons']:
                    for label,callback in row:
                        self.assertTrue(label);self.assertLessEqual(len(callback.encode()),64)
                for index in range(5):
                    sample=bot_flow.create(self.catalog,data={'lang':lang,'purchase_country_code':country})
                    sample['step']='models';bot_flow.transition(sample,'model',str(index),self.catalog)
                    self.assertEqual(sample['step'],'photo')
                    self.assertTrue(bot_flow.view(sample,self.catalog,STRINGS,CONSENT)['text'])

    def test_complete_native_bot_flow_saves_one_request(self):
        state=bot_flow.create(self.catalog)
        for action,value in [('country','canada'),('model','2'),('select',''),('budget','b2'),('type','k2')]:
            bot_flow.transition(state,action,value,self.catalog)
        for value in ('Україна','Київ','Тестовий клієнт','@test_user','Потрібна консультація'):
            bot_flow.enter_text(state,value)
        self.assertEqual(state['step'],'review')
        from ua_order.service import Principal
        payload=dict(state['data'],consent={'accepted':True,'version':'test-consent-v1'})
        receipt=self.service.submit(payload,Principal('telegram:123','telegram_bot'))
        state['receipt']=receipt
        self.assertIn(receipt['number'],bot_flow.view(state,self.catalog,STRINGS,CONSENT)['text'])
        self.assertEqual(self.count('order_requests'),1)


class TelegramAdapterTest(OrderFixture,unittest.IsolatedAsyncioTestCase):
    async def test_existing_library_registration_no_network(self):
        from telegram.ext import Application
        from telegram.request import BaseRequest
        class NoNetwork(BaseRequest):
            @property
            def read_timeout(self): return 0
            async def initialize(self): pass
            async def shutdown(self): pass
            async def do_request(self,*args,**kwargs): raise AssertionError('No real Telegram calls in tests')
        app=Application.builder().token('123456:local-test-no-network').request(NoNetwork()).get_updates_request(NoNetwork()).build()
        adapter=CustomerAdapter(self.service,STRINGS,CONSENT,media_root=ROOT/'web',allow_update=lambda _:True)
        adapter.register(app,group=-21)
        self.assertIn(-21,app.handlers)
        with self.assertRaises(ValueError):adapter.register(app,group=-21)

    async def test_crm_denied_before_reading_database(self):
        from telegram.ext import ApplicationHandlerStop
        query=SimpleNamespace(answer=AsyncMock(),data='orders:list')
        repo=SimpleNamespace(list_requests=lambda **_:self.fail('Unauthorized DB read'))
        adapter=CRMAdapter(repo,self.catalog,authorize=lambda _:False)
        with self.assertRaises(ApplicationHandlerStop):
            await adapter.callback(SimpleNamespace(callback_query=query),SimpleNamespace())
        query.answer.assert_awaited_once_with('Недостаточно прав',show_alert=True)

    async def test_refresh_edits_and_deleted_menu_is_recreated_once(self):
        from telegram.error import BadRequest
        bot=SimpleNamespace(edit_message_text=AsyncMock(),send_message=AsyncMock(return_value=SimpleNamespace(message_id=45)))
        context=SimpleNamespace(user_data={'menu':12})
        view={'text':'Авто под заказ','buttons':[[('Обновить','orders:list')]]}
        await _menu(bot,123,context,'menu',view)
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.side_effect=BadRequest('Message to edit not found')
        await _menu(bot,123,context,'menu',view)
        self.assertEqual(context.user_data['menu'],45)
        bot.send_message.assert_awaited_once()

    async def test_stale_callback_does_not_modify_draft(self):
        from telegram.ext import ApplicationHandlerStop
        state=bot_flow.create(self.catalog)
        context=SimpleNamespace(user_data={'order_flow':state},bot=SimpleNamespace(id=456,send_message=AsyncMock()))
        query=SimpleNamespace(answer=AsyncMock(),data='ord:bad:0:country:canada')
        update=SimpleNamespace(callback_query=query,effective_user=SimpleNamespace(id=123),
                               effective_chat=SimpleNamespace(id=123,type='private'),update_id=99)
        adapter=CustomerAdapter(self.service,STRINGS,CONSENT,media_root=ROOT/'web',allow_update=lambda _:True)
        with self.assertRaises(ApplicationHandlerStop):await adapter.callback(update,context)
        self.assertEqual(state['data']['purchase_country_code'],'')
        self.assertEqual(self.count('order_requests'),0)

    async def test_callback_after_restart_recovers_committed_receipt_for_owner(self):
        from telegram.ext import ApplicationHandlerStop
        from ua_order.service import Principal
        receipt=self.service.submit(self.data,Principal('telegram:123','telegram_bot'))
        context=SimpleNamespace(user_data={},bot=SimpleNamespace(id=456,send_message=AsyncMock()))
        query=SimpleNamespace(answer=AsyncMock(),data=f'ord:{self.data["request_id"]}:9:submit:')
        update=SimpleNamespace(callback_query=query,effective_user=SimpleNamespace(id=123),
                               effective_chat=SimpleNamespace(id=123,type='private'),update_id=101)
        adapter=CustomerAdapter(self.service,STRINGS,CONSENT,media_root=ROOT/'web',allow_update=lambda _:True)
        with self.assertRaises(ApplicationHandlerStop):await adapter.callback(update,context)
        self.assertIn(receipt['number'],context.bot.send_message.call_args.args[1])
        self.assertEqual(self.count('order_requests'),1)


if __name__=='__main__':unittest.main()
