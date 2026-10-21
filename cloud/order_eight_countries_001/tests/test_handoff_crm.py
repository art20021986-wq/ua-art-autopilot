"""One real adapter chain, with temporary storage and no external messages."""
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from telegram.ext import ApplicationHandlerStop

from ua_order import bot_flow
from ua_order.auth import WebSessions
from ua_order.notifications import dispatch_once
from ua_order.telegram import CRMAdapter, CustomerAdapter
from ua_order.web import WebAdapter
from test_bot import CONSENT, ROOT, STRINGS
from test_orders import OrderFixture


class HandoffCRMTest(OrderFixture, unittest.IsolatedAsyncioTestCase):
    async def test_web_draft_bot_confirmation_flat_crm_and_outbox(self):
        sessions=WebSessions(b'test-session-key-not-production!!')
        cookie=sessions.create()
        api=WebAdapter(self.service,sessions,origin='https://example.test',
                       consent_text=CONSENT,allow_request=lambda env,actor:True)
        raw=json.dumps(self.data).encode()
        env=dict(PATH_INFO='/api/orders/handoff',REQUEST_METHOD='POST',
                 CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(raw)),
                 HTTP_ORIGIN='https://example.test',HTTP_COOKIE='ua_order_session='+cookie,
                 HTTP_X_CSRF_TOKEN=sessions.csrf(cookie))
        env['wsgi.input']=io.BytesIO(raw)
        responses=[]
        body=b''.join(api(env,lambda status,headers:responses.append(status)))
        self.assertEqual(responses,['200 OK'])
        start=parse_qs(urlparse(json.loads(body)['url']).query)['start'][0]
        self.assertEqual(self.count('order_requests'),0)

        # Only Telegram's verified update identity binds the draft to this user.
        bot=SimpleNamespace(id=456,send_message=AsyncMock(return_value=SimpleNamespace(message_id=20)),
                            edit_message_text=AsyncMock())
        context=SimpleNamespace(user_data={},bot_data={},bot=bot)
        update=SimpleNamespace(effective_user=SimpleNamespace(id=123),
                               effective_chat=SimpleNamespace(id=123,type='private'),
                               effective_message=SimpleNamespace(text='/start '+start),
                               callback_query=None,update_id=91)
        customer=CustomerAdapter(self.service,STRINGS,CONSENT,media_root=ROOT/'web',
                                 allow_update=lambda _:True)
        with self.assertRaises(ApplicationHandlerStop):await customer.start(update,context)
        state=context.user_data['order_flow']
        self.assertEqual(state['step'],'review')
        self.assertEqual(state['data']['model'],self.data['model'])
        self.assertEqual(state['data']['comment'],self.data['comment'])
        self.assertEqual(state['data']['delivery_city'],self.data['delivery_city'])
        self.assertEqual(self.count('order_requests'),0)

        update.update_id=92
        update.callback_query=SimpleNamespace(data=bot_flow.callback(state,'submit'),answer=AsyncMock())
        with self.assertRaises(ApplicationHandlerStop):await customer.callback(update,context)
        receipt=state['receipt']
        with self.assertRaises(ApplicationHandlerStop):await customer.callback(update,context)
        self.assertEqual(self.count('order_requests'),1)
        self.assertEqual(self.count('order_outbox'),1)

        crm_bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=30)),
                                edit_message_text=AsyncMock())
        staff_context=SimpleNamespace(user_data={},bot=crm_bot)
        staff=SimpleNamespace(effective_user=SimpleNamespace(id=789),
                              effective_chat=SimpleNamespace(id=789),
                              callback_query=SimpleNamespace(data='orders:list',answer=AsyncMock()))
        crm=CRMAdapter(self.repo,self.catalog,authorize=lambda update:update.effective_user.id==789)
        with self.assertRaises(ApplicationHandlerStop):await crm.callback(staff,staff_context)
        menu=crm_bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard
        self.assertEqual(menu[0][0].text,self.data['customer_name']+' · '+self.catalog.country('korea')['name']['ru'])
        self.assertTrue(menu[0][0].callback_data.startswith('orders:open:'))
        staff.callback_query.data=menu[0][0].callback_data
        with self.assertRaises(ApplicationHandlerStop):await crm.callback(staff,staff_context)
        detail=crm_bot.edit_message_text.call_args.kwargs['text']
        self.assertIn(receipt['number'],detail)
        self.assertIn(self.data['comment'],detail)
        self.assertIn('+380990000000',detail)

        deliver=AsyncMock()
        self.assertTrue(await dispatch_once(self.repo,deliver))
        self.assertFalse(await dispatch_once(self.repo,deliver))
        deliver.assert_awaited_once()
        self.assertEqual(deliver.call_args.args[0]['number'],receipt['number'])
        self.assertEqual(deliver.call_args.args[0]['telegram_user_id'],'123')
        self.assertEqual(self.count('order_requests'),1)


if __name__=='__main__':unittest.main()
