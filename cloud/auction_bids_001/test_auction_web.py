"""Site login: cookie, me, logout, origin, rate limit, block and new password end the session."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ua_auction_clients as store  # noqa: E402
import ua_auction_web as web  # noqa: E402


class WebTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for target, value in ((store, ('DB', Path(tmp.name) / 'clients.db')),
                              (web, ('KEY_FILE', Path(tmp.name) / 'session.key'))):
            p = patch.object(target, *value)
            p.start()
            self.addCleanup(p.stop)
        _, self.password = store.create('Шевченко', 'Тарас', '+380991112233', 't@e.com', 'Київ', 4000, 1)
        self.app = web.mount(lambda environ, start: (start('200 OK', []), [b'site'])[1])
        self.cookie = ''

    def call(self, method, action, body=None, origin=web.ORIGIN, addr='1.2.3.4'):
        raw = json.dumps(body).encode() if body is not None else b''
        environ = {'PATH_INFO': web.PREFIX + action, 'REQUEST_METHOD': method, 'HTTP_ORIGIN': origin,
                   'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw),
                   'REMOTE_ADDR': addr, 'HTTP_COOKIE': 'other=1; ua_auction=' + self.cookie}
        seen = {}
        data = b''.join(self.app(environ, lambda status, headers: seen.update(status=status, headers=headers)))
        for name, value in seen['headers']:
            if name == 'Set-Cookie':
                self.cookie = value.split(';')[0].split('=', 1)[1]
                seen['set_cookie'] = value
        return seen['status'][:3], json.loads(data)

    def login(self, password=None, **kw):
        return self.call('POST', 'login', {'phone': '+380991112233', 'password': password or self.password}, **kw)

    def test_login_me_logout(self):
        self.assertEqual(self.call('GET', 'me')[0], '401')
        status, body = self.login()
        self.assertEqual((status, body['client']['limit_usd']), ('200', 30000))
        self.assertEqual(self.call('GET', 'me')[1]['client']['name'], 'Тарас')
        self.assertEqual(self.call('POST', 'logout', {})[0], '200')
        self.assertEqual(self.call('GET', 'me')[0], '401')

    def test_cookie_is_secure_and_signed(self):
        self.login()
        self.assertNotIn(self.password, self.cookie)
        self.cookie = self.cookie[:-2] + ('AA' if not self.cookie.endswith('AA') else 'BB')
        self.assertEqual(self.call('GET', 'me')[0], '401')

    def test_block_and_new_password_end_the_session(self):
        self.login()
        store.set_blocked('+380991112233', True)
        self.assertEqual(self.call('GET', 'me')[0], '401')
        store.set_blocked('+380991112233', False)
        self.assertEqual(self.call('GET', 'me')[0], '200')
        store.reset_password('+380991112233')
        self.assertEqual(self.call('GET', 'me')[0], '401')

    def test_wrong_password_foreign_origin_and_limit(self):
        self.assertEqual(self.login('wrong')[0], '401')
        self.assertEqual(self.login(origin='https://evil.example')[0], '403')
        statuses = [self.login('wrong', addr='5.5.5.5')[0] for _ in range(6)]
        self.assertEqual(statuses[-1], '429')  # 5 per phone in 15 minutes (one used above)

    def test_bid_needs_login_and_is_checked_then_placed(self):
        import types
        self.assertEqual(self.call('POST', 'bid', {'lot': '20261112000123', 'krw': 10050000})[0], '401')
        self.login()
        placed = []
        fake = types.SimpleNamespace(
            BidError=ValueError,
            check=lambda client, lot, krw: {'lot': {'id': lot}, 'krw': int(krw), 'usd': 7357},
            place=lambda client, bid, browser, login: placed.append((client['phone'], bid['krw'], login)) or ('placed', ''))
        korea = types.ModuleType('korea_auction')
        korea.job = types.SimpleNamespace(read_login=lambda: ('e', 'p'))
        korea.session = types.SimpleNamespace(Session=lambda pause: 'browser')
        with patch.dict(sys.modules, {'ua_auction_bids': fake, 'korea_auction': korea}):
            status, body = self.call('POST', 'bid', {'lot': '20261112000123', 'krw': 10050000})
            self.assertEqual((status, body['status'], body['usd']), ('200', 'placed', 7357))
            self.assertEqual(placed, [('+380991112233', 10050000, ('e', 'p'))])
            fake.check = lambda *a: (_ for _ in ()).throw(ValueError('too_low'))
            self.assertEqual(self.call('POST', 'bid', {'lot': '20261112000123', 'krw': 1})[1], {'error': 'too_low'})
        self.assertEqual(self.call('POST', 'bid', {'lot': '1', 'krw': 1}, origin='https://evil.example')[0], '403')

    def test_other_paths_go_to_the_site(self):
        seen = {}
        body = self.app({'PATH_INFO': '/video/index.html'}, lambda s, h: seen.update(status=s))
        self.assertEqual((b''.join(body), seen['status']), (b'site', '200 OK'))


if __name__ == '__main__':
    unittest.main()
