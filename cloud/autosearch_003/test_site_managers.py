"""AUTOSEARCH-003: site managers as their own logins (created like clients), the manager's own clients and requests on the
site, the greeting first and each lot once, the CRM screens without manager rights in the client card, the creation
dialogue, and the page back to its exact version before any manager section.

Telegram and the CRM staff table are stand-ins; every record goes to temporary databases. The live «Мій кабінет» (with the
AUTOSEARCH-002 section) and a part of the lot list were read from the site on 2026-11-17.
"""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
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
staff_db.list_staff = lambda active_only=False: [{'user_id': 7, 'full_name': 'Артём', 'username': 'art'}]
pay_store = types.ModuleType('ua_pay_store')  # server-only (CRM-PAYMENTS): nobody here has bought cars
pay_store.purchased_cars = lambda phone: []
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram_ext, 'telegram.error': telegram_error,
                    'ua_crm_orders': orders, 'db': staff_db, 'ua_pay_store': pay_store})

import candidate_builder  # noqa: E402
import ua_auction_clients as clients  # noqa: E402
import ua_lot_alerts as alerts  # noqa: E402
import ua_lot_alerts_view as alerts_view  # noqa: E402
import ua_lot_alerts_web as web  # noqa: E402
import ua_site_managers as managers  # noqa: E402
import ua_site_managers_view as managers_view  # noqa: E402

FIX = HERE / 'fixtures'
LOTS = FIX / 'lots_sample.json'
GROUP = 'https://chat.whatsapp.com/AbCdEfGhIj12345'
MANAGER = '+380990000011'


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        for target, name, value in ((alerts, 'DB', self.folder / 'alerts.db'), (alerts, 'LOTS', LOTS),
                                    (managers, 'DB', self.folder / 'managers.db'),
                                    (clients, 'DB', self.folder / 'clients.db')):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.generated, self.lots = alerts.read_lots(LOTS)
        web._cache.clear()

    def manager(self, phone=MANAGER):
        record, password = managers.create('Петров', 'Олег', phone, 'o@uaart.com.ua', 'Киев', 7)
        return dict(record, role='manager'), password


class ManagerStoreTests(Base):
    def test_created_like_a_client_but_apart(self):
        record, password = managers.create('Петров', 'Олег', '+38 (099) 000-00-11', 'o@uaart.com.ua', 'Киев', 7)
        self.assertEqual((record['phone'], record['created_by']), (MANAGER, 7))
        self.assertEqual(clients.all_clients(), [])  # not a client
        self.assertEqual(managers.verify(MANAGER, password)['surname'], 'Петров')
        self.assertIsNone(managers.verify(MANAGER, 'wrong'))
        with self.assertRaisesRegex(managers.ManagerError, 'phone_exists'):
            managers.create('Х', 'Х', MANAGER, 'x@x.ua', 'Киев', 7)
        clients.create('Іваненко', 'Петро', '+380991112233', 'p@x.ua', 'Київ', 7)
        with self.assertRaisesRegex(managers.ManagerError, 'phone_exists'):  # a client's phone is not given
            managers.create('Х', 'Х', '+380991112233', 'x@x.ua', 'Киев', 7)
        managers.set_blocked(MANAGER, True)
        self.assertIsNone(managers.verify(MANAGER, password))
        managers.set_blocked(MANAGER, False)
        new = managers.reset_password(MANAGER)
        self.assertIsNone(managers.verify(MANAGER, password))
        self.assertIsNotNone(managers.verify(MANAGER, new))


class LoginTests(Base):
    def call(self, app, module, method, path, body=b'', cookie=''):
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ORIGIN': module.ORIGIN,
                   'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(body)),
                   'wsgi.input': io.BytesIO(body), 'REMOTE_ADDR': '1.2.3.4', 'HTTP_COOKIE': cookie}
        return app.handle(path[len(module.PREFIX):], environ)

    def test_manager_logs_in_with_the_same_form_and_does_not_bid(self):
        import ua_auction_web as site
        _, password = self.manager()
        _, client_password = clients.create('Іваненко', 'Петро', '+380991112233', 'p@x.ua', 'Київ', 7)
        app = site.AuctionApp(lambda environ, start: [b'site'])
        with patch.object(site, 'KEY_FILE', self.folder / 'k'):
            status, body, headers = self.call(app, site, 'POST', '/api/auction/login',
                                              json.dumps({'phone': MANAGER, 'password': password}).encode())
            self.assertEqual((status, body['client']['phone']), ('200 OK', MANAGER))
            cookie = headers[0][1].split(';')[0]
            self.assertEqual(site.current_client({'HTTP_COOKIE': cookie}, site._key())['role'], 'manager')
            self.assertEqual(self.call(app, site, 'GET', '/api/auction/alerts', cookie=cookie)[0], '200 OK')
            self.assertEqual(self.call(app, site, 'GET', '/api/auction/my', cookie=cookie)[0], '200 OK')
            self.assertEqual(self.call(app, site, 'POST', '/api/auction/bid', b'{"lot": "1", "krw": 1}', cookie=cookie)[:2],
                             ('403 Forbidden', {'error': 'manager'}))
            status, body, headers = self.call(app, site, 'POST', '/api/auction/login',
                                              json.dumps({'phone': '+380991112233', 'password': client_password}).encode())
            client_cookie = headers[0][1].split(';')[0]
            self.assertNotIn('role', site.current_client({'HTTP_COOKIE': client_cookie}, site._key()))
            self.assertEqual(self.call(app, site, 'GET', '/api/auction/alerts', cookie=client_cookie)[0], '403 Forbidden')
            self.assertEqual(self.call(app, site, 'POST', '/api/auction/alerts/contact', b'{}')[0], '401 Unauthorized')
            managers.reset_password(MANAGER)  # a new password ends the open session
            self.assertIsNone(site.current_client({'HTTP_COOKIE': cookie}, site._key()))


class RecordTests(Base):
    def test_schema_three_drops_the_old_rights_and_requests_keeps_views(self):
        with sqlite3.connect(alerts.DB) as connection:
            connection.execute('CREATE TABLE managers (phone TEXT)')
            connection.execute('CREATE TABLE requests (id INTEGER, client_phone TEXT)')
            connection.execute('CREATE TABLE views (phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL, '
                               'count INTEGER NOT NULL, last_at TEXT NOT NULL, PRIMARY KEY (phone, lot_id))')
            connection.execute("INSERT INTO views VALUES ('+1', '1', 'Kia', 2, 'x')")
        alerts.contacts()
        with sqlite3.connect(alerts.DB) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(connection.execute('SELECT count FROM views').fetchone()[0], 2)
        self.assertEqual(names, {'contacts', 'requests', 'posted', 'views'})
        rid = alerts.add_request(MANAGER, alerts.add_contact(MANAGER, 'Петро', '+380991112233'), GROUP, {'maker': 'Kia'})
        alerts.contacts()  # a second connection does not drop again
        self.assertEqual([r['id'] for r in alerts.requests()], [rid])

    def test_contacts_and_requests_belong_to_their_manager(self):
        cid = alerts.add_contact(MANAGER, 'Іваненко Петро', '+38 099 111 22 33')
        self.assertEqual(alerts.contacts(MANAGER)[0]['phone'], '+380991112233')
        for name, phone, code in (('', '+380991112233', 'name'), ('X', '123', 'phone'),
                                  ('Y', '+380991112233', 'phone_exists')):
            with self.assertRaisesRegex(alerts.AlertError, code):
                alerts.add_contact(MANAGER, name, phone)
        self.assertEqual(alerts.add_contact('+380990000022', 'Інший', '+380991112233') > cid, True)
        with self.assertRaisesRegex(alerts.AlertError, 'client'):  # not this manager's client
            alerts.add_request('+380990000022', cid, GROUP, {'maker': 'Kia'})
        with self.assertRaisesRegex(alerts.AlertError, 'group_link'):
            alerts.add_request(MANAGER, cid, 'https://wa.me/1', {'maker': 'Kia'})
        for _ in range(alerts.MAX_REQUESTS):
            rid = alerts.add_request(MANAGER, cid, GROUP, {'maker': 'Kia'})
        with self.assertRaisesRegex(alerts.AlertError, 'limit'):
            alerts.add_request(MANAGER, cid, GROUP, {'maker': 'Kia'})
        self.assertEqual(alerts.delete_request('+380990000022', rid), 0)
        self.assertEqual(alerts.delete_request(MANAGER, rid), 1)


class WebTests(Base):
    def test_manager_flow_greeting_first_then_lots_once(self):
        user, _ = self.manager()
        self.assertEqual(web.handle('alerts', {}, {'phone': '+380991112233'}), ('403 Forbidden', {'error': 'manager'}))
        status, body = web.handle('alerts/contact', {'name': 'Іваненко Петро', 'phone': '+380991112233'}, user)
        self.assertEqual((status, body['manager'], body['clients'][0]['name']), ('200 OK', 'Петров Олег', 'Іваненко Петро'))
        cid = body['clients'][0]['id']
        self.assertEqual(web.handle('alerts/add', {'contact': cid, 'maker': 'Kia', 'group_link': 'x'}, user),
                         ('400 Bad Request', {'error': 'group_link'}))
        status, body = web.handle('alerts/add', {'contact': cid, 'maker': 'Kia', 'group_link': GROUP}, user)
        rid = body['requests'][0]['id']
        self.assertEqual([(m['id'], m['kind']) for m in body['messages']], [(rid, 'welcome')])
        self.assertIn('Здравствуйте', urllib.parse.unquote(body['messages'][0]['share']))
        status, body = web.handle('alerts/sent', {'id': rid}, user)
        kia = sorted((x for x in self.lots if x['maker'] == 'Kia'), key=lambda x: x['auction_start'])
        self.assertEqual([m['lot'] for m in body['messages']], [x['id'] for x in kia[:10]])
        status, body = web.handle('alerts/sent', {'id': rid, 'lot': kia[0]['id']}, user)
        self.assertEqual(body['requests'][0]['sent'], 1)
        self.assertNotIn(kia[0]['id'], [m['lot'] for m in body['messages']])
        other, _ = self.manager('+380990000022')
        self.assertEqual(web.handle('alerts/sent', {'id': rid}, other), ('400 Bad Request', {'error': 'request'}))
        self.assertEqual(web.handle('alerts', {}, other)[1]['requests'], [])  # sees only his own
        self.assertEqual(web.handle('alerts/delete', {'id': rid}, user)[1]['requests'], [])

    def test_views_for_any_logged_in_client(self):
        self.assertEqual(web.handle('alerts/seen', {'lot': '1', 'title': 'Kia K5 2021'}, {'phone': '+380991112233'}),
                         ('200 OK', {'ok': True}))
        self.assertEqual(alerts.views('+380991112233')[0]['count'], 1)


class CrmTests(Base):
    def test_texts(self):
        cid = alerts.add_contact(MANAGER, 'Іваненко Петро', '+380991112233')
        rid = alerts.add_request(MANAGER, cid, GROUP, {'title': 'Kia K5', 'year_from': 2020})
        alerts.record_posted(rid, ['1', '2'])
        home = {'text': '<b>🔨 Клиенты аукциона</b>', 'buttons': [[('a', 'ac:new')], [('← Меню', 'menu')]]}
        screen = managers_view.with_home(alerts_view.with_home(home, alerts.summary()), 1)
        self.assertEqual([row[0][1] for row in screen['buttons']], ['ac:new', 'ac:alerts', 'sm:list', 'menu'])
        self.assertIn('Запросов: 1 · клиентов у менеджеров: 1', screen['text'])
        text = alerts_view.screen(alerts.summary(), {cid: 'Іваненко Петро'}, {MANAGER: 'Петров Олег'},
                                  alerts.posted_counts())['text']
        self.assertIn('№%03d · Іваненко Петро — Kia K5 · от 2020 · менеджер Петров Олег · отправлено 2' % rid, text)
        card = {'text': '<b>B A</b>\n\n<b>Ставки</b>: пока нет', 'buttons': [[('x', 'ac:pw:p')]]}
        self.assertEqual(alerts_view.with_card(card, []), card)
        self.assertLess(alerts_view.with_card(card, [{'title': 'Kia', 'count': 2}])['text'].index('Смотрел'),
                        card['text'].index('<b>Ставки</b>') + 40)

    def test_manager_screens(self):
        record, _ = managers.create('Петров', 'Олег', MANAGER, 'o@uaart.com.ua', 'Киев', 7)
        listing = managers_view.list_view([record], {MANAGER: 3})
        self.assertEqual(listing['buttons'][0], [('➕ Создать менеджера', 'sm:new')])
        self.assertEqual(listing['buttons'][1], [('Петров Олег · клиентов 3', 'sm:c:' + MANAGER)])
        card = managers_view.card(record, 3, 4, 'Артём')
        self.assertIn('Клиентов: 3 · запросов: 4', card['text'])
        self.assertEqual(card['buttons'][0][0], ('🔁 Сменить пароль', 'sm:pw:' + MANAGER))
        self.assertIn('Логін: %s\nПароль: abc' % MANAGER, managers_view.access_text(record, 'abc'))
        self.assertEqual(managers_view.ask(4)['buttons'], [[('Киев', 'sm:city:Киев')]])


class Message:
    def __init__(self, text=''):
        self.text, self.sent = text, []

    async def reply_text(self, text, **kw):
        self.sent.append(text)
        return self


class Query:
    def __init__(self, data, message):
        self.data, self.message = data, message

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.message.sent.append(text)


class DialogueTests(Base):
    def test_create_a_manager_in_five_steps(self):
        import ua_auction_clients_bot as glue  # noqa: F401 (the shared screen helpers)
        import ua_site_managers_bot as bot
        context = types.SimpleNamespace(user_data={})
        user = types.SimpleNamespace(id=7)
        chat = Message()

        def press(data):
            update = types.SimpleNamespace(callback_query=Query(data, chat), effective_user=user, effective_message=chat)
            with self.assertRaises(Stop):
                asyncio.run(bot.callback(update, context))

        def say(text):
            message = Message(text)
            message.sent = chat.sent
            update = types.SimpleNamespace(effective_user=user, effective_message=message)
            with self.assertRaises(Stop):
                asyncio.run(bot.text(update, context))

        press('sm:new')
        for answer in ('+380990000011', 'Петров', 'Олег', 'o@uaart.com.ua'):
            say(answer)
        press('sm:city:Киев')
        self.assertIn('Проверьте данные менеджера', chat.sent[-1])
        press('sm:ok')
        self.assertIn('Пароль:', chat.sent[-1])
        self.assertEqual(managers.get(MANAGER)['created_by'], 7)
        self.assertEqual(clients.all_clients(), [])
        asyncio.run(bot.text(types.SimpleNamespace(effective_user=user, effective_message=Message('x')), context))  # passes on


class CandidateTests(unittest.TestCase):
    def test_cabinet_back_to_before_then_site_manager_cabinet(self):
        page = (FIX / 'kabinet_live.html').read_text(encoding='utf-8')
        restored, after = candidate_builder.cabinet(page)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), candidate_builder.CABINET_BEFORE)
        self.assertNotIn('ua-manager-v1', after)
        self.assertEqual((after.count('id="mr-form"'), after.count('id="mr-add"')), (1, 1))
        self.assertLess(after.index('id="cab-bids"'), after.index('id="mr"'))

    def test_build_refuses_other_versions(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({name: b'x' for name in candidate_builder.SOURCE_FILES}, {})

    def test_build_on_the_installed_versions(self):
        a2 = HERE.parent / 'autosearch_002'
        source = {name: (a2 / name).read_bytes() for name in candidate_builder.REPLACED}
        source['video/kabinet.html'] = (FIX / 'kabinet_live.html').read_bytes()
        candidate = candidate_builder.build(source, {})
        self.assertEqual(set(candidate), set(candidate_builder.REPLACED + candidate_builder.NEW) | {'video/kabinet.html'})
        for name, value in candidate.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')


if __name__ == '__main__':
    unittest.main()
