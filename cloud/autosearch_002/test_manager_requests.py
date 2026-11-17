"""AUTOSEARCH-002: manager rights, requests (up to 10 per client), the greeting first, each lot once, the WhatsApp
share link, the manager cabinet API (no Telegram for the manager), CRM screens, and the candidate removals giving back
the exact earlier files.

Telegram and the CRM staff table are stand-ins; every record goes to a temporary database. The live «Мій кабінет»
(with the AUTOSEARCH-001 section) and a part of the lot list were read from the site on 2026-11-17.
"""
import asyncio
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
import urllib.parse
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'auction_no_deposit_001'), str(HERE.parent / 'auction_manager_bids_001')]


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
staff_db.ROLE_OWNER = 'owner'
staff_db.list_staff = lambda active_only=False: [{'user_id': 7, 'full_name': 'Артём', 'username': 'art'},
                                                 {'user_id': 11, 'full_name': 'Олег', 'username': 'oleg'}]
staff_db.staff_ids_by_role = lambda role: [7]
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db})

import candidate_builder  # noqa: E402
import ua_lot_alerts as alerts  # noqa: E402
import ua_lot_alerts_view as alerts_view  # noqa: E402
import ua_lot_alerts_web as web  # noqa: E402
import ua_lot_alerts_whatsapp as whatsapp  # noqa: E402

FIX = HERE / 'fixtures'
LOTS = FIX / 'lots_sample.json'
GROUP = 'https://chat.whatsapp.com/AbCdEfGhIj12345'
PEOPLE = [{'phone': '+380991112233', 'name': 'Петро', 'surname': 'Іваненко', 'created_by': 11, 'blocked': 0},
          {'phone': '+380991112244', 'name': 'Олена', 'surname': 'Коваль', 'created_by': 7, 'blocked': 0},
          {'phone': '+380990000011', 'name': 'Олег', 'surname': 'Менеджер', 'created_by': 7, 'blocked': 0}]
MANAGER, OWNER_LOGIN = '+380990000011', '+380990000007'


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for target, value in ((alerts, ('DB', Path(folder.name) / 'alerts.db')), (alerts, ('LOTS', LOTS))):
            patcher = patch.object(target, *value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.generated, self.lots = alerts.read_lots(LOTS)
        web._cache.clear()


class RecordTests(Base):
    def test_old_tables_go_and_new_ones_come(self):
        import sqlite3
        with sqlite3.connect(alerts.DB) as connection:
            connection.execute('CREATE TABLE searches (id INTEGER)')
            connection.execute('CREATE TABLE sent (phone TEXT, lot_id TEXT)')
        alerts.requests()
        with sqlite3.connect(alerts.DB) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertEqual(names, {'managers', 'requests', 'posted', 'views'})

    def test_manager_sees_own_clients_owner_all_and_no_manager_logins(self):
        alerts.set_manager(MANAGER, 11, 'Олег', False)
        alerts.set_manager(OWNER_LOGIN, 7, 'Артём', True)
        logins = alerts.manager_phones()
        self.assertEqual([c['phone'] for c in alerts.own_clients(alerts.manager(MANAGER), PEOPLE, logins)],
                         ['+380991112233'])
        self.assertEqual([c['phone'] for c in alerts.own_clients(alerts.manager(OWNER_LOGIN), PEOPLE, logins)],
                         ['+380991112233', '+380991112244'])
        self.assertEqual(alerts.unset_manager(MANAGER), 1)
        self.assertIsNone(alerts.manager(MANAGER))

    def test_request_needs_a_whatsapp_invite_link_and_at_most_ten(self):
        for bad in ('', 'https://wa.me/123', 'http://chat.whatsapp.com/AbCdEfGhIj12', 'https://chat.whatsapp.com/x'):
            with self.assertRaisesRegex(alerts.AlertError, 'group_link'):
                alerts.add_request('+380991112233', 11, bad, {'maker': 'Kia'})
        for _ in range(alerts.MAX_REQUESTS):
            alerts.add_request('+380991112233', 11, GROUP, {'maker': 'Kia'})
        with self.assertRaisesRegex(alerts.AlertError, 'limit'):
            alerts.add_request('+380991112233', 11, GROUP, {'maker': 'Kia'})
        self.assertEqual(len(alerts.requests(client_phone='+380991112233')), 10)

    def test_delete_only_own(self):
        rid = alerts.add_request('+380991112233', 11, GROUP, {'maker': 'Kia'})
        self.assertEqual(alerts.delete_request(rid, {'+380991112244'}), 0)
        self.assertEqual(alerts.delete_request(rid, {'+380991112233'}), 1)

    def test_matching_and_description(self):
        rule = alerts.criteria({'maker': 'Kia', 'year_from': 2020, 'km_max': 100000, 'usd_max': 15000})
        for lot in [x for x in self.lots if alerts.matches(rule, x)]:
            self.assertTrue(lot['maker'] == 'Kia' and lot['year'] >= 2020 and lot['mileage_km'] <= 100000)
            self.assertTrue(not lot['start_usd'] or lot['start_usd'] <= 15000)
        self.assertEqual(alerts.describe(alerts.criteria({'title': 'Kia K5', 'year_from': 2020, 'year_to': 2023,
                                                          'usd_max': 15000, 'fuel': 'gasoline'})),
                         'Kia K5 · 2020–2023 · до 15 000 $ · бензин')


class WhatsAppTests(unittest.TestCase):
    def test_owner_greeting(self):
        self.assertEqual(whatsapp.welcome('Kia K5 · 2020–2023'),
                         'Здравствуйте! Создан запрос на поиск вашего авто: Kia K5 · 2020–2023. Как только подходящий '
                         'автомобиль появится на аукционе, мы сразу пришлём сюда всю информацию.')

    def test_lot_text_and_share_link(self):
        text = whatsapp.lot({'id': '2026', 'title': 'Kia K5', 'year': 2021, 'mileage_km': 45000, 'start_usd': 9365,
                             'auction_start': '2026/11/18 12:00'})
        self.assertEqual(text, '🚗 Kia K5 2021 · 45 000 км · ≈ 9 365 $\nТорги 18.11\n'
                               'https://www.uaart.com.ua/video/korea.html#lot-2026')
        self.assertIn('цена уточняется', whatsapp.lot({'id': '1', 'title': 'X', 'year': 2020, 'start_usd': 0}))
        url = whatsapp.share_url(text)
        self.assertTrue(url.startswith('https://wa.me/?text='))
        self.assertEqual(urllib.parse.unquote(url[len(whatsapp.SHARE):]), text)


class MessageTests(Base):
    def setUp(self):
        super().setUp()
        self.rid = alerts.add_request('+380991112233', 11, GROUP, {'maker': 'Kia'})
        self.kia = sorted((x for x in self.lots if x['maker'] == 'Kia'), key=lambda x: x['auction_start'])
        self.people = {'+380991112233': 'Іваненко Петро'}

    def test_greeting_first_then_new_lots_once_up_to_ten(self):
        pending, more = web.messages(alerts.requests(), self.people, self.lots)
        self.assertEqual([(m['id'], m['kind']) for m in pending], [(self.rid, 'welcome')])  # lots only after it
        self.assertIn('Здравствуйте', urllib.parse.unquote(pending[0]['share']))
        self.assertEqual(pending[0]['group_link'], GROUP)
        alerts.mark_welcomed(self.rid)
        pending, more = web.messages(alerts.requests(), self.people, self.lots)
        self.assertEqual([m['lot'] for m in pending], [x['id'] for x in self.kia[:10]])
        self.assertEqual(more, {self.rid: len(self.kia) - 10} if len(self.kia) > 10 else {})
        alerts.record_posted(self.rid, [self.kia[0]['id']])
        pending, _ = web.messages(alerts.requests(), self.people, self.lots)
        self.assertNotIn(self.kia[0]['id'], [m['lot'] for m in pending])
        self.assertEqual(alerts.posted_counts()[self.rid], 1)


class WebTests(Base):
    def setUp(self):
        super().setUp()
        store = types.SimpleNamespace(all_clients=lambda: PEOPLE)
        patcher = patch.dict(sys.modules, {'ua_auction_clients': store})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_managers_and_only_their_clients(self):
        self.assertEqual(web.handle('alerts', {}, {'phone': '+380991112233'}), ('403 Forbidden', {'error': 'manager'}))
        alerts.set_manager(MANAGER, 11, 'Олег', False)
        status, body = web.handle('alerts', {}, {'phone': MANAGER})
        self.assertEqual((status, body['manager'], [c['phone'] for c in body['clients']]),
                         ('200 OK', 'Олег', ['+380991112233']))
        self.assertIn('Kia', body['options']['makers'])
        self.assertEqual(web.handle('alerts/add', {'client': '+380991112244', 'maker': 'Kia', 'group_link': GROUP},
                                    {'phone': MANAGER}), ('400 Bad Request', {'error': 'client'}))
        status, body = web.handle('alerts/add', {'client': '+380991112233', 'maker': 'Kia', 'group_link': GROUP},
                                  {'phone': MANAGER})
        self.assertEqual((status, len(body['requests']), body['requests'][0]['client_name']),
                         ('200 OK', 1, 'Іваненко Петро'))
        self.assertEqual(web.handle('alerts/add', {'client': '+380991112233', 'maker': 'Kia', 'group_link': 'x'},
                                    {'phone': MANAGER}), ('400 Bad Request', {'error': 'group_link'}))
        rid = body['requests'][0]['id']
        self.assertEqual(body['messages'][0]['kind'], 'welcome')
        status, body = web.handle('alerts/sent', {'id': rid}, {'phone': MANAGER})
        self.assertTrue(body['messages'] and all(m['kind'] == 'lot' for m in body['messages']))
        lot = body['messages'][0]['lot']
        status, body = web.handle('alerts/sent', {'id': rid, 'lot': lot}, {'phone': MANAGER})
        self.assertEqual((status, body['requests'][0]['sent']), ('200 OK', 1))
        self.assertNotIn(lot, [m['lot'] for m in body['messages']])
        other = alerts.add_request('+380991112244', 7, GROUP, {'maker': 'Kia'})  # not this manager's client
        self.assertEqual(web.handle('alerts/sent', {'id': other}, {'phone': MANAGER}), ('400 Bad Request', {'error': 'request'}))
        self.assertEqual(web.handle('alerts/delete', {'id': rid}, {'phone': MANAGER})[1]['requests'], [])

    def test_views_for_any_logged_in_client(self):
        self.assertEqual(web.handle('alerts/seen', {'lot': '1', 'title': 'Kia K5 2021'}, {'phone': '+380991112233'}),
                         ('200 OK', {'ok': True}))
        self.assertEqual(alerts.views('+380991112233')[0]['count'], 1)

    def test_wsgi_routes(self):
        import io
        import ua_auction_web as app_module
        app = app_module.AuctionApp(lambda environ, start: [b'site'])

        def call(method, path, body=b''):
            environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ORIGIN': app_module.ORIGIN,
                       'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(body)),
                       'wsgi.input': io.BytesIO(body), 'REMOTE_ADDR': '1.2.3.4', 'HTTP_COOKIE': ''}
            return app.handle(path[len(app_module.PREFIX):], environ)[0]
        with tempfile.TemporaryDirectory() as folder, patch.object(app_module, 'KEY_FILE', Path(folder) / 'k'):
            self.assertEqual(call('GET', '/api/auction/alerts'), '401 Unauthorized')
            self.assertEqual(call('POST', '/api/auction/alerts/add', b'{}'), '401 Unauthorized')
            self.assertEqual(call('POST', '/api/auction/alerts/telegram', b'{}'), '404 Not Found')  # AUTOSEARCH-001 gone


class CrmViewTests(Base):
    def test_home_block_screen_and_card(self):
        rid = alerts.add_request('+380991112233', 11, GROUP, {'title': 'Kia K5', 'year_from': 2020})
        alerts.record_posted(rid, ['1', '2'])
        home = {'text': '<b>🔨 Клиенты аукциона</b>', 'buttons': [[('a', 'ac:new')], [('← Меню', 'menu')]]}
        screen = alerts_view.with_home(home, alerts.summary())
        self.assertEqual([row[0][1] for row in screen['buttons']], ['ac:new', 'ac:alerts', 'menu'])
        self.assertIn('Запросов: 1 · клиентов: 1', screen['text'])
        self.assertEqual(alerts.summary(staff_id=7)['requests'], [])  # another manager sees none of these
        text = alerts_view.screen(alerts.summary(), {'+380991112233': 'Іваненко Петро'}, {11: 'Олег'},
                                  alerts.posted_counts())['text']
        self.assertIn('№%03d · Іваненко Петро — Kia K5 · от 2020 · менеджер Олег · отправлено 2' % rid, text)
        card = {'text': '<b>B A</b>\n\n<b>Ставки</b> (время Кореи): пока нет',
                'buttons': [[('x', 'ac:pw:p')], [('К списку клиентов', 'ac:list')]]}
        owner_card = alerts_view.with_card(card, '+380991112233', alerts.requests(), alerts.posted_counts(), [], None, True)
        self.assertEqual(owner_card['buttons'][-2], [('👔 Права менеджера на сайте', 'ac:role:+380991112233')])
        self.assertLess(owner_card['text'].index('🔔 Автопоиск'), owner_card['text'].index('<b>Ставки</b>'))
        manager_card = alerts_view.with_card(card, '+380991112233', [], {}, [], None, False)
        self.assertEqual(manager_card['buttons'], card['buttons'])
        right = {'staff_name': 'Олег', 'sees_all': 0}
        removing = alerts_view.with_card(card, '+380991112233', [], {}, [], right, True)
        self.assertEqual(removing['buttons'][-2], [('✖️ Снять права менеджера', 'ac:roleoff:+380991112233')])
        self.assertIn('Менеджер сайта:</b> Олег · видит своих клиентов', removing['text'])

    def test_role_screen(self):
        screen = alerts_view.role_screen({'phone': MANAGER}, staff_db.list_staff(), {7})
        self.assertEqual(screen['buttons'][0], [('Артём (@art) — владелец', 'ac:roleset:%s:7' % MANAGER)])
        self.assertEqual(screen['buttons'][-1], [('← Карточка', 'ac:c:' + MANAGER)])


class CandidateTests(unittest.TestCase):
    def test_cabinet_back_to_before_then_manager_section(self):
        page = (FIX / 'kabinet_live.html').read_text(encoding='utf-8')
        restored, after = candidate_builder.cabinet(page)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), candidate_builder.CABINET_BEFORE)
        self.assertNotIn('ua-autosearch-v1', after)
        self.assertEqual(after.count('id="mr-form"'), 1)
        self.assertLess(after.index('id="cab-bids"'), after.index('id="mr"'))

    def test_lead_bot_hook_removed(self):
        text = (FIX / 'lead_bot_sanitized.txt').read_text(encoding='utf-8')
        hooked = text.replace('    # LEAD-FOLDERS-001: the lead desk', candidate_builder.LEAD_HOOK
                              + '    # LEAD-FOLDERS-001: the lead desk', 1)
        self.assertEqual(candidate_builder.lead(hooked), text)
        with self.assertRaises(ValueError):
            candidate_builder.lead(text)

    def test_build_refuses_other_versions(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({name: b'x' for name in candidate_builder.SOURCE_FILES}, {})

    def test_build(self):
        a1 = HERE.parent / 'autosearch_001'
        lead = (FIX / 'lead_bot_sanitized.txt').read_text(encoding='utf-8')
        source = {name: (a1 / name).read_bytes() for name in ('ua_lot_alerts.py', 'ua_lot_alerts_web.py',
                                                              'ua_lot_alerts_view.py', 'ua_lot_alerts_bot.py',
                                                              'ua_auction_clients_bot.py', 'ua_auction_web.py')}
        source['lead_bot.py'] = lead.replace('    # LEAD-FOLDERS-001: the lead desk', candidate_builder.LEAD_HOOK
                                             + '    # LEAD-FOLDERS-001: the lead desk', 1).encode()
        source['video/kabinet.html'] = (FIX / 'kabinet_live.html').read_bytes()
        hashes = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
        self.assertEqual({k: v for k, v in hashes.items() if k != 'lead_bot.py'},
                         {k: v for k, v in candidate_builder.SOURCE_SHA256.items() if k != 'lead_bot.py'})
        with patch.dict(candidate_builder.SOURCE_SHA256, hashes), \
                patch.object(candidate_builder, 'LEAD_BEFORE', hashlib.sha256(lead.encode()).hexdigest()):
            candidate = candidate_builder.build(source, {})
        self.assertIsNone(candidate['ua_lot_alerts_bot.py'])
        self.assertEqual(candidate['lead_bot.py'], lead.encode())
        for name, value in candidate.items():
            if name.endswith('.py') and value is not None and name != 'lead_bot.py':
                compile(value, name, 'exec')


if __name__ == '__main__':
    unittest.main()
