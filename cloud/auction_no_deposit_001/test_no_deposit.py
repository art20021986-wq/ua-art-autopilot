"""AUCTION-NO-DEPOSIT-001: «Новый клиент аукционов» in 5 steps, no prepayment asked, no «0 $» shown anywhere.

Telegram, the CRM staff table and the other auction modules are stand-ins; the clients table is a temporary file.
"""
import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Stop(Exception):
    """telegram.ext.ApplicationHandlerStop"""


telegram = types.ModuleType('telegram')
telegram.InlineKeyboardButton = lambda text, callback_data=None, url=None: (text, callback_data or url)
telegram.InlineKeyboardMarkup = lambda rows: rows
telegram_ext = types.ModuleType('telegram.ext')
telegram_ext.ApplicationHandlerStop = Stop
telegram_error = types.ModuleType('telegram.error')
telegram_error.BadRequest = type('BadRequest', (Exception,), {})
orders = types.ModuleType('ua_crm_orders')
orders.allowed = lambda update: True
staff_db = types.ModuleType('db')
staff_db.list_staff = lambda active_only=False: [{'user_id': 11, 'full_name': 'Иван', 'username': ''}]
bids = types.ModuleType('ua_auction_bids')  # the installed module; only its error type is used on these paths
bids.BidError = type('BidError', (ValueError,), {})
stats = types.ModuleType('ua_auction_stats')
stats.of_client = lambda phone: []
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db, 'ua_auction_bids': bids, 'ua_auction_stats': stats})

import candidate_builder  # noqa: E402
import ua_auction_clients as store  # noqa: E402
import ua_auction_clients_bot as bot  # noqa: E402
import ua_auction_clients_view as view  # noqa: E402


class Message:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)


class Query:
    def __init__(self, data, message):
        self.data, self.message = data, message

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.message.sent.append(text)


class FormTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(store, 'DB', Path(folder.name) / 'clients.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.context = types.SimpleNamespace(user_data={})
        self.message = Message()

    def update(self, data=None, text=None):
        return types.SimpleNamespace(callback_query=Query(data, self.message) if data else None,
                                     effective_user=types.SimpleNamespace(id=11),
                                     effective_message=types.SimpleNamespace(text=text, reply_text=self.message.reply_text))

    def tap(self, data):
        with self.assertRaises(Stop):
            asyncio.run(bot.callback(self.update(data=data), self.context))

    def say(self, text):
        try:
            asyncio.run(bot.text(self.update(text=text), self.context))
        except Stop:
            pass
        return self.message.sent[-1]

    def test_five_steps_then_saved(self):
        self.assertEqual([field for field, _ in view.STEPS], ['phone', 'surname', 'name', 'email', 'city'])
        self.tap('ac:new')
        self.assertIn('шаг 1 из 5', self.message.sent[-1])
        for answer, step in (('+380991112233', 2), ('Иванов', 3), ('Иван', 4), ('i@x.ua', 5)):
            self.assertIn('шаг %d из 5' % step, self.say(answer))
        confirm = self.say('Киев')
        self.assertIn('Город: Киев', confirm)
        self.assertNotIn('Депозит', confirm)
        self.assertNotIn('Передоплата', confirm)
        self.tap('ac:ok')
        client = store.get('+380991112233')
        self.assertEqual((client['surname'], client['deposit_usd'], client['created_by']), ('Иванов', 0, 11))
        self.assertTrue(any('Пароль' in text for text in self.message.sent))  # the access message for the client
        self.assertFalse(any('Депозит' in text or '0 $' in text for text in self.message.sent))

    def test_no_prepayment_question_or_text_left(self):
        source = (HERE / 'ua_auction_clients_view.py').read_text(encoding='utf-8')
        self.assertNotIn('Передоплата в $', source)
        self.assertNotIn('deposit_usd', (HERE / 'ua_auction_clients_bot.py').read_text(encoding='utf-8').split(
            'async def _answer')[1].split('if \'deposit_for\'')[0])

    def test_card_shows_prepayment_only_when_set(self):
        client = {'phone': '+1', 'surname': 'И', 'name': 'И', 'email': 'e@x', 'city': 'Киев', 'deposit_usd': 0,
                  'blocked': 0, 'created_by': 11}
        self.assertNotIn('Депозит', view.card(client)['text'])
        self.assertIn('Депозит: 1 000 $', view.card(dict(client, deposit_usd=1000))['text'])  # older records as before
        self.assertIn(('💵 Депозит', 'ac:dep:+1'), [b for row in view.card(client)['buttons'] for b in row])

    def test_prepayment_can_still_be_set_later(self):
        store.create('Иванов', 'Иван', '+380991112233', 'i@x.ua', 'Киев', 11)
        self.assertEqual(store.set_deposit('+380991112233', '1 000')['deposit_usd'], 1000)
        with self.assertRaises(store.ClientError):
            store.set_deposit('+380991112233', '999')


class CabinetPageTest(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'kabinet_live.html').read_text(encoding='utf-8')

    def test_prepayment_hidden_when_not_set(self):
        new = candidate_builder.cabinet(self.page)
        self.assertEqual(new.count('$("cab-dep").parentNode.hidden=!c.deposit_usd;'), 1)
        self.assertEqual(len(new) - len(self.page), len('$("cab-dep").parentNode.hidden=!c.deposit_usd;'))
        with self.assertRaisesRegex(ValueError, 'CABINET_PAGE_UNEXPECTED'):
            candidate_builder.cabinet(new.replace(candidate_builder.PREPAYMENT, ''))

    def test_other_installed_version_stops(self):
        source = {name: b'other' for name in candidate_builder.MODULES}
        source[candidate_builder.PAGE] = self.page.encode('utf-8')
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})


if __name__ == '__main__':
    unittest.main()
