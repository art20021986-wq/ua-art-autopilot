"""«🔨 Клиенты аукциона»: statistics, bids by date, the client's bids in the card, the main menu button."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
KST = timezone(timedelta(hours=9))
CLIENTS = [{'phone': '+380991112233', 'surname': 'Иванов', 'name': 'Иван', 'email': 'i@x.ua', 'city': 'Киев',
            'deposit_usd': 4000, 'limit_usd': 30000, 'blocked': 0},
           {'phone': '+380671112233', 'surname': 'Петров', 'name': 'Пётр', 'email': 'p@x.ua', 'city': 'Киев',
            'deposit_usd': 2000, 'limit_usd': 15000, 'blocked': 1}]
# Stand-ins for the installed modules this package reads (ua_auction_bids, ua_auction_clients, ua_crm_orders, telegram).
bids_stub = types.ModuleType('ua_auction_bids')
bids_stub.KST, bids_stub.DB = KST, Path('/nonexistent/bids.db')
clients_stub = types.ModuleType('ua_auction_clients')
clients_stub.all_clients = lambda: CLIENTS
clients_stub.get = lambda phone: next((c for c in CLIENTS if c['phone'] == phone), None)
clients_stub.ClientError = type('ClientError', (ValueError,), {})
orders_stub = types.ModuleType('ua_crm_orders')
orders_stub.markup = lambda rows: rows


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


telegram_stub = types.ModuleType('telegram')
telegram_stub.InlineKeyboardButton, telegram_stub.InlineKeyboardMarkup = Button, Markup
sys.modules.update({'ua_auction_bids': bids_stub, 'ua_auction_clients': clients_stub, 'ua_crm_orders': orders_stub,
                    'telegram': telegram_stub})
import ua_auction_clients_view as view  # noqa: E402
import ua_auction_stats as stats  # noqa: E402
import ua_menu_extra  # noqa: E402

SCHEMA = '''CREATE TABLE bids (id INTEGER PRIMARY KEY, phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL,
    krw INTEGER NOT NULL, usd INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0)'''
NOW = datetime(2026, 11, 11, 15, 0, tzinfo=KST)


class Ledger(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / 'bids.db'
        rows = [('+380991112233', '1001', 'Kia K5 2021', 20000000, 15000, 'placed', '', '2026-11-11T10:05:00+09:00'),
                ('+380991112233', '1002', 'Kia Sorento 2020', 25000000, 18000, 'failed', 'too_low',
                 '2026-11-11T10:20:00+09:00'),
                ('+380671112233', '1003', 'Hyundai Tucson 2022', 18000000, 13000, 'placed', '',
                 '2026-11-09T11:00:00+09:00'),
                ('+380991112233', '1004', 'Kia K5 2019', 9000000, 6500, 'placed', '', '2026-10-30T11:00:00+09:00')]
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(SCHEMA)
            connection.executemany('INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at) '
                                   'VALUES (?,?,?,?,?,?,?,?)', rows)


class StatsTests(Ledger):
    def test_summary(self):
        n = stats.summary(NOW, self.db, CLIENTS)
        self.assertEqual((n['clients'], n['active'], n['blocked'], n['deposit_usd'], n['limit_usd']),
                         (2, 1, 1, 6000, 45000))
        self.assertEqual((n['bids_today'], n['bids_week'], n['bids_all'], n['placed'], n['failed']), (2, 3, 4, 3, 1))
        self.assertEqual(n['placed_usd_week'], 28000)

    def test_days_and_one_day(self):
        self.assertEqual(stats.days(self.db), [('2026-11-11', 2), ('2026-11-09', 1), ('2026-10-30', 1)])
        self.assertEqual([b['lot_id'] for b in stats.on_day('2026-11-11', self.db)], ['1001', '1002'])
        self.assertEqual([b['lot_id'] for b in stats.of_client('+380991112233', self.db)], ['1002', '1001', '1004'])

    def test_no_ledger_yet(self):
        missing = self.db.with_name('none.db')
        self.assertEqual((stats.days(missing), stats.summary(NOW, missing, [])['bids_all']), ([], 0))
        self.assertFalse(missing.exists())  # read only: nothing is created


class ViewTests(Ledger):
    def test_home(self):
        screen = view.home(stats.summary(NOW, self.db, CLIENTS))
        self.assertIn('Клиентов: 2 (активных 1, заблокировано 1)', screen['text'])
        self.assertIn('Сегодня: 2 · за 7 дней: 3 · всего: 4', screen['text'])
        self.assertIn('Сумма поставленных за 7 дней: 28 000 $', screen['text'])
        self.assertEqual([row[0][1] for row in screen['buttons']], ['ac:new', 'ac:list', 'ac:days', 'menu'])

    def test_dates_open_their_bids(self):
        screen = view.days_view(stats.days(self.db))
        self.assertEqual(screen['buttons'][0], [('Ср 11.11.2026 · ставок: 2', 'ac:day:2026-11-11')])
        day = view.day_view('2026-11-11', stats.on_day('2026-11-11', self.db), {'+380991112233': 'Иванов Иван'})
        self.assertIn('Ставки за Ср 11.11.2026', day['text'])
        self.assertIn('✅ 10:05 · Иванов Иван (+380991112233) · Kia K5 2021 · лот 1001 · ₩20 000 000 ≈ $15 000', day['text'])
        self.assertIn('❌ 10:20', day['text'])

    def test_card_lists_bids_by_date(self):
        text = view.card(CLIENTS[0], stats.of_client('+380991112233', self.db))['text']
        self.assertIn('Ставки</b> (время Кореи): 3', text)
        self.assertLess(text.index('Ср 11.11.2026'), text.index('Пт 30.10.2026'))
        self.assertIn('❌ 10:20 · Kia Sorento 2020 · лот 1002', text)
        self.assertIn('пока нет', view.card(CLIENTS[1])['text'])

    def test_long_history_fits_telegram(self):
        bid = stats.of_client('+380991112233', self.db)[0]
        text = view.card(CLIENTS[0], [bid] * 400)['text']
        self.assertLessEqual(len(text), 3902)
        self.assertTrue(text.endswith('…'))


class MenuTests(unittest.TestCase):
    def full(self, *datas):
        return Markup([[Button(d, callback_data=d)] for d in datas])

    def test_button_right_under_clients(self):
        menu = ua_menu_extra.with_buttons(self.full('cards_cars', 'cards_clients', 'staff_list'), self.full('cards_cars'))
        self.assertEqual([[b.callback_data for b in row] for row in menu.inline_keyboard],
                         [['cards_cars'], ['cards_clients'], ['ac:home'], ['staff_list']])
        self.assertEqual(menu.inline_keyboard[2][0].text, '🔨 Клиенты аукциона')

    def test_no_clients_no_button(self):
        menu = ua_menu_extra.with_buttons(self.full('cards_cars'), self.full('cards_cars'))
        self.assertEqual([[b.callback_data for b in row] for row in menu.inline_keyboard], [['cards_cars']])

    def test_not_twice(self):
        once = ua_menu_extra.with_buttons(self.full('cards_clients'), self.full('cards_clients'))
        twice = ua_menu_extra.with_buttons(self.full('cards_clients'), once)
        self.assertEqual(sum(row[0].callback_data == 'ac:home' for row in twice.inline_keyboard), 1)


class BotTests(Ledger):
    def run_callback(self, data):
        stop = type('ApplicationHandlerStop', (Exception,), {})
        ext = types.ModuleType('telegram.ext')
        ext.ApplicationHandlerStop = stop
        error = types.ModuleType('telegram.error')
        error.BadRequest = type('BadRequest', (Exception,), {})
        shown = []

        class Query:
            message = None

            async def answer(self, *args, **kwargs):
                pass

            async def edit_message_text(self, text, **kwargs):
                shown.append((text, kwargs['reply_markup']))

        query = Query()
        query.data = data
        update = types.SimpleNamespace(callback_query=query, effective_user=types.SimpleNamespace(id=1))
        orders_stub.allowed = lambda update: True
        with patch.dict(sys.modules, {'telegram.ext': ext, 'telegram.error': error}), \
                patch.object(bids_stub, 'DB', self.db):
            import ua_auction_clients_bot as bot
            with self.assertRaises(stop):
                asyncio.run(bot.callback(update, types.SimpleNamespace(user_data={'auction_client': {'step': 1}})))
        return shown[0]

    def test_home_days_day(self):
        text, rows = self.run_callback('ac:home')
        self.assertIn('Клиенты аукциона', text)
        text, rows = self.run_callback('ac:days')
        self.assertEqual(rows[0][0][1], 'ac:day:2026-11-11')
        text, rows = self.run_callback('ac:day:2026-11-11')
        self.assertIn('Иванов Иван (+380991112233)', text)
        text, rows = self.run_callback('ac:day:x')  # not a date: the dates again
        self.assertIn('Ставки по датам', text)

    def test_card_with_bids(self):
        text, rows = self.run_callback('ac:c:+380991112233')
        self.assertIn('Ставки</b> (время Кореи): 3', text)


if __name__ == '__main__':
    unittest.main()
