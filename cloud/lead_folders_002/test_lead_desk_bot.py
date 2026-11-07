#!/usr/bin/env python3
"""The client bot conversation of «Оформить договор» with a fake Telegram (runs where python-telegram-bot is
installed, as on the server; skipped otherwise)."""
import asyncio
import tempfile
import unittest
from types import SimpleNamespace

try:
    from telegram.ext import ApplicationHandlerStop
except ImportError:  # pragma: no cover - the CI image has no telegram library
    ApplicationHandlerStop = None

import test_lead_folders as base
import ua_contract_files as files
import ua_lead_desk
from ua_lead_desk_store import CONTRACT


class Message:
    def __init__(self, text=None, document=None, photo=None):
        self.text, self.document, self.photo, self.replies = text, document, photo, []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs.get('reply_markup')))


class Query:
    def __init__(self, data, message):
        self.data, self.message, self.edits = data, message, []

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)


class TelegramFile:
    async def download_as_bytearray(self):
        return bytearray(b'%PDF-1.7 contract')


class Bot:
    async def get_file(self, file_id):
        return TelegramFile()


@unittest.skipIf(ApplicationHandlerStop is None, 'python-telegram-bot is not installed')
class ContractConversation(unittest.TestCase):
    def setUp(self):
        flow = base.DeskFlow('test_status_and_note')
        flow.setUp()
        self.desk, self.book, self.store = flow.desk, flow.book, flow.store
        self.context = SimpleNamespace(user_data={}, bot=Bot())
        self.user = SimpleNamespace(id=7)

    def press(self, data):
        message = Message()
        query = Query(data, message)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(self.desk.callback(SimpleNamespace(callback_query=query, effective_user=self.user), self.context))
        return query, message

    def send(self, message):
        update = SimpleNamespace(effective_message=message, effective_user=self.user)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(self.desk.message(update, self.context))
        return message

    def test_number_file_confirm(self):
        _, asked = self.press('ld:contract:or:2')
        self.assertIn('Шаг 1 из 3', asked.replies[0][0])
        self.assertIn('Шаг 2 из 3', self.send(Message(text='  12/2026 ')).replies[0][0])
        self.assertIn('Нужен файл', self.send(Message(text='не файл')).replies[0][0])
        document = SimpleNamespace(file_name='Договор.pdf', mime_type='application/pdf', file_size=20, file_id='f')
        confirm = self.send(Message(document=document)).replies[0][0]
        self.assertIn('Договор №</b> 12/2026', confirm)
        query, _ = self.press('ld:ok:or:2')
        self.assertIn('✅ Заказ оформлен: договор № 12/2026, Олена.', query.edits[0])
        order = self.book.all()[0]
        self.assertEqual((order['folder'], order['contract_no']), ('korea', '12/2026'))
        self.assertEqual(files.path(order['contract_file'], root=self.desk.files_root).read_bytes(), b'%PDF-1.7 contract')
        self.assertEqual(self.store.get('or:2')['status'], CONTRACT)

    def test_confirm_without_steps_refused(self):
        query, _ = self.press('ld:ok:or:2')
        self.assertEqual(query.edits, ['Лид не найден'])
        self.assertEqual(self.book.all(), [])

    def test_other_message_passes_on(self):
        update = SimpleNamespace(effective_message=Message(text='привет'), effective_user=self.user)
        self.assertIsNone(asyncio.run(self.desk.message(update, self.context)))

    def test_pending_only_while_a_step_waits(self):
        app = SimpleNamespace(user_data={7: {}})
        self.assertFalse(ua_lead_desk.pending(app, 7))
        self.press('ld:contract:or:2')
        app.user_data[7] = self.context.user_data
        self.assertTrue(ua_lead_desk.pending(app, 7))
        self.assertFalse(ua_lead_desk.pending(app, 8))

    def test_stranger_refused(self):
        self.desk.authorize = lambda update: False
        query = Query('ld:home', Message())
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(self.desk.callback(SimpleNamespace(callback_query=query, effective_user=self.user), self.context))
        self.assertEqual(query.edits, [])


if __name__ == '__main__':
    unittest.main()
