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

    def inbox_app(self):
        jobs = []
        app = SimpleNamespace(handlers={-3: []},
            job_queue=SimpleNamespace(get_jobs_by_name=lambda _: [],
                run_repeating=lambda fn, **kw: jobs.append((fn, kw))),
            bot=SimpleNamespace(send_message=AsyncMock()))
        app.add_handler = lambda handler, group: app.handlers.setdefault(group, []).append(handler)
        adapter = bindings.owner_inbox(app, self.runtime(), owner_id='789')
        return app, adapter, jobs

    async def test_owner_only_private_folder_contains_existing_request(self):
        self.service.submit(self.data, Principal('telegram:123', 'telegram_bot'))
        app, adapter, jobs = self.inbox_app()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=789),
            effective_chat=SimpleNamespace(id=789, type='private'),
            callback_query=SimpleNamespace(data='orders:list', answer=AsyncMock()))
        context = SimpleNamespace(bot=app.bot, user_data={})
        with self.assertRaises(ApplicationHandlerStop):
            await adapter.callback(update, context)
        rows = app.bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard
        self.assertEqual(rows[0][0].callback_data, 'orders:open:1')
        self.assertEqual(rows[-1][-1].callback_data, 'v_start')
        self.assertEqual(self.count('order_requests'), 1)
        app.bot.send_message.reset_mock()
        for user, chat, kind in ((123,123,'private'), (789,-1,'group'), (789,123,'private')):
            update.effective_user.id, update.effective_chat.id, update.effective_chat.type = user, chat, kind
            for callback in ('orders:list', 'orders:open:1'):
                update.callback_query.data = callback
                with self.assertRaises(ApplicationHandlerStop):
                    await adapter.callback(update, context)
                update.callback_query.answer.assert_awaited_with('Недостаточно прав', show_alert=True)
        app.bot.send_message.assert_not_awaited()

    async def test_client_owner_delivery_retries_and_does_not_repeat_receipt(self):
        receipt = self.service.submit(self.data, Principal('telegram:123', 'telegram_bot'))
        app, adapter, jobs = self.inbox_app()
        self.assertEqual(jobs[0][1]['name'], bindings.JOB_NAME)
        app.bot.send_message.side_effect = TimeoutError('offline failure')
        with self.assertRaises(TimeoutError):
            await jobs[0][0](None)
        with self.repo.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM order_outbox').fetchone()[0], 'pending')
            db.execute('UPDATE order_outbox SET available_at=0')
        app.bot.send_message.side_effect = None
        await jobs[0][0](None)
        options = app.bot.send_message.call_args.kwargs
        self.assertEqual(options['chat_id'], 789)
        self.assertIn(receipt['number'], options['text'])
        self.assertEqual(options['reply_markup'].inline_keyboard[0][0].callback_data, 'orders:open:1')
        with self.repo.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM order_outbox').fetchone()[0], 'sent')
            # Recover after a crash between recipient receipt and outbox commit.
            db.execute("UPDATE order_outbox SET state='pending', available_at=0")
        app.bot.send_message.reset_mock()
        await jobs[0][0](None)
        app.bot.send_message.assert_not_awaited()

    def test_duplicate_delivery_job_and_group_owner_are_rejected(self):
        app, adapter, jobs = self.inbox_app()
        app.job_queue.get_jobs_by_name = lambda _: [object()]
        with self.assertRaisesRegex(ValueError, 'already registered'):
            bindings.owner_inbox(app, self.runtime(), owner_id=789)
        with self.assertRaisesRegex(ValueError, 'private owner'):
            bindings.owner_inbox(app, self.runtime(), owner_id=-789)


if __name__ == '__main__':
    unittest.main()
