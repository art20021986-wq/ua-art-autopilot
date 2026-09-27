import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler
from telegram.request import BaseRequest

from ua_order import bindings
from ua_order.service import Principal
from test_bot import CONSENT, ROOT, STRINGS
from test_orders import OrderFixture


class OfflineTelegram(BaseRequest):
    @property
    def read_timeout(self):
        return 0

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, **kwargs):
        api = url.rsplit('/', 1)[-1]
        if api == 'getMe':
            result = {'id': 456, 'is_bot': True, 'first_name': 'Offline', 'username': 'offline_bot'}
        elif api == 'answerCallbackQuery':
            result = True
        else:
            raise AssertionError('Unexpected Telegram operation: ' + api)
        return 200, json.dumps({'ok': True, 'result': result}).encode()


def callback_update(app, data, update_id=1):
    return Update.de_json({'update_id': update_id, 'callback_query': {
        'id': str(update_id), 'chat_instance': 'local', 'data': data,
        'from': {'id': 123, 'is_bot': False, 'first_name': 'Test'},
        'message': {'message_id': 1, 'date': 1, 'text': 'menu',
                    'chat': {'id': 123, 'type': 'private'}},
    }}, app.bot)


class BindingTest(OrderFixture, unittest.IsolatedAsyncioTestCase):
    def runtime(self):
        return SimpleNamespace(service=self.service, strings=STRINGS, consent_text=CONSENT,
                               media_root=ROOT/'web', allow_update=lambda _: True)

    async def test_real_dispatcher_old_entries_and_exit_do_not_reach_old_order_flow(self):
        app = (Application.builder().token('456:offline-test').request(OfflineTelegram())
               .get_updates_request(OfflineTelegram()).job_queue(None).build())
        old_calls = []
        async def old(update, context):
            old_calls.append(update.callback_query.data if update.callback_query else update.message.text)
            raise ApplicationHandlerStop
        app.add_handler(CallbackQueryHandler(old), group=-1)
        app.add_handler(CommandHandler('cars', old), group=-1)
        adapter = bindings.customer(app, self.runtime())
        adapter.show = AsyncMock()
        errors = []
        async def error(update, context):
            errors.append(context.error)
        app.add_error_handler(error)
        await app.initialize()
        try:
            for number, entrance in enumerate(('c_order', 'c_ans:budget:выше', 'lead_start',
                                                'buycar:12', 'ready', 'custom_order'), 1):
                await app.process_update(callback_update(app, entrance, number))
                self.assertIn('order_flow', app.user_data[123])
                self.assertEqual(app.user_data[123]['order_flow']['step'], 'country')
            self.assertFalse(old_calls)
            for number, exit_data in enumerate(('c_menu', 'c_cars', 'c_car:12', 'c_bron:12',
                                                'c_vopros:12', 'c_terms', 'c_contacts'), 20):
                await app.process_update(callback_update(app, 'c_order', number*2))
                await app.process_update(callback_update(app, exit_data, number*2+1))
                self.assertNotIn('order_flow', app.user_data[123])
                self.assertEqual(old_calls[-1], exit_data)
            await app.process_update(callback_update(app, 'c_order', 100))
            command = Update.de_json({'update_id': 101, 'message': {
                'message_id': 101, 'date': 1, 'text': '/cars',
                'entities': [{'type': 'bot_command', 'offset': 0, 'length': 5}],
                'from': {'id': 123, 'is_bot': False, 'first_name': 'Test'},
                'chat': {'id': 123, 'type': 'private'},
            }}, app.bot)
            await app.process_update(command)
            self.assertNotIn('order_flow', app.user_data[123])
            self.assertEqual(old_calls[-1], '/cars')
            self.assertFalse(errors, errors)
        finally:
            await app.shutdown()

    async def test_owner_delivery_retry_is_private_and_idempotent(self):
        self.service.submit(self.data, Principal('telegram:123', 'telegram_bot'))
        jobs=[]
        app=SimpleNamespace(handlers={},bot=SimpleNamespace(send_message=AsyncMock()),
            job_queue=SimpleNamespace(get_jobs_by_name=lambda _:[],run_repeating=lambda fn,**kw:jobs.append(fn)))
        app.add_handler=lambda handler,group:app.handlers.setdefault(group,[]).append(handler)
        adapter=bindings.owner_inbox(app,self.runtime(),owner_id=789)
        update=SimpleNamespace(effective_user=SimpleNamespace(id=789),effective_chat=SimpleNamespace(id=789,type='private'))
        self.assertTrue(adapter.authorize(update))
        update.effective_chat.type='group';self.assertFalse(adapter.authorize(update))
        update.effective_chat.type='private';update.effective_user.id=123;self.assertFalse(adapter.authorize(update))
        app.bot.send_message.side_effect=TimeoutError('Offline failure')
        with self.assertRaises(TimeoutError):await jobs[0](None)
        self.assertEqual(self.repo.notification_recipients_sent(self.data['request_id']),set())
        with self.repo.connection() as db:db.execute('UPDATE order_outbox SET available_at=0')
        app.bot.send_message.side_effect=None
        await jobs[0](None);self.assertEqual(self.repo.notification_recipients_sent(self.data['request_id']),{789})
        sent=app.bot.send_message.await_count
        await jobs[0](None);self.assertEqual(app.bot.send_message.await_count,sent)
        self.assertEqual(app.bot.send_message.call_args.kwargs['chat_id'],789)


if __name__=='__main__':unittest.main()
