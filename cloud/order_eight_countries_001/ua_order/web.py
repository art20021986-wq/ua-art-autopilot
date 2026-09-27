"""Small WSGI adapter mounted by the existing web application, no new server."""
from http.cookies import SimpleCookie
import json
import sqlite3
from urllib.parse import parse_qs

from .auth import Unauthorized, telegram_user
from .contract import Conflict, Invalid, MAX_BYTES, decode
from .repository import NotFound
from .service import Principal


class WebAdapter:
    def __init__(self, service, sessions, *, origin, consent_text, allow_request,
                 bot_token=None, bot_username='UA_artcompany_LLC_bot'):
        if not callable(allow_request):
            raise ValueError('Connect the existing rate limiter before enabling intake')
        if not origin.startswith('https://') or origin.endswith('/'):
            raise ValueError('Configure the exact HTTPS origin')
        if set(consent_text) != {'uk', 'ru', 'ka'} or not all(consent_text.values()):
            raise ValueError('The existing consent text is required in all UI languages')
        self.service, self.sessions, self.origin = service, sessions, origin
        self.consent_text, self.allow_request = consent_text, allow_request
        self.bot_token, self.bot_username = bot_token, bot_username

    def _cookie(self, env):
        try:
            cookies = SimpleCookie(env.get('HTTP_COOKIE', ''))
            return cookies['ua_order_session'].value if 'ua_order_session' in cookies else ''
        except Exception as exc:
            raise Unauthorized('cookie') from exc

    def _principal(self, env, *, csrf=False):
        init_data = env.get('HTTP_X_TELEGRAM_INIT_DATA')
        if init_data:
            if not self.bot_token:
                raise Unauthorized('telegram_disabled')
            user_id = telegram_user(init_data, self.bot_token)
            return Principal(f'telegram:{user_id}', 'telegram_mini_app')
        cookie = self._cookie(env)
        owner = self.sessions.verify(cookie)
        if csrf:
            self.sessions.check_csrf(cookie, env.get('HTTP_X_CSRF_TOKEN', ''))
        return Principal(owner, 'site')

    def __call__(self, env, start_response):
        headers = [('Content-Type', 'application/json; charset=utf-8'),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        status = 200
        try:
            path, method = env.get('PATH_INFO', ''), env.get('REQUEST_METHOD', '')
            if path == '/api/orders/bootstrap' and method == 'GET':
                cookie = self._cookie(env)
                try:
                    self.sessions.verify(cookie)
                except Unauthorized:
                    cookie = self.sessions.create()
                    headers.append(('Set-Cookie', f'ua_order_session={cookie}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400'))
                result = dict(catalog=self.service.catalog.export(), csrf=self.sessions.csrf(cookie),
                              consent_version=self.service.consent_version, consent_text=self.consent_text)
            elif path == '/api/orders/receipt' and method == 'GET':
                principal = self._principal(env)
                try:
                    query = parse_qs(env.get('QUERY_STRING', ''), max_num_fields=2)
                except ValueError as exc:
                    raise Invalid('request_id') from exc
                request_ids = query.get('request_id', [])
                if len(request_ids) != 1 or set(query) != {'request_id'}:
                    raise Invalid('request_id')
                result = self.service.repository.receipt_for_owner(request_ids[0], principal.owner)
            elif path in ('/api/orders/submit', '/api/orders/handoff') and method == 'POST':
                if env.get('HTTP_ORIGIN') != self.origin:
                    raise Unauthorized('origin')
                principal = self._principal(env, csrf=True)
                if not self.allow_request(env, principal):
                    status, result = 429, {'error': 'rate_limit'}
                else:
                    if env.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                        raise Invalid('content_type')
                    try:
                        length = int(env.get('CONTENT_LENGTH', '0'))
                    except ValueError as exc:
                        raise Invalid('body_size') from exc
                    if not 0 < length <= MAX_BYTES:
                        raise Invalid('body_size')
                    raw = env['wsgi.input'].read(length)
                    if len(raw) != length:
                        raise Invalid('body_size')
                    payload = decode(raw)
                    if path.endswith('/submit'):
                        result = self.service.submit(payload, principal)
                    else:
                        token = self.service.handoff(payload, principal)
                        result = {'url': f'https://t.me/{self.bot_username}?start=or_{token}'}
            else:
                status, result = 404, {'error': 'not_found'}
        except Invalid as exc:
            status, result = (413 if exc.field == 'body_size' else 400), {'error': 'invalid', 'field': exc.field}
        except Unauthorized:
            status, result = 403, {'error': 'unauthorized'}
        except NotFound:
            status, result = 404, {'error': 'not_found'}
        except Conflict:
            status, result = 409, {'error': 'conflict'}
        except sqlite3.Error:
            status, result = 503, {'error': 'temporarily_unavailable'}
        body = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode()
        names = {200:'OK', 400:'Bad Request', 403:'Forbidden', 404:'Not Found',
                 409:'Conflict', 413:'Content Too Large', 429:'Too Many Requests', 503:'Service Unavailable'}
        headers.append(('Content-Length', str(len(body))))
        start_response(f'{status} {names[status]}', headers)
        return [body]


def mount(application, order_adapter):
    """Outer WSGI wrapper: only order API paths bypass the existing application."""
    def wrapped(env,start_response):
        if env.get('PATH_INFO','').startswith('/api/orders/'):
            return order_adapter(env,start_response)
        return application(env,start_response)
    return wrapped
