"""AUTOSEARCH-001: searches (up to 10), matching like the Korea page filter, one-time Telegram link, no repeated lot,
cabinet API, CRM screens, and the candidate edits on the live pages.

Telegram and the CRM staff table are stand-ins; every record goes to a temporary database. The live pages and a part of
the lot list (fixtures/) were read from the site on 2026-11-17; the lead bot copy is the sanitized one (no token).
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'auction_no_deposit_001'), str(HERE.parent / 'auction_manager_bids_001')]


class Stop(Exception):
    """telegram.ext.ApplicationHandlerStop"""


class Forbidden(Exception):
    """telegram.error.Forbidden"""


telegram = types.ModuleType('telegram')
telegram.InlineKeyboardButton = lambda text, callback_data=None, url=None: (text, callback_data or url)
telegram.InlineKeyboardMarkup = lambda rows: rows
telegram_ext = types.ModuleType('telegram.ext')
telegram_ext.ApplicationHandlerStop = Stop
telegram_error = types.ModuleType('telegram.error')
telegram_error.BadRequest = type('BadRequest', (Exception,), {})
telegram_error.Forbidden = Forbidden
orders = types.ModuleType('ua_crm_orders')
orders.allowed = lambda update: True
staff_db = types.ModuleType('db')
staff_db.list_staff = lambda active_only=False: []
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db})

import cabinet_alerts  # noqa: E402
import candidate_builder  # noqa: E402
import ua_lot_alerts as alerts  # noqa: E402
import ua_lot_alerts_bot as alerts_bot  # noqa: E402
import ua_lot_alerts_view as alerts_view  # noqa: E402
import ua_lot_alerts_web as web  # noqa: E402

FIX = HERE / 'fixtures'
LOTS = FIX / 'lots_sample.json'
PHONE = '+380991112233'


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(alerts, 'DB', Path(folder.name) / 'alerts.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.generated, self.lots = alerts.read_lots(LOTS)


class SearchTests(Base):
    def test_criteria_checked_and_years_swapped(self):
        rule = alerts.criteria({'maker': 'Kia', 'title': 'Kia K5', 'year_from': '2023', 'year_to': 2020,
                                'km_max': '100000', 'usd_max': '', 'fuel': 'gasoline', 'color': ''})
        self.assertEqual(rule, {'maker': 'Kia', 'title': 'Kia K5', 'year_from': 2020, 'year_to': 2023,
                                'km_max': 100000, 'usd_max': 0, 'fuel': 'gasoline', 'color': ''})
        for bad in ({}, {'maker': 'Kia', 'fuel': 'coal'}, {'maker': 'Kia', 'km_max': '-5'},
                    {'maker': 'Kia', 'year_from': 'x'}, {'maker': 'K' * 80}, []):
            with self.assertRaises(alerts.AlertError):
                alerts.criteria(bad)

    def test_ten_searches_at_most(self):
        for _ in range(alerts.MAX_SEARCHES):
            alerts.add_search(PHONE, {'maker': 'Kia'})
        with self.assertRaisesRegex(alerts.AlertError, 'limit'):
            alerts.add_search(PHONE, {'maker': 'Kia'})
        self.assertEqual(len(alerts.searches(PHONE)), 10)
        self.assertEqual(alerts.add_search('+380000000001', {'maker': 'Kia'}) > 0, True)  # another client is separate

    def test_only_own_search_is_deleted(self):
        sid = alerts.add_search(PHONE, {'maker': 'Kia'})
        self.assertEqual(alerts.delete_search('+380000000001', sid), 0)
        self.assertEqual(alerts.delete_search(PHONE, sid), 1)
        self.assertEqual(alerts.searches(PHONE), [])

    def test_matching_follows_the_korea_filter_and_keeps_unpriced_lots(self):
        rule = alerts.criteria({'maker': 'Kia', 'year_from': 2020, 'km_max': 100000, 'usd_max': 15000})
        found = [lot for lot in self.lots if alerts.matches(rule, lot)]
        self.assertTrue(found)
        for lot in found:
            self.assertEqual(lot['maker'], 'Kia')
            self.assertGreaterEqual(lot['year'], 2020)
            self.assertLessEqual(lot['mileage_km'], 100000)
            self.assertTrue(not lot['start_usd'] or lot['start_usd'] <= 15000)
        self.assertTrue(any(not lot['start_usd'] for lot in found) or not any(
            not lot['start_usd'] and lot['maker'] == 'Kia' and lot['year'] >= 2020 and lot['mileage_km'] <= 100000
            for lot in self.lots))
        model = self.lots[0]['title']
        rule = alerts.criteria({'title': model})
        self.assertTrue(all(lot['title'] == model for lot in self.lots if alerts.matches(rule, lot)))

    def test_describe(self):
        rule = alerts.criteria({'title': 'Kia K5', 'year_from': 2020, 'year_to': 2023, 'km_max': 100000,
                                'usd_max': 15000, 'fuel': 'gasoline'})
        self.assertEqual(alerts.describe(rule), 'Kia K5 · 2020–2023 · до 100 000 км · до 15 000 $ · бензин')
        self.assertEqual(alerts.describe(alerts.criteria({'maker': 'Hyundai', 'year_from': 2021, 'fuel': 'diesel'}), 1),
                         'Hyundai · от 2021 · дизель')


class TelegramLinkTests(Base):
    def test_code_links_once_and_only_its_hash_is_kept(self):
        code = alerts.new_code(PHONE)
        self.assertRegex(code, r'^as-[A-Za-z0-9_-]{24}$')
        import sqlite3
        with sqlite3.connect(alerts.DB) as connection:
            self.assertNotIn(code, json.dumps(connection.execute('SELECT * FROM codes').fetchall()))
        self.assertEqual(alerts.link(code, 555), PHONE)
        self.assertIsNone(alerts.link(code, 777))
        self.assertEqual(alerts.chat(PHONE), 555)
        self.assertEqual(alerts.unlink(PHONE), 1)
        self.assertIsNone(alerts.chat(PHONE))

    def test_old_and_replaced_codes_do_not_link(self):
        code = alerts.new_code(PHONE, now=1000)
        self.assertIsNone(alerts.link(code, 1, now=1000 + alerts.CODE_SECONDS + 1))
        first = alerts.new_code(PHONE)
        alerts.new_code(PHONE)
        self.assertIsNone(alerts.link(first, 1))
        self.assertIsNone(alerts.link('as-wrong', 1))

    def test_start_link_handler(self):
        code = alerts.new_code(PHONE)
        sent = []

        class Update:
            effective_chat = types.SimpleNamespace(id=42)
            effective_message = types.SimpleNamespace(reply_text=lambda text: _async(sent.append(text)))
        with self.assertRaises(Stop):
            asyncio.run(alerts_bot.start_link(Update(), types.SimpleNamespace(args=[code])))
        self.assertEqual(alerts.chat(PHONE), 42)
        self.assertIn('✅ Telegram підключено', sent[0])
        with self.assertRaises(Stop):
            asyncio.run(alerts_bot.start_link(Update(), types.SimpleNamespace(args=[code])))
        self.assertIn('застаріло', sent[1])

    def test_start_pattern(self):
        import re
        self.assertTrue(re.match(alerts_bot.START, '/start ' + alerts.new_code(PHONE)))
        for other in ('/start', '/start insta', '/start as-', '/start as-x y'):
            self.assertIsNone(re.match(alerts_bot.START, other))


async def _async(value=None):
    return value


class Bot:
    def __init__(self, refuse=False):
        self.sent, self.refuse = [], refuse

    async def send_message(self, chat, text, **kw):
        if self.refuse:
            raise Forbidden()
        self.sent.append((chat, text, kw))


class CheckTests(Base):
    def run_check(self, bot, active=lambda phone: True):
        context = types.SimpleNamespace(bot=bot)
        return asyncio.run(alerts_bot.check(context, read=lambda: (self.generated, self.lots), active=active))

    def test_new_lots_once_up_to_ten_with_the_rest_counted(self):
        alerts.add_search(PHONE, {'maker': 'Kia'})
        alerts.link(alerts.new_code(PHONE), 42)
        kia = [lot for lot in self.lots if lot['maker'] == 'Kia']
        bot = Bot()
        self.assertEqual(self.run_check(bot), 1)
        chat, text, kw = bot.sent[0]
        self.assertEqual((chat, kw['parse_mode']), (42, 'HTML'))
        self.assertEqual(text.count('#lot-'), min(10, len(kia)))
        if len(kia) > 10:
            self.assertIn('Ще %d' % (len(kia) - 10), text)
        self.assertEqual(self.run_check(bot), 0)  # same lot list: nothing again
        alerts.add_search(PHONE, {'title': kia[0]['title']})  # a new search: its lots were all sent already
        self.assertEqual(self.run_check(bot), 0)
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(sum(alerts.sent_counts(PHONE).values()), len(kia))

    def test_without_telegram_or_access_nothing_is_sent_and_kept_for_later(self):
        alerts.add_search(PHONE, {'maker': 'Kia'})
        bot = Bot()
        self.assertEqual(self.run_check(bot), 0)
        alerts.link(alerts.new_code(PHONE), 42)
        self.assertEqual(self.run_check(bot, active=lambda phone: False), 0)
        self.assertEqual(self.run_check(bot), 1)

    def test_stopped_bot_unlinks(self):
        alerts.add_search(PHONE, {'maker': 'Kia'})
        alerts.link(alerts.new_code(PHONE), 42)
        self.assertEqual(self.run_check(Bot(refuse=True)), 0)
        self.assertIsNone(alerts.chat(PHONE))

    def test_message_text_is_escaped(self):
        lot = dict(self.lots[0], title='<b>X</b>', start_usd=0)
        text = alerts_bot.message(alerts.criteria({'maker': 'Kia'}), [lot])
        self.assertIn('&lt;b&gt;X&lt;/b&gt;', text)
        self.assertIn('ціна уточнюється', text)


class WebTests(Base):
    def setUp(self):
        super().setUp()
        patcher = patch.object(alerts, 'LOTS', LOTS)
        patcher.start()
        self.addCleanup(patcher.stop)
        web._cache.clear()

    def test_handle(self):
        client = {'phone': PHONE}
        status, body = web.handle('alerts', {}, client)
        self.assertEqual(status, '200 OK')
        self.assertIn('Kia', body['options']['makers'])
        self.assertEqual((body['searches'], body['telegram'], body['limit']), ([], False, 10))
        status, body = web.handle('alerts/add', {'maker': 'Kia', 'fuel': 'diesel'}, client)
        self.assertEqual(len(body['searches']), 1)
        self.assertEqual(web.handle('alerts/add', {'fuel': 'diesel'}, client), ('400 Bad Request', {'error': 'maker'}))
        status, body = web.handle('alerts/telegram', {}, client)
        self.assertRegex(body['url'], r'^https://t\.me/UA_artcompany_LLC_bot\?start=as-[A-Za-z0-9_-]{24}$')
        sid = web.handle('alerts', {}, client)[1]['searches'][0]['id']
        self.assertEqual(web.handle('alerts/delete', {'id': sid}, client)[1]['searches'], [])
        self.assertEqual(web.handle('alerts/seen', {'lot': '123', 'title': 'Kia K5 2021'}, client), ('200 OK', {'ok': True}))
        self.assertEqual(alerts.views(PHONE)[0]['count'], 1)
        self.assertEqual(web.handle('alerts/seen', {}, client), ('400 Bad Request', {'error': 'request'}))

    def test_wsgi_routes_need_a_login_origin_and_json(self):
        import ua_auction_web as app_module
        app = app_module.AuctionApp(lambda environ, start: [b'site'])

        def call(method, path, body=b'', origin=app_module.ORIGIN, cookie=''):
            import io
            environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ORIGIN': origin,
                       'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(body)),
                       'wsgi.input': io.BytesIO(body), 'REMOTE_ADDR': '1.2.3.4', 'HTTP_COOKIE': cookie}
            return app.handle(path[len(app_module.PREFIX):], environ)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(app_module, 'KEY_FILE', Path(folder) / 'k'):
            self.assertEqual(call('GET', '/api/auction/alerts')[0], '401 Unauthorized')
            self.assertEqual(call('POST', '/api/auction/alerts/add', b'{"maker":"Kia"}')[0], '401 Unauthorized')
            self.assertEqual(call('POST', '/api/auction/alerts/add', b'{}', origin='https://evil')[0], '403 Forbidden')
            self.assertEqual(call('POST', '/api/auction/alerts/other', b'{}')[0], '404 Not Found')
            key = app_module._key()
            client = {'phone': PHONE, 'name': 'A', 'surname': 'B', 'blocked': 0}
            cookie = app_module.COOKIE + '=' + app_module.sign(PHONE, 'fp', 9e12, key)
            with patch.object(app_module.store, 'session_key', return_value='fp'), \
                    patch.object(app_module.store, 'get', return_value=client):
                status, body, _ = call('POST', '/api/auction/alerts/add', b'{"maker":"Kia"}', cookie=cookie)
                self.assertEqual((status, len(body['searches'])), ('200 OK', 1))
                status, body, _ = call('GET', '/api/auction/alerts', cookie=cookie)
                self.assertEqual((status, len(body['searches'])), ('200 OK', 1))
                self.assertEqual(call('POST', '/api/auction/alerts/add', b'[1]', cookie=cookie)[0], '400 Bad Request')


class CrmViewTests(Base):
    def test_home_block_and_button_before_menu(self):
        alerts.add_search(PHONE, {'maker': 'Kia'})
        home = {'text': '<b>🔨 Клиенты аукциона</b>', 'buttons': [[('a', 'ac:new')], [('← Меню', 'menu')]]}
        screen = alerts_view.with_home(home, alerts.summary())
        self.assertEqual([row[0][1] for row in screen['buttons']], ['ac:new', 'ac:alerts', 'menu'])
        self.assertIn('Клиентов с поиском: 1 · поисков: 1', screen['text'])

    def test_screen_lists_who_and_what(self):
        alerts.add_search(PHONE, {'title': 'Kia K5'})
        alerts.add_search('+380000000001', {'title': 'Kia K5'})
        alerts.link(alerts.new_code(PHONE), 1)
        alerts.record_view(PHONE, '1', 'Kia K5 2021')
        alerts.record_view(PHONE, '1', 'Kia K5 2021')
        screen = alerts_view.screen(alerts.summary(), {PHONE: 'Іваненко Петро'})
        self.assertIn('Kia K5 — 2 клиента', screen['text'])
        self.assertIn('Kia K5 2021 — 1 клиент, просмотров 2', screen['text'])
        self.assertIn('Іваненко Петро — поисков 1 · TG ✅', screen['text'])
        self.assertIn(('Іваненко Петро · 1', 'ac:c:' + PHONE), [row[0] for row in screen['buttons']])
        self.assertEqual(screen['buttons'][-1], [alerts_view.BACK])

    def test_card_lines_before_bids(self):
        sid = alerts.add_search(PHONE, {'title': 'Kia K5', 'year_from': 2020})
        alerts.record_sent(PHONE, sid, ['1', '2'])
        card = {'text': '<b>B A</b>\nЛогин: x\n\n<b>Ставки</b> (время Кореи): пока нет', 'buttons': []}
        text = alerts_view.with_card(card, alerts.searches(PHONE), alerts.sent_counts(PHONE), True,
                                     [{'title': 'Kia K5 2021', 'count': 3}])['text']
        self.assertLess(text.index('🔔 Автопоиск'), text.index('<b>Ставки</b>'))
        self.assertIn('1. Kia K5 · от 2020 — отправлено 2', text)
        self.assertIn('Kia K5 2021 — 3 раз(а)', text)


class CandidateTests(unittest.TestCase):
    def test_cabinet_section_after_bids_once(self):
        page = (FIX / 'kabinet_live.html').read_text(encoding='utf-8')
        after = cabinet_alerts.cabinet(page)
        self.assertEqual(after.count('id="as-form"'), 1)
        self.assertLess(after.index('id="cab-bids"'), after.index('id="as-head"'))
        self.assertLess(after.index('id="as-head"'), after.index('</main>'))
        self.assertEqual(after.replace(cabinet_alerts.SECTION, '').replace(cabinet_alerts.STYLE, '')
                         .replace(cabinet_alerts.SCRIPT, ''), page)
        with self.assertRaises(ValueError):
            cabinet_alerts.cabinet(after)

    def test_korea_counts_an_opened_lot_only(self):
        page = (FIX / 'korea_live.html').read_text(encoding='utf-8')
        after = cabinet_alerts.korea(page)
        self.assertEqual(after.replace(cabinet_alerts.SEEN, ''), page)
        self.assertEqual(after.count('/api/auction/alerts/seen'), 1)
        with self.assertRaises(ValueError):
            cabinet_alerts.korea(after)

    def test_lead_bot_hook(self):
        text = (FIX / 'lead_bot_sanitized.txt').read_text(encoding='utf-8')
        after = candidate_builder.lead(text)
        self.assertEqual(after.replace(candidate_builder.LEAD_HOOK, ''), text)
        # the sanitized copy itself does not compile (lines cut out); the server preview compiles the real file
        compile('import logging\ndef build(app):\n' + candidate_builder.LEAD_HOOK + '    return app\n', 'hook', 'exec')
        self.assertLess(after.index('ua_lot_alerts_bot.register(app)'), after.index('    return app\n'))
        with self.assertRaises(ValueError):
            candidate_builder.lead(after)

    def test_build_refuses_other_versions(self):
        source = {name: b'x' for name in candidate_builder.SOURCE_FILES}
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})

    def test_build_on_the_live_pages(self):
        import hashlib
        source = {'ua_auction_web.py': (HERE.parent / 'auction_manager_bids_001/ua_auction_web.py').read_bytes(),
                  'ua_auction_clients_bot.py': (HERE.parent / 'auction_no_deposit_001/ua_auction_clients_bot.py').read_bytes(),
                  'lead_bot.py': (FIX / 'lead_bot_sanitized.txt').read_bytes(),
                  'video/kabinet.html': (FIX / 'kabinet_live.html').read_bytes(),
                  'video/korea.html': (FIX / 'korea_live.html').read_bytes()}
        hashes = {name: hashlib.sha256(source[name]).hexdigest() for name in candidate_builder.SOURCE_SHA256}
        self.assertEqual({k: v for k, v in hashes.items() if k != 'lead_bot.py'},
                         {k: v for k, v in candidate_builder.SOURCE_SHA256.items() if k != 'lead_bot.py'})
        with patch.dict(candidate_builder.SOURCE_SHA256, hashes):
            candidate = candidate_builder.build(source, {})
        self.assertEqual(set(candidate), set(candidate_builder.NEW + candidate_builder.REPLACED) | {
            'lead_bot.py', 'video/kabinet.html', 'video/korea.html'})
        for name, value in candidate.items():
            if name.endswith('.py') and name != 'lead_bot.py':
                compile(value, name, 'exec')


if __name__ == '__main__':
    unittest.main()
