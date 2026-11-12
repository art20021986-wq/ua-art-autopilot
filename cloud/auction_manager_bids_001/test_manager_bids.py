"""AUCTION-MGR-BIDS-001: variant А (a person places every bid), a manager's bid for a client, statistics by manager,
«Мій кабінет». Telegram, the CRM staff table and the lot list are stand-ins; nothing is sent anywhere.
"""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import io
import json
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


class Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


telegram = types.ModuleType('telegram')
telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup = Button, Markup
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
staff_db.list_staff = lambda active_only=False: [dict(s, role='manager') for s in STAFF]
staff_db.ROLE_OWNER, staff_db.ROLE_ADMIN, staff_db.ROLE_MANAGER = 'owner', 'admin', 'manager'
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db})

import candidate_builder  # noqa: E402
import ua_auction_bids as bids  # noqa: E402
import ua_auction_bids_bot as notify  # noqa: E402
import ua_auction_clients as store  # noqa: E402
import ua_auction_clients_bot as bot  # noqa: E402
import ua_auction_clients_view as view  # noqa: E402
import ua_auction_stats as stats  # noqa: E402
import ua_auction_web as web  # noqa: E402
import ua_client_cabinet as cabinet  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=KST)
LOT = {'id': '20261112000123', 'title': 'Kia K5', 'year': 2021, 'start_krw': 10000000, 'vin': 'KNAGT41BBKA000001'}
NBU = {'usd_uah': 41.0, 'krw_uah': 0.03}
OLD_SCHEMA = bids.SCHEMA.split(', placed_by')[0] + ')'  # the ledger before 2026-11-12


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


def put(db, phone, placed_by=0, status='placed', handled_by=0, now=NOW):
    return bids._insert({'phone': phone}, a_bid(), status, placed_by, handled_by, db, now)


class LedgerTest(Folder):
    def test_request_waits_and_the_first_answer_counts(self):
        asked = bids.request({'phone': '+1'}, a_bid(), self.db, NOW)
        self.assertEqual(bids.get(asked, self.db)['status'], 'requested')
        self.assertTrue(bids.mark(asked, 11, True, self.db, NOW))
        self.assertFalse(bids.mark(asked, 22, False, self.db, NOW))  # a second answer changes nothing
        row = bids.get(asked, self.db)
        self.assertEqual((row['status'], row['placed_by'], row['handled_by']), ('placed', 0, 11))
        refused = bids.request({'phone': '+1'}, a_bid(), self.db, NOW)
        self.assertTrue(bids.mark(refused, 22, False, self.db, NOW))
        self.assertEqual(bids.get(refused, self.db)['status'], 'not_placed')

    def test_answers_at_the_same_moment_give_one_winner(self):
        asked = bids.request({'phone': '+1'}, a_bid(), self.db, NOW)
        results, start = [], threading.Barrier(16)

        def tap(manager):
            start.wait()
            results.append(bids.mark(asked, manager, manager % 2 == 0, self.db, NOW))
        threads = [threading.Thread(target=tap, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), [False] * 15 + [True])

    def test_manager_bid_is_placed_by_the_manager(self):
        bid_id = bids.by_manager({'phone': '+1'}, a_bid(), 11, self.db, NOW)
        row = bids.get(bid_id, self.db)
        self.assertEqual((row['status'], row['placed_by'], row['handled_by']), ('placed', 11, 11))
        self.assertFalse(bids.mark(bid_id, 22, False, self.db, NOW))

    def test_old_ledger_gets_the_columns_and_keeps_its_bids(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(OLD_SCHEMA)
            connection.execute("INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at, vin) "
                               "VALUES ('+1', '1', 'Old', 1, 1, 'failed', 'OSError', '2026-11-11T10:00:00+09:00', 'V')")
        self.assertEqual(stats.summary(NOW, self.db, [])['failed'], 1)  # read only: no columns yet
        bids.request({'phone': '+1'}, a_bid(), self.db, NOW)
        rows = stats.of_client('+1', self.db)
        self.assertEqual([(r['title'], r['status'], r['placed_by'], r['handled_by']) for r in rows],
                         [('Kia K5 2021', 'requested', 0, 0), ('Old', 'failed', 0, 0)])
        bids.request({'phone': '+1'}, a_bid(), self.db, NOW)  # a second open does not migrate again
        self.assertEqual(len(stats.of_client('+1', self.db)), 3)

    def test_day_limit_counts_placed_and_waiting(self):
        for status in ['placed'] * 10 + ['requested'] * 20 + ['not_placed'] * 5:
            put(self.db, '+1', status=status)
        self.assertEqual(bids.today_count(self.db, NOW), 30)
        with self.assertRaisesRegex(bids.BidError, 'day_limit'):
            bids.check(client(), LOT['id'], 25000000, self.lots, self.db, NOW)
        self.assertEqual(bids.today_count(self.db, NOW + timedelta(days=1)), 0)

    def test_nothing_talks_to_the_auction(self):
        for name in ('place', 'bid_form', 'confirmed', '_OneAtATime'):
            self.assertFalse(hasattr(bids, name), name)

    def test_notices(self):
        bids.add_notice(5, 11, 100, self.db)
        bids.add_notice(5, 22, 200, self.db)
        bids.add_notice(6, 11, 300, self.db)
        self.assertEqual(sorted(bids.notices(5, self.db)), [(11, 100), (22, 200)])


class StatsTest(Folder):
    def test_counts_by_who_placed_and_by_manager(self):
        people = [client('+1', 11), client('+2', 11), client('+3', 22)]
        put(self.db, '+1', 0, 'placed', 33)
        put(self.db, '+1', 11, 'placed', 11)
        put(self.db, '+2', 0, 'not_placed', 22)
        put(self.db, '+3', 11, 'placed', 11)
        put(self.db, '+3', 0, 'requested')
        put(self.db, '+9', 0, 'placed')  # a client no longer in the list
        n = stats.summary(NOW, self.db, people)
        self.assertEqual((n['bids_all'], n['bids_self'], n['bids_manager'], n['placed'], n['failed']), (6, 4, 2, 4, 1))
        self.assertEqual(stats.managers(people, self.db), [
            {'id': 11, 'clients': 2, 'for_clients': 2, 'clients_self': 2},
            {'id': 22, 'clients': 1, 'for_clients': 0, 'clients_self': 1}])
        self.assertEqual([(r['phone'], r['placed_by']) for r in stats.of_manager(22, people, self.db)], [('+3', 0)])

    def test_empty_and_missing_ledger(self):
        missing = self.dir / 'none.db'
        self.assertEqual(stats.managers([], missing), [])
        self.assertEqual(stats.of_manager(11, [], missing), [])
        self.assertEqual(stats.summary(NOW, missing, [])['bids_all'], 0)
        self.assertFalse(missing.exists())  # reading never creates the ledger

    def test_ten_thousand_bids_stay_fast(self):
        people = [client('+%d' % i, 11 + i % 7) for i in range(500)]
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(bids.SCHEMA)
            connection.executemany(
                'INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at, placed_by) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                [('+%d' % (i % 500), str(i), 'Car', 10000000, 7000, ('placed', 'requested', 'not_placed')[i % 3], '',
                  (NOW - timedelta(minutes=i)).isoformat(), 0 if i % 3 else 11 + i % 7) for i in range(10000)])
        started = time.monotonic()
        n = stats.summary(NOW, self.db, people)
        rows = stats.managers(people, self.db)
        mine = stats.of_manager(11, people, self.db)
        screens = [view.home(n), view.managers_view(rows, {}), view.manager_view(11, 72, mine, {}, {})]
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(n['bids_self'] + n['bids_manager'], 10000)
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
        self.assertIn('12:40 · сам', screen['text'])  # a bid from before variant А
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

    def test_statuses_and_who_answered(self):
        base = dict(phone='+1', lot_id='1', title='Kia', krw=1, usd=1, vin='', created_at='2026-11-12T13:05:00+09:00')
        waiting = view.card(client(), [dict(base, status='requested', placed_by=0, handled_by=0)], STAFF_NAMES)['text']
        self.assertIn('⏳ 13:05 · заявка клиента · ждёт менеджера', waiting)
        done = view.card(client(), [dict(base, status='placed', placed_by=0, handled_by=11)], STAFF_NAMES)['text']
        self.assertIn('✅ 13:05 · заявка клиента · поставил Иван', done)
        refused = view.card(client(), [dict(base, status='not_placed', placed_by=0, handled_by=22)], STAFF_NAMES)['text']
        self.assertIn('❌ 13:05 · заявка клиента · не поставил @olga', refused)

    def test_bid_screens(self):
        c = client()
        self.assertIn('Шаг 1 из 2: номер лота', view.bid_lot_prompt(c)['text'])
        amount = view.bid_amount_prompt(c, LOT)['text']
        self.assertIn('старт ₩10 000 000', amount)
        self.assertIn('от ₩10 050 000', amount)
        confirm = view.bid_confirm(c, {'lot': LOT, 'krw': 25000000, 'usd': 18293}, bids.LOT_URL % LOT['id'])
        self.assertIn('₩25 000 000 ≈ $18 293', confirm['text'])
        self.assertIn('поставьте сами на аукционе', confirm['text'])
        self.assertEqual(confirm['buttons'], [[('🔗 Открыть лот на аукционе', 'https://jpauto.auction/vehicle-detail/kr/' + LOT['id'])],
                                              [('✅ Поставил', 'ac:bidok'), ('✖ Отмена', 'ac:c:+380991112233')]])
        self.assertTrue(view.BID_RECORDED.startswith('✅'))
        self.assertTrue(set(view.BID_ERRORS) >= {'lot', 'amount', 'step', 'too_low', 'day_limit', 'blocked',
                                                 'no_start_price'})


class Message:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)


class Query:
    def __init__(self, data, message):
        self.data, self.message, self.edits, self.answers = data, message, [], []

    async def answer(self, *a, **kw):
        self.answers.append(a[0] if a else '')

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)

    async def edit_message_reply_markup(self, **kw):
        self.edits.append('no buttons')


class BotTest(Folder):
    """The manager's dialogue end to end, with the clients and the lot list as stand-ins."""

    def setUp(self):
        super().setUp()
        self.clients = {'+380991112233': client(), '+380671112233': client('+380671112233', blocked=1)}
        patches = [patch.object(store, 'get', lambda phone, db=None: self.clients.get(phone)),
                   patch.object(store, 'all_clients', lambda db=None: list(self.clients.values())),
                   patch.object(bids, 'LOTS', self.lots), patch.object(bids, 'DB', self.db)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.context = types.SimpleNamespace(user_data={})
        self.message = Message()
        self.shown = []
        real_show = bot._show

        async def show(message, screen, edit=None):
            self.shown.append(screen)
            await real_show(message, screen, None)
        patcher = patch.object(bot, '_show', show)
        patcher.start()
        self.addCleanup(patcher.stop)

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
        self.assertEqual(self.shown[-1]['buttons'][0][0][1], bids.LOT_URL % LOT['id'])  # the link button
        query = self.tap('ac:bidok')
        self.assertEqual(query.edits, ['no buttons'])
        self.assertTrue(self.message.sent[-1].startswith(view.BID_RECORDED))
        self.tap('ac:bidok')  # a second tap: nothing more is recorded
        self.assertEqual(self.message.sent[-1], 'Ставка уже отмечена или отменена.')
        rows = stats.of_client('+380991112233', self.db)
        self.assertEqual([(r['krw'], r['status'], r['placed_by'], r['handled_by']) for r in rows],
                         [(25000000, 'placed', 11, 11)])

    def test_cancel_and_other_buttons_end_the_dialogue(self):
        self.tap('ac:bid:+380991112233')
        self.say('20261112000123')
        self.say('25000000')
        self.tap('ac:c:+380991112233')  # «✖ Отмена» opens the card
        self.tap('ac:bidok')
        self.assertEqual(stats.of_client('+380991112233', self.db), [])

    def test_blocked_and_unknown_clients(self):
        self.tap('ac:bid:+380671112233')
        self.assertEqual(self.message.sent[-1], view.BID_ERRORS['blocked'])
        self.assertNotIn(bot.WAIT, self.context.user_data)
        self.tap('ac:bid:+380000000000')
        self.assertEqual(self.message.sent[-1], view.FIELD_ERRORS['not_found'])

    def test_day_limit_ends_the_dialogue(self):
        for i in range(bids.DAY_LIMIT):
            bids.request({'phone': '+1'}, a_bid(), self.db)
        self.tap('ac:bid:+380991112233')
        self.say('20261112000123')
        self.assertEqual(self.say('25000000'), view.BID_ERRORS['day_limit'])
        self.assertNotIn(bot.WAIT, self.context.user_data)

    def test_managers_screens(self):
        put(self.db, '+380991112233', 22, 'placed', 22)
        for data in ('ac:mgrs', 'ac:mgr:22', 'ac:mgr:x', 'ac:home', 'ac:c:+380991112233', 'ac:list', 'ac:cancel'):
            self.tap(data)

    def test_link_buttons(self):
        markup = bot._markup([[('🔗 Открыть', 'https://jpauto.auction/vehicle-detail/kr/1')], [('A', 'ac:x'), ('B', 'ac:y')]])
        first, (a, b) = markup.inline_keyboard
        self.assertEqual((first[0].url, first[0].callback_data, a.callback_data, b.url), (
            'https://jpauto.auction/vehicle-detail/kr/1', None, 'ac:x', None))

    def test_staff_names(self):
        self.assertEqual(bot._staff(), {11: 'Иван', 22: '@olga', 33: '33'})


class Sent:
    def __init__(self):
        self.messages, self.edits, self.next_id = [], [], 100

    async def send_message(self, chat, message, **kw):
        self.next_id += 1
        self.messages.append((chat, message, kw.get('reply_markup')))
        return types.SimpleNamespace(message_id=self.next_id)

    async def edit_message_text(self, message, chat_id, message_id, **kw):
        self.edits.append((chat_id, message_id, message))


class NoticeTest(Folder):
    """The staff message about a bid and the answer buttons of a request."""

    def setUp(self):
        super().setUp()
        patches = [patch.object(bids, 'DB', self.db), patch.object(notify, 'recipients', lambda: [11, 22, 33]),
                   patch.object(store, 'get', lambda phone, db=None: client(phone))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.bot = Sent()
        self.context = types.SimpleNamespace(bot=self.bot)

    def answer(self, data, user):
        update = types.SimpleNamespace(callback_query=Query(data, Message()), effective_user=types.SimpleNamespace(id=user))
        with self.assertRaises(Stop):
            asyncio.run(notify.answer(update, self.context))
        return update.callback_query

    def test_request_goes_to_all_with_buttons_and_the_first_answer_shows_everywhere(self):
        asked = bids.request({'phone': '+1'}, a_bid(LOT['id']), self.db, NOW)
        asyncio.run(notify.notify(self.context))
        self.assertEqual([m[0] for m in self.bot.messages], [11, 22, 33])
        chat, message, markup = self.bot.messages[0]
        self.assertTrue(message.startswith('<b>🔨 Заявка на ставку</b>\nПоставьте сами на аукционе и отметьте.'))
        link, (ok, no) = markup.inline_keyboard
        self.assertEqual((link[0].url, ok.callback_data, no.callback_data),
                         (bids.LOT_URL % LOT['id'], 'ab:ok:%d' % asked, 'ab:no:%d' % asked))
        self.assertEqual(len(bids.notices(asked, self.db)), 3)
        query = self.answer('ab:ok:%d' % asked, 22)
        self.assertEqual(query.answers, ['Отмечено'])
        self.assertEqual(sorted(e[0] for e in self.bot.edits), [11, 22, 33])
        self.assertTrue(all('✅ поставил @olga' in e[2] for e in self.bot.edits))
        query = self.answer('ab:no:%d' % asked, 11)  # late answer: nothing changes
        self.assertTrue(query.answers[0].startswith('Уже отмечено: ✅ поставил @olga'))
        self.assertEqual(bids.get(asked, self.db)['status'], 'placed')
        asyncio.run(notify.notify(self.context))
        self.assertEqual(len(self.bot.messages), 3)  # each bid is told once

    def test_strangers_cannot_answer(self):
        asked = bids.request({'phone': '+1'}, a_bid(), self.db, NOW)
        self.assertEqual(self.answer('ab:ok:%d' % asked, 99).answers, ['Недостаточно прав'])
        self.assertEqual(bids.get(asked, self.db)['status'], 'requested')

    def test_manager_bid_is_information_for_the_others(self):
        bids.by_manager({'phone': '+1'}, a_bid(), 11, self.db, NOW)
        asyncio.run(notify.notify(self.context))
        self.assertEqual([m[0] for m in self.bot.messages], [22, 33])
        self.assertTrue(self.bot.messages[0][1].startswith('<b>🔨 Ставка менеджера Иван за клиента</b>\n✅ поставил Иван'))
        self.assertIsNone(self.bot.messages[0][2])


class WebTest(Folder):
    """The site: a bid becomes a request (nothing goes to the auction); «Мій кабінет» shows only the client's own."""

    def setUp(self):
        super().setUp()
        self.me = client('+380991112233')
        patches = [patch.object(bids, 'DB', self.db), patch.object(bids, 'LOTS', self.lots),
                   patch.object(web, 'current_client', lambda environ, key: self.me), patch.object(web, '_key', lambda p: b'k')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = web.AuctionApp(lambda environ, start: [b'site'])

    def call(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else b''
        environ = {'PATH_INFO': '/api/auction/' + path, 'REQUEST_METHOD': method, 'CONTENT_LENGTH': str(len(data)),
                   'CONTENT_TYPE': 'application/json', 'HTTP_ORIGIN': web.ORIGIN, 'wsgi.input': io.BytesIO(data),
                   'REMOTE_ADDR': '1.2.3.4'}
        status = []
        out = self.app(environ, lambda s, h: status.append(s))
        return status[0], json.loads(b''.join(out))

    def test_bid_becomes_a_request(self):
        status, answer = self.call('bid', 'POST', {'lot': LOT['id'], 'krw': 25000000})
        self.assertEqual((status, answer['status']), ('200 OK', 'requested'))
        self.assertEqual(self.call('bid', 'POST', {'lot': LOT['id'], 'krw': 10000})[1], {'error': 'too_low'})
        self.assertEqual([r['status'] for r in stats.of_client(self.me['phone'], self.db)], ['requested'])

    def test_cabinet_shows_only_the_clients_own(self):
        put(self.db, self.me['phone'], 0, 'placed', 11)
        put(self.db, '+380000000000', 0, 'placed', 11)  # someone else's
        status, page = self.call('my')
        self.assertEqual(status, '200 OK')
        self.assertEqual(page['client'], {'name': 'Иван', 'surname': 'Иванов', 'phone': '+380991112233', 'deposit_usd': 1000})
        self.assertEqual(len(page['bids']), 1)
        self.assertEqual(set(page['bids'][0]), set(web.BID_FIELDS))  # no manager ids or other columns
        self.assertEqual(page['cars'], [])
        self.me = None
        self.assertEqual(self.call('my'), ('401 Unauthorized', {'error': 'login'}))


class PageTest(unittest.TestCase):
    """The Korea page after AUCTION-LIMIT (the live page restored by KOREA-CARD) and «Мій кабінет»."""

    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_after_limit.html').read_text(encoding='utf-8')

    def test_korea_page(self):
        new = candidate_builder.korea(self.page)
        self.assertEqual(new.count('id="kc-cab"'), 1)
        self.assertIn('href="/video/kabinet.html"', new)
        self.assertIn('r.status==="requested"', new)
        self.assertNotIn('Розміщуємо ставку на аукціоні', new)
        self.assertEqual(new.count('<!--UA-KOREA-BID-V1-->'), 1)
        self.assertEqual(new.count('<!--UA-KOREA-LOGIN-V1-->'), 1)
        outside = lambda html: html[:html.index('<!--UA-KOREA-LOGIN-V1-->')]
        self.assertEqual(outside(new), outside(self.page))  # nothing before the login block changes

    def test_page_before_auction_limit_stops(self):
        with self.assertRaisesRegex(ValueError, 'KOREA_PAGE_BEFORE_AUCTION_LIMIT'):
            candidate_builder.korea(self.page.replace('id="kc-name"', 'id="kc-name"></b><b id="kc-limit"', 1))
        with self.assertRaisesRegex(ValueError, 'KOREA_LOGIN_LINE'):
            cabinet.link('<html></html>')

    def test_cabinet_page(self):
        html = cabinet.page(candidate_builder.korea(self.page))
        for part in ('noindex', 'id="cab-bids"', 'id="cab-cars"', 'id="cab-login"', '<header class="site-header">',
                     'ua-site-languages.js', '/api/auction/my', 'Мій кабінет'):
            self.assertIn(part, html)
        self.assertEqual(html.count('<header'), 1)


class BuildTest(unittest.TestCase):
    def test_other_installed_version_stops(self):
        source = {name: b'other' for name in candidate_builder.MODULES}
        source[candidate_builder.PAGE] = b''
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})


if __name__ == '__main__':
    unittest.main()
