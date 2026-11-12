"""AUCTION-MGR-BIDS-001: a manager's bid for a client, who placed every bid, statistics by manager.

The auction site, Telegram, the CRM staff table and the lot list are stand-ins; nothing is sent anywhere.
"""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Stop(Exception):
    """telegram.ext.ApplicationHandlerStop"""


class BadRequest(Exception):
    """telegram.error.BadRequest"""


telegram = types.ModuleType('telegram')
telegram_ext = types.ModuleType('telegram.ext')
telegram_ext.ApplicationHandlerStop = Stop
telegram_error = types.ModuleType('telegram.error')
telegram_error.BadRequest = BadRequest
orders = types.ModuleType('ua_crm_orders')
orders.allowed = lambda update: True
orders.markup = lambda rows: rows
staff_db = types.ModuleType('db')
STAFF = [{'user_id': 11, 'full_name': 'Иван', 'username': 'ivan'}, {'user_id': 22, 'full_name': '', 'username': 'olga'},
         {'user_id': 33, 'full_name': None, 'username': None}]
staff_db.list_staff = lambda active_only=False: STAFF
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db})

import ua_auction_bids as bids  # noqa: E402
import ua_auction_clients as store  # noqa: E402
import ua_auction_clients_bot as bot  # noqa: E402
import ua_auction_clients_view as view  # noqa: E402
import ua_auction_stats as stats  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=KST)
LOT = {'id': '20261112000123', 'title': 'Kia K5', 'year': 2021, 'start_krw': 10000000, 'vin': 'KNAGT41BBKA000001'}
NBU = {'usd_uah': 41.0, 'krw_uah': 0.03}
OLD_SCHEMA = bids.SCHEMA.replace(', placed_by INTEGER NOT NULL DEFAULT 0', '')


def client(phone='+380991112233', created_by=11, blocked=0, surname='Иванов', name='Иван'):
    return {'phone': phone, 'surname': surname, 'name': name, 'email': 'i@x.ua', 'city': 'Киев', 'deposit_usd': 1000,
            'blocked': blocked, 'created_at': '2026-11-12T00:00:00+00:00', 'created_by': created_by}


def a_bid(lot_id='1', krw=10050000):
    return {'lot': dict(LOT, id=lot_id), 'krw': krw, 'usd': 7354}


class Folder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.db = self.dir / 'bids.db'
        self.lots = self.dir / 'lots.json'
        self.lots.write_text(json.dumps({'nbu': NBU, 'lots': [LOT]}))


class Browser:
    """The auction site: confirms every bid; counts how many bids are inside it at once."""
    inside = 0
    most = 0
    guard = threading.Lock()

    def __init__(self, pause=0.0, fail=False):
        self.pause, self.fail = pause, fail

    def login(self, email, password):
        with Browser.guard:
            Browser.inside += 1
            Browser.most = max(Browser.most, Browser.inside)
        time.sleep(self.pause)
        with Browser.guard:
            Browser.inside -= 1
        if self.fail:
            raise OSError('down')

    def fetch(self, path, data=None):
        if path == '/bids/kr/':
            return path, '%s ... 1,005' % LOT['id']
        return path, ('<form action="/bids/bid/%s/" id="bidding"><input type="hidden" name="a" value="1"></form>'
                      % LOT['id'])


def _place_in_process(db, results):
    bid = {'lot': LOT, 'krw': 10050000, 'usd': 7354}
    results.put(bids.place({'phone': '+380991112233'}, bid, Browser(0.3), ('e', 'p'), db, placed_by=11)[0])


class LedgerTest(Folder):
    def test_new_ledger_records_who_placed(self):
        bids.record({'phone': '+1'}, a_bid(), 'placed', '', self.db, NOW)
        bids.record({'phone': '+1'}, a_bid(), 'placed', '', self.db, NOW, placed_by=11)
        self.assertEqual([r['placed_by'] for r in stats.of_client('+1', self.db)], [11, 0])

    def test_old_ledger_gets_the_column_and_keeps_its_bids(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(OLD_SCHEMA)
            connection.execute("INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at, vin) "
                               "VALUES ('+1', '1', 'Old', 1, 1, 'placed', '', '2026-11-11T10:00:00+09:00', 'V')")
        self.assertEqual(stats.summary(NOW, self.db, [])['bids_self'], 1)  # read only: no column yet
        bids.record({'phone': '+1'}, a_bid(), 'placed', '', self.db, NOW, placed_by=22)
        rows = stats.of_client('+1', self.db)
        self.assertEqual([(r['title'], r['placed_by'], r['vin']) for r in rows],
                         [('Kia K5 2021', 22, LOT['vin']), ('Old', 0, 'V')])
        bids.record({'phone': '+1'}, a_bid(), 'placed', '', self.db, NOW)  # a second open does not migrate again
        self.assertEqual(len(stats.of_client('+1', self.db)), 3)

    def test_place_records_the_manager_placed_or_failed(self):
        self.assertEqual(bids.place({'phone': '+1'}, a_bid(LOT['id'], 10050000), Browser(), ('e', 'p'), self.db,
                                    placed_by=11), ('placed', ''))
        self.assertEqual(bids.place({'phone': '+1'}, a_bid(LOT['id']), Browser(fail=True), ('e', 'p'), self.db,
                                    placed_by=11), ('failed', 'OSError'))
        self.assertEqual(bids.place({'phone': '+1'}, a_bid(LOT['id']), Browser(), ('e', 'p'), self.db), ('placed', ''))
        self.assertEqual([(r['status'], r['placed_by']) for r in stats.of_client('+1', self.db)],
                         [('placed', 0), ('failed', 11), ('placed', 11)])

    def test_bids_from_threads_go_one_at_a_time(self):
        Browser.most = 0
        threads = [threading.Thread(target=bids.place, args=({'phone': '+%d' % i}, a_bid(LOT['id']), Browser(0.05),
                                                             ('e', 'p'), self.db), kwargs={'placed_by': i % 2 * 11})
                   for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(Browser.most, 1)
        self.assertEqual(stats.summary(NOW, self.db, [])['bids_all'], 12)
        self.assertEqual(stats.summary(NOW, self.db, [])['placed'], 12)

    def test_bids_from_processes_go_one_at_a_time(self):
        """The web app and the bot are separate processes: the lock file keeps their bids apart."""
        context = multiprocessing.get_context('fork')
        results = context.Queue()
        started = time.monotonic()
        workers = [context.Process(target=_place_in_process, args=(self.db, results)) for _ in range(3)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(30)
        self.assertEqual(sorted(results.get(timeout=5) for _ in workers), ['placed'] * 3)
        self.assertGreaterEqual(time.monotonic() - started, 0.9)  # 3 × 0.3 s, never side by side
        self.assertEqual(stats.summary(NOW, self.db, [])['bids_manager'], 3)

    def test_a_bid_still_waiting_is_reported_busy(self):
        with bids._OneAtATime(self.db):
            with patch.object(bids, 'LOCK_WAIT', 0.2):
                self.assertEqual(bids.place({'phone': '+1'}, a_bid(), Browser(), ('e', 'p'), self.db, placed_by=11),
                                 ('failed', 'busy'))
        self.assertEqual([(r['message'], r['placed_by']) for r in stats.of_client('+1', self.db)], [('busy', 11)])
        self.assertEqual(bids.place({'phone': '+1'}, a_bid(LOT['id']), Browser(), ('e', 'p'), self.db)[0], 'placed')


class StatsTest(Folder):
    def fill(self, rows):
        for phone, placed_by, status in rows:
            bids.record({'phone': phone}, a_bid(), status, '', self.db, NOW, placed_by=placed_by)

    def test_counts_by_who_placed_and_by_manager(self):
        people = [client('+1', 11), client('+2', 11), client('+3', 22)]
        self.fill([('+1', 0, 'placed'), ('+1', 11, 'placed'), ('+2', 0, 'failed'), ('+3', 11, 'placed'),
                   ('+3', 0, 'placed'), ('+9', 0, 'placed')])  # +9: a client no longer in the list
        n = stats.summary(NOW, self.db, people)
        self.assertEqual((n['bids_all'], n['bids_self'], n['bids_manager']), (6, 4, 2))
        self.assertEqual(stats.managers(people, self.db), [
            {'id': 11, 'clients': 2, 'for_clients': 2, 'clients_self': 2},
            {'id': 22, 'clients': 1, 'for_clients': 0, 'clients_self': 1}])
        self.assertEqual([(r['phone'], r['placed_by']) for r in stats.of_manager(11, people, self.db)],
                         [('+3', 11), ('+2', 0), ('+1', 11), ('+1', 0)])
        self.assertEqual([(r['phone'], r['placed_by']) for r in stats.of_manager(22, people, self.db)], [('+3', 0)])

    def test_manager_who_only_placed_bids_is_listed(self):
        self.fill([('+1', 33, 'placed')])
        self.assertEqual(stats.managers([client('+1', 11)], self.db), [
            {'id': 33, 'clients': 0, 'for_clients': 1, 'clients_self': 0},
            {'id': 11, 'clients': 1, 'for_clients': 0, 'clients_self': 0}])

    def test_empty_and_missing_ledger(self):
        missing = self.dir / 'none.db'
        self.assertEqual(stats.managers([], missing), [])
        self.assertEqual(stats.of_manager(11, [], missing), [])
        n = stats.summary(NOW, missing, [])
        self.assertEqual((n['bids_self'], n['bids_manager'], n['clients']), (0, 0, 0))
        self.assertFalse(missing.exists())  # reading never creates the ledger

    def test_ten_thousand_bids_stay_fast(self):
        people = [client('+%d' % i, 11 + i % 7) for i in range(500)]
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(bids.SCHEMA)
            connection.executemany(
                'INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at, placed_by) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                [('+%d' % (i % 500), str(i), 'Car', 10000000, 7000, 'placed' if i % 5 else 'failed', '',
                  (NOW - timedelta(minutes=i)).isoformat(), 0 if i % 3 else 11 + i % 7) for i in range(10000)])
        started = time.monotonic()
        n = stats.summary(NOW, self.db, people)
        rows = stats.managers(people, self.db)
        mine = stats.of_manager(11, people, self.db)
        screens = [view.home(n), view.managers_view(rows, {}), view.manager_view(11, 72, mine, {}, {})]
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(n['bids_self'] + n['bids_manager'], 10000)
        self.assertEqual(sum(m['for_clients'] + m['clients_self'] for m in rows), 10000)
        self.assertTrue(all(len(s['text']) <= 4096 for s in screens))


STAFF_NAMES = {11: 'Иван', 22: '@olga', 33: '33'}


class ViewTest(unittest.TestCase):
    def test_home(self):
        n = {'clients': 3, 'active': 3, 'blocked': 0, 'deposit_usd': 3000, 'bids_today': 4, 'bids_week': 9,
             'bids_all': 9, 'bids_self': 5, 'bids_manager': 4, 'placed': 8, 'failed': 1, 'placed_usd_week': 41500}
        screen = view.home(n)
        self.assertIn('Сегодня: 4 · за 7 дней: 9 · всего: 9\nКлиенты сами: 5 · менеджеры за клиентов: 4\n'
                      'Поставлено на аукционе: 8', screen['text'])
        self.assertEqual([row[0] for row in screen['buttons']],
                         [view.NEW, ('👥 Клиенты с доступом · 3', 'ac:list'), view.DAYS, ('👔 По менеджерам', 'ac:mgrs'),
                          view.MENU])

    def test_card_shows_creator_who_placed_and_the_button(self):
        rows = [dict(a_bid(), phone='+1', lot_id='1', title='Kia K5 2021', status='placed', krw=1, usd=1, vin='V',
                     created_at='2026-11-12T13:05:00+09:00', placed_by=11),
                dict(phone='+1', lot_id='2', title='Tucson', status='placed', krw=1, usd=1, vin='',
                     created_at='2026-11-12T12:40:00+09:00', placed_by=0)]
        screen = view.card(client(created_by=22), rows, STAFF_NAMES)
        self.assertIn('Логин: +380991112233\nОформил: @olga\n', screen['text'])
        self.assertIn('13:05 · ставил: менеджер Иван', screen['text'])
        self.assertIn('12:40 · сам', screen['text'])
        self.assertIn([('🔨 Ставка за клиента', 'ac:bid:+380991112233')], screen['buttons'])
        self.assertEqual(screen['buttons'][-1], [('К списку клиентов', 'ac:list')])

    def test_unknown_staff_and_html_are_safe(self):
        screen = view.card(client(created_by=99, surname='<b>X', name='&'), (), {})
        self.assertIn('Оформил: id 99', screen['text'])
        self.assertIn('&lt;b&gt;X &amp;', screen['text'])
        managers = view.managers_view([{'id': 99, 'clients': 1, 'for_clients': 0, 'clients_self': 0}], {99: '<i>'})
        self.assertIn('&lt;i&gt;', managers['text'])

    def test_managers_and_manager_screens(self):
        rows = [{'id': 11, 'clients': 2, 'for_clients': 3, 'clients_self': 4}]
        screen = view.managers_view(rows, STAFF_NAMES)
        self.assertIn('<b>Иван</b> — оформил клиентов: 2\n ставок за клиентов: 3 · ставки его клиентов сами: 4',
                      screen['text'])
        self.assertEqual(screen['buttons'], [[('Иван · 7', 'ac:mgr:11')], [('← Назад', 'ac:home')]])
        self.assertIn('Пока нет', view.managers_view([], {})['text'])
        bid_rows = [dict(phone='+1', lot_id='1', title='Kia', status='placed', krw=1, usd=1, vin='', placed_by=11,
                         created_at='2026-11-12T13:05:00+09:00'),
                    dict(phone='+2', lot_id='2', title='Tucson', status='failed', krw=1, usd=1, vin='', placed_by=0,
                         created_at='2026-11-11T12:40:00+09:00')]
        screen = view.manager_view(11, 2, bid_rows, {'+1': 'Петров П.', '+2': 'Иванов И.'}, STAFF_NAMES)
        self.assertIn('<b>Иван</b> · клиентов: 2\n<b>Чт 12.11.2026</b>', screen['text'])
        self.assertIn('за Петров П.', screen['text'])
        self.assertIn('<b>Ср 11.11.2026</b>\n❌ 12:40 · сам клиент Иванов И.', screen['text'])
        self.assertEqual(screen['buttons'], [[('← По менеджерам', 'ac:mgrs')]])

    def test_day_view_shows_who_placed(self):
        row = dict(phone='+1', lot_id='1', title='Kia', status='placed', krw=1, usd=1, vin='', placed_by=11,
                   created_at='2026-11-12T13:05:00+09:00')
        self.assertIn('Петров П. (+1) · ставил: менеджер Иван', view.day_view('2026-11-12', [row], {'+1': 'Петров П.'},
                                                                             STAFF_NAMES)['text'])

    def test_bid_screens_and_results(self):
        c = client()
        self.assertIn('Шаг 1 из 2: номер лота', view.bid_lot_prompt(c)['text'])
        amount = view.bid_amount_prompt(c, LOT)['text']
        self.assertIn('старт ₩10 000 000', amount)
        self.assertIn('от ₩10 050 000', amount)
        confirm = view.bid_confirm(c, {'lot': LOT, 'krw': 25000000, 'usd': 18293})
        self.assertIn('₩25 000 000 ≈ $18 293', confirm['text'])
        self.assertEqual(confirm['buttons'], [[('✅ Поставить', 'ac:bidok'), ('✖ Отмена', 'ac:c:+380991112233')]])
        self.assertTrue(view.bid_result('placed', '').startswith('✅'))
        for code in ('busy', 'not_confirmed', 'OSError', 'day_limit'):
            self.assertTrue(view.bid_result('failed', code).startswith('❌ Ставка не прошла: '))
        self.assertEqual(set(view.BID_ERRORS) >= {'lot', 'amount', 'step', 'too_low', 'day_limit', 'blocked',
                                                  'no_start_price'}, True)


class Message:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)


class Query:
    def __init__(self, data, message):
        self.data, self.message, self.edits = data, message, []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)

    async def edit_message_reply_markup(self, **kw):
        self.edits.append('no buttons')


class BotTest(Folder):
    """The manager's dialogue end to end, with the clients, the lot list and the auction as stand-ins."""

    def setUp(self):
        super().setUp()
        self.clients = {'+380991112233': client(), '+380671112233': client('+380671112233', blocked=1)}
        self.sent = []
        patches = [patch.object(store, 'get', lambda phone, db=None: self.clients.get(phone)),
                   patch.object(store, 'all_clients', lambda db=None: list(self.clients.values())),
                   patch.object(bids, 'LOTS', self.lots), patch.object(bids, 'DB', self.db),
                   patch.object(bot, '_send', self.fake_send)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.context = types.SimpleNamespace(user_data={})
        self.message = Message()

    def fake_send(self, phone, bid, manager):
        time.sleep(0.2)  # the auction takes a while; the bot must not wait for it
        self.sent.append((phone, bid['krw'], manager))
        return 'placed', ''

    def update(self, data=None, text=None):
        return types.SimpleNamespace(callback_query=Query(data, self.message) if data else None,
                                     effective_user=types.SimpleNamespace(id=11),
                                     effective_message=types.SimpleNamespace(text=text, reply_text=self.message.reply_text))

    def tap(self, data):
        update = self.update(data=data)
        with self.assertRaises(Stop):
            asyncio.run(bot.callback(update, self.context))
        return update.callback_query

    def say(self, text):
        try:
            asyncio.run(bot.text(self.update(text=text), self.context))
        except Stop:
            pass
        return self.message.sent[-1]

    def test_full_dialogue_and_double_tap(self):
        self.tap('ac:bid:+380991112233')
        self.assertIn('Шаг 1 из 2', self.message.sent[-1])
        self.assertEqual(self.say('abc'), view.BID_ERRORS['lot'])
        self.assertEqual(self.say('20261112999999'), view.BID_ERRORS['lot'])
        self.assertIn('Шаг 2 из 2', self.say(' 20261112000123 '))
        self.assertEqual(self.say('сто'), view.BID_ERRORS['amount'])
        self.assertEqual(self.say('10 000 000'), view.BID_ERRORS['too_low'])
        self.assertEqual(self.say('10 055 000'), view.BID_ERRORS['step'])
        self.assertIn('Проверьте ставку', self.say('₩25,000,000'))
        query = self.tap('ac:bidok')
        self.assertEqual(query.edits, ['no buttons'])
        self.assertTrue(self.message.sent[-1].startswith('✅ Ставка поставлена на аукционе.'))
        self.tap('ac:bidok')  # a second tap: nothing more is sent
        self.assertEqual(self.message.sent[-1], 'Ставка уже отправлена или отменена.')
        self.assertEqual(self.sent, [('+380991112233', 25000000, 11)])

    def test_cancel_and_other_buttons_end_the_dialogue(self):
        self.tap('ac:bid:+380991112233')
        self.say('20261112000123')
        self.say('25000000')
        self.tap('ac:c:+380991112233')  # «✖ Отмена» opens the card
        self.tap('ac:bidok')
        self.assertEqual(self.sent, [])

    def test_blocked_and_unknown_clients(self):
        self.tap('ac:bid:+380671112233')
        self.assertEqual(self.message.sent[-1], view.BID_ERRORS['blocked'])
        self.assertNotIn(bot.WAIT, self.context.user_data)
        self.tap('ac:bid:+380000000000')
        self.assertEqual(self.message.sent[-1], view.FIELD_ERRORS['not_found'])

    def test_day_limit_ends_the_dialogue(self):
        for i in range(bids.DAY_LIMIT):
            bids.record({'phone': '+1'}, a_bid(), 'placed', '', self.db)
        self.tap('ac:bid:+380991112233')
        self.say('20261112000123')
        self.assertEqual(self.say('25000000'), view.BID_ERRORS['day_limit'])
        self.assertNotIn(bot.WAIT, self.context.user_data)

    def test_the_bot_keeps_answering_while_a_bid_is_sent(self):
        self.tap('ac:bid:+380991112233')
        self.say('20261112000123')
        self.say('25000000')
        ticks = []

        async def both():
            async def other():
                for _ in range(5):
                    ticks.append(time.monotonic())
                    await asyncio.sleep(0.02)
            try:
                await asyncio.gather(bot.callback(self.update(data='ac:bidok'), self.context), other())
            except Stop:
                pass
        started = time.monotonic()
        asyncio.run(both())
        self.assertEqual(len(ticks), 5)
        self.assertLess(ticks[-1] - started, 0.2)  # the other work ran while the 0.2 s send was in progress

    def test_managers_screens(self):
        bids.record({'phone': '+380991112233'}, a_bid(), 'placed', '', self.db, placed_by=22)
        self.tap('ac:mgrs')
        self.tap('ac:mgr:22')
        self.tap('ac:mgr:x')  # a broken id shows the list again
        self.tap('ac:home')
        self.tap('ac:c:+380991112233')

    def test_staff_names(self):
        self.assertEqual(bot._staff(), {11: 'Иван', 22: '@olga', 33: '33'})


class BuildTest(unittest.TestCase):
    def test_other_installed_version_stops(self):
        import candidate_builder
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({name: b'other' for name in candidate_builder.SOURCE_FILES}, {})


if __name__ == '__main__':
    unittest.main()
