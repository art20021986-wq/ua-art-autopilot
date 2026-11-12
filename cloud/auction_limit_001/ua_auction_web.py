"""Client login on the site for the Korea online auctions (JPAUTO-KOREA-001, owner 2026-11-10).

A WSGI wrapper: only /api/auction/* is handled here, every other request goes on to the site unchanged.
  POST /api/auction/login   {"phone", "password"} -> sets the login cookie, returns the client's name
  GET  /api/auction/me      -> the logged-in client, or 401
  POST /api/auction/logout  -> clears the cookie
  POST /api/auction/bid     {"lot", "krw"} -> a logged-in client's bid, checked and placed (ua_auction_bids)
The cookie holds the phone, an expiry and the current password fingerprint, signed with HMAC-SHA256 by a server-only
key; a new password or a block ends the session at once. POSTs need the site's own Origin and JSON.
Logins are limited per address and per phone. Standard library only.
"""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import threading
import time

import ua_auction_clients as store

PREFIX = '/api/auction/'
ORIGIN = 'https://www.uaart.com.ua'
COOKIE = 'ua_auction'
KEY_FILE = Path('/home/Carix/auction_clients/session.key')
SESSION_SECONDS = 7 * 24 * 3600
MAX_BODY = 4096
# (limit, seconds) for login attempts per remote address and per phone, and bids per client
LIMITS = {'addr': (10, 60), 'phone': (5, 900), 'bid': (5, 60)}
BID_PAUSE = 1.0  # seconds between the auction site requests of one bid


class Limiter:
    """Login attempts in a sliding window, per key, in this process."""

    def __init__(self, limit, seconds):
        self.limit, self.seconds, self.hits, self.lock = limit, seconds, {}, threading.Lock()

    def allow(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            recent = [t for t in self.hits.get(key, ()) if now - t < self.seconds]
            if len(self.hits) > 10000:
                self.hits.clear()
            allowed = len(recent) < self.limit
            if allowed:
                recent.append(now)
            self.hits[key] = recent
            return allowed


def _key(path=None):
    path = path or KEY_FILE
    if not path.exists():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with open(path, 'xb') as handle:
                handle.write(secrets.token_bytes(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
    return path.read_bytes()


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def sign(phone, fingerprint, expires, key):
    body = _b64(json.dumps([phone, fingerprint, int(expires)], separators=(',', ':')).encode())
    return body + '.' + _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def unsign(value, key, now=None):
    """(phone, fingerprint) of a valid, unexpired cookie, else None."""
    try:
        body, mac = value.split('.')
        if not hmac.compare_digest(_b64(hmac.new(key, body.encode(), hashlib.sha256).digest()), mac):
            return None
        phone, fingerprint, expires = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    except (ValueError, TypeError):
        return None
    return (phone, fingerprint) if expires > (time.time() if now is None else now) else None


def _cookie(environ):
    for part in environ.get('HTTP_COOKIE', '').split(';'):
        name, _, value = part.strip().partition('=')
        if name == COOKIE:
            return value
    return ''


def current_client(environ, key):
    """The logged-in, active client of this request, or None."""
    found = unsign(_cookie(environ), key)
    if not found or store.session_key(found[0]) != found[1]:
        return None
    return store.get(found[0])


def _public(client):
    return {'name': client['name'], 'surname': client['surname'], 'phone': client['phone']}


def _set_cookie(value, max_age):
    return ('Set-Cookie', '%s=%s; Path=/; Max-Age=%d; Secure; HttpOnly; SameSite=Strict' % (COOKIE, value, max_age))


class AuctionApp:
    def __init__(self, application, key_path=None):
        self.application, self.key_path = application, key_path
        self.limits = {name: Limiter(*value) for name, value in LIMITS.items()}

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if not path.startswith(PREFIX):
            return self.application(environ, start_response)
        status, body, headers = self.handle(path[len(PREFIX):], environ)
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        start_response(status, [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'),
                                ('Content-Length', str(len(data)))] + headers)
        return [data]

    def handle(self, action, environ):
        key = _key(self.key_path)
        method = environ.get('REQUEST_METHOD', 'GET')
        if action == 'me' and method == 'GET':
            client = current_client(environ, key)
            return ('200 OK', {'client': _public(client)}, []) if client else ('401 Unauthorized', {'error': 'login'}, [])
        if method != 'POST' or action not in ('login', 'logout', 'bid'):
            return '404 Not Found', {'error': 'not_found'}, []
        if environ.get('HTTP_ORIGIN') != ORIGIN or not environ.get('CONTENT_TYPE', '').startswith('application/json'):
            return '403 Forbidden', {'error': 'origin'}, []
        if action == 'logout':
            return '200 OK', {'ok': True}, [_set_cookie('', 0)]
        if action == 'bid':
            return self.bid(environ, key)
        try:
            length = int(environ.get('CONTENT_LENGTH') or 0)
            if not 0 < length <= MAX_BODY:
                raise ValueError
            data = json.loads(environ['wsgi.input'].read(length))
            phone, password = str(data['phone']), str(data['password'])
        except (ValueError, KeyError, TypeError):
            return '400 Bad Request', {'error': 'request'}, []
        if not (self.limits['addr'].allow(environ.get('REMOTE_ADDR', '')) and self.limits['phone'].allow(phone[-10:])):
            return '429 Too Many Requests', {'error': 'too_many'}, []
        client = store.verify(phone, password)
        if client is None:
            return '401 Unauthorized', {'error': 'login'}, []
        value = sign(client['phone'], store.session_key(client['phone']), time.time() + SESSION_SECONDS, key)
        return '200 OK', {'client': _public(client)}, [_set_cookie(value, SESSION_SECONDS)]

    def bid(self, environ, key):
        """A logged-in client's bid: checked (step, minimum, day limit), then placed from the owner's account."""
        import ua_auction_bids as bids
        client = current_client(environ, key)
        if client is None:
            return '401 Unauthorized', {'error': 'login'}, []
        try:
            lot, krw = _bid_request(environ)
        except (ValueError, KeyError, TypeError):
            return '400 Bad Request', {'error': 'request'}, []
        if not self.limits['bid'].allow(client['phone']):
            return '429 Too Many Requests', {'error': 'too_many'}, []
        try:
            bid = bids.check(client, lot, krw)
        except bids.BidError as error:
            return '400 Bad Request', {'error': str(error)}, []
        from korea_auction import job, session
        status, message = bids.place(client, bid, session.Session(pause=BID_PAUSE), job.read_login())
        return '200 OK', {'status': status, 'message': message, 'krw': bid['krw'], 'usd': bid['usd']}, []


def _bid_request(environ):
    length = int(environ.get('CONTENT_LENGTH') or 0)
    if not 0 < length <= MAX_BODY:
        raise ValueError
    data = json.loads(environ['wsgi.input'].read(length))
    return str(data['lot']), data['krw']


def mount(application):
    """The site's WSGI application with the auction client endpoints in front of it."""
    return AuctionApp(application)
