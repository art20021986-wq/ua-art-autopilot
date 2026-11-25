"""ADS-KEYS-001: keys file, consent link, code exchange, the bot message, the site callback, the two live-file edits."""
import asyncio
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import urllib.parse
from unittest.mock import patch

import candidate_builder
import edit_cars_ui
import edit_order_host
import ua_google_ads_auth as auth
import ua_google_ads_key as key
import ua_google_ads_oauth_web as web

F = Path(__file__).resolve().parent / 'fixtures'
# The CRM bot's register chain as the live file ends (the earlier blocks re-define register the same way).
CARS_UI = (b"import logging\nlog = logging.getLogger(__name__)\n\n\ndef register(app):\n    pass\n\n\n"
           b"# TELEGRAM-KEY-BOT: the owner's Telegram API key message\n_ua_telegram_key_register = register\n\n\n"
           b"def register(app):\n    _ua_telegram_key_register(app)\n")
# Made-up values in the real shapes, built from parts so that no file holds anything that looks like a real key.
TOKEN = 'TEST' + 'x' * 18
CLIENT = '1' * 12 + '-' + 'test' * 8 + '.apps.' + 'googleusercontent.com'
SECRET = 'GOC' + 'SPX-' + 'test' * 7


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AuthTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.keys, self.state = folder / 'keys.json', folder / 'state.json'
        self.enterContext(patch.object(auth, 'KEYS_PATH', self.keys))
        self.enterContext(patch.object(auth, 'STATE_PATH', self.state))

    def test_keys_saved_private(self):
        auth.save_client(TOKEN, CLIENT, SECRET, now=lambda: 100)
        data = auth.load()
        self.assertEqual((data['developer_token'], data['client_id'], data['client_secret']), (TOKEN, CLIENT, SECRET))
        self.assertEqual((data['login_customer_id'], data['customer_id']), ('9054959760', '4680747874'))
        self.assertEqual(self.keys.stat().st_mode & 0o777, 0o600)

    def test_link_and_single_use_state(self):
        auth.save_client(TOKEN, CLIENT, SECRET)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(auth.auth_url(now=lambda: 100)).query)
        self.assertEqual(query['redirect_uri'], ['https://www.uaart.com.ua/api/google-ads/oauth'])
        self.assertEqual(query['scope'], ['https://www.googleapis.com/auth/adwords'])
        self.assertEqual((query['access_type'], query['prompt'], query['client_id']), (['offline'], ['consent'], [CLIENT]))
        state = query['state'][0]
        self.assertFalse(auth.consume_state('wrong', now=lambda: 100))  # a wrong state also spends the saved one
        auth.auth_url(now=lambda: 100)
        state = json.loads(self.state.read_text())['state']
        self.assertFalse(auth.consume_state(state, now=lambda: 100 + auth.STATE_SECONDS + 1))
        auth.auth_url(now=lambda: 100)
        state = json.loads(self.state.read_text())['state']
        self.assertTrue(auth.consume_state(state, now=lambda: 200))
        self.assertFalse(auth.consume_state(state, now=lambda: 200))

    def test_link_needs_keys(self):
        with self.assertRaisesRegex(auth.AuthError, 'NO_CLIENT'):
            auth.auth_url()

    def test_code_exchange_keeps_refresh_token(self):
        auth.save_client(TOKEN, CLIENT, SECRET)
        auth.auth_url()
        state = json.loads(self.state.read_text())['state']
        sent = []

        def opener(request, timeout):
            sent.append(urllib.parse.parse_qs(request.data.decode()))
            return Answer(b'{"refresh_token": "r-1", "access_token": "a"}')
        auth.complete('code-1', state, opener=opener)
        self.assertEqual(auth.load()['refresh_token'], 'r-1')
        self.assertEqual(sent[0]['grant_type'], ['authorization_code'])
        self.assertEqual(sent[0]['client_secret'], [SECRET])
        # The same client keeps the token; a new client drops it.
        auth.save_client(TOKEN, CLIENT, SECRET)
        self.assertEqual(auth.load()['refresh_token'], 'r-1')
        auth.save_client(TOKEN, CLIENT, SECRET + 'x')
        self.assertNotIn('refresh_token', auth.load())

    def test_exchange_failures(self):
        auth.save_client(TOKEN, CLIENT, SECRET)
        with self.assertRaisesRegex(auth.AuthError, 'STATE'):
            auth.complete('c', 'nope', opener=None)
        auth.auth_url()
        state = json.loads(self.state.read_text())['state']
        with self.assertRaisesRegex(auth.AuthError, 'NO_REFRESH_TOKEN'):
            auth.complete('c', state, opener=lambda r, timeout: Answer(b'{"access_token": "a"}'))
        auth.auth_url()
        state = json.loads(self.state.read_text())['state']

        def broken(request, timeout):
            raise OSError('down')
        with self.assertRaisesRegex(auth.AuthError, 'TOKEN_EXCHANGE:OSError'):
            auth.complete('c', state, opener=broken)


class BotMessageTests(unittest.TestCase):
    def test_parse_any_order(self):
        for text in ('%s\n%s\n%s' % (TOKEN, CLIENT, SECRET), '%s %s %s' % (SECRET, TOKEN, CLIENT)):
            self.assertEqual(key.parse(text), (TOKEN, CLIENT, SECRET))

    def test_parse_refuses(self):
        for text in (CLIENT + ' ' + SECRET, TOKEN + ' extra ' + CLIENT + ' ' + SECRET, TOKEN + ' ' + CLIENT,
                     'short ' + CLIENT + ' ' + SECRET):
            self.assertIsNone(key.parse(text))

    def test_attempt_detection(self):
        self.assertTrue(key.is_attempt('x ' + SECRET))
        self.assertTrue(key.is_attempt(CLIENT))
        self.assertFalse(key.is_attempt('35000 WAUZZZ8V5KA123456'))

    def run_handler(self, text, chat='private', full=True):
        sent, deleted = [], []

        class Message:
            def __init__(self):
                self.text = text

            async def delete(self):
                deleted.append(True)

        async def send_message(**kwargs):
            sent.append(kwargs)
        update = types.SimpleNamespace(effective_message=Message(), effective_chat=types.SimpleNamespace(type=chat, id=7),
                                       effective_user=types.SimpleNamespace(id=1))
        context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=send_message))
        stop = type('ApplicationHandlerStop', (Exception,), {})
        ext = types.ModuleType('telegram.ext')
        ext.ApplicationHandlerStop = stop
        with patch.dict(sys.modules, {'telegram': types.ModuleType('telegram'), 'telegram.ext': ext}), \
                patch.object(key, 'is_full_rights', return_value=full), \
                patch.object(auth, 'save_client') as save, patch.object(auth, 'auth_url', return_value='https://link'):
            try:
                asyncio.run(key.on_message(update, context))
                stopped = False
            except stop:
                stopped = True
        return sent, deleted, stopped, save

    def test_saves_deletes_and_answers_with_link(self):
        sent, deleted, stopped, save = self.run_handler('%s\n%s\n%s' % (TOKEN, CLIENT, SECRET))
        self.assertEqual((deleted, stopped), ([True], True))
        save.assert_called_once_with(TOKEN, CLIENT, SECRET)
        self.assertIn('https://link', sent[0]['text'])
        self.assertNotIn(SECRET, sent[0]['text'])

    def test_wrong_format_deleted_not_saved(self):
        sent, deleted, stopped, save = self.run_handler(SECRET)
        self.assertEqual((deleted, stopped, sent[0]['text']), ([True], True, key.WRONG))
        save.assert_not_called()

    def test_ignored_outside_owner_private_chat(self):
        for chat, full in (('group', True), ('private', False)):
            sent, deleted, stopped, save = self.run_handler('%s %s %s' % (TOKEN, CLIENT, SECRET), chat, full)
            self.assertEqual((sent, deleted, stopped), ([], [], False))

    def test_ordinary_message_ignored(self):
        self.assertEqual(self.run_handler('Kia K5 2021 — 17000')[:3], ([], [], False))


class CallbackTests(unittest.TestCase):
    def call(self, path, query='', method='GET'):
        seen, status = [], []

        def site(environ, start):
            seen.append(environ['PATH_INFO'])
            start('200 OK', [])
            return [b'site']
        body = b''.join(web.mount(site)({'PATH_INFO': path, 'QUERY_STRING': query, 'REQUEST_METHOD': method},
                                        lambda s, h: status.append((s, dict(h)))))
        return seen, status, body

    def test_other_requests_pass(self):
        self.assertEqual(self.call('/video/index.html')[0], ['/video/index.html'])
        self.assertEqual(self.call(web.PATH, method='POST')[0], [web.PATH])

    def test_pages(self):
        seen, status, body = self.call(web.PATH)
        self.assertEqual((seen, status[0][0]), ([], '400 Bad Request'))
        self.assertEqual(status[0][1]['X-Robots-Tag'], 'noindex')
        self.assertIn(web.MARK.encode(), body)
        self.assertEqual(self.call(web.PATH, 'error=access_denied')[1][0][0], '200 OK')
        with patch.object(auth, 'complete') as complete:
            seen, status, body = self.call(web.PATH, 'code=c1&state=s1')
        complete.assert_called_once_with('c1', 's1')
        self.assertIn('Готово'.encode(), body)
        for reason, expected in (('STATE', '400 Bad Request'), ('TOKEN_EXCHANGE:OSError', '502 Bad Gateway')):
            with patch.object(auth, 'complete', side_effect=auth.AuthError(reason)):
                self.assertEqual(self.call(web.PATH, 'code=c&state=s')[1][0][0], expected)


class EditTests(unittest.TestCase):
    def test_cars_ui_block(self):
        before = CARS_UI
        after = edit_cars_ui.build(before).decode()
        compile(after, 'cars_ui.py', 'exec')  # the whole small file must still be valid Python
        self.assertTrue(after.startswith(before.decode().rstrip('\n')))
        self.assertEqual(after.count('ua_google_ads_key.register(app)'), 1)
        with self.assertRaisesRegex(ValueError, 'CARS_UI_ALREADY_INSTALLED'):
            edit_cars_ui.build(after.encode())

    def test_host_mount(self):
        before = (F / 'order_host.txt').read_bytes()  # a sanitized copy: checked by its text, compiled live by the preview
        after = edit_order_host.build(before).decode()
        self.assertEqual(after.replace(edit_order_host.NEW, edit_order_host.OLD), before.decode())
        self.assertEqual(after.count('ua_google_ads_oauth_web.mount(application)'), 1)
        self.assertLess(after.index('ua_auction_web.mount'), after.index('ua_google_ads_oauth_web.mount'))
        self.assertIn(edit_order_host.NEW, after)  # after the auction login, before the order feature is loaded
        with self.assertRaisesRegex(ValueError, 'ORDER_HOST_FRAGMENT_NOT_UNIQUE'):
            edit_order_host.build(after.encode())

    def test_builder(self):
        source = {'cars_ui.py': CARS_UI, 'ua_order/host.py': (F / 'order_host.txt').read_bytes()}
        result = candidate_builder.build(source)
        self.assertEqual(set(result), set(candidate_builder.NEW_FILES) | set(source))
        with self.assertRaisesRegex(ValueError, 'UNPLANNED'):
            candidate_builder.build({'cars_ui.py': b''})


if __name__ == '__main__':
    unittest.main()
