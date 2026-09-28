"""Telegram signature verification and anonymous web-session protection."""
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import parse_qsl


class Unauthorized(ValueError):
    pass


def telegram_user(raw, bot_token, *, now=None, max_age=3600):
    now = time.time() if now is None else now
    try:
        if not isinstance(raw, str) or len(raw.encode()) > 16384:
            raise ValueError()
        pairs = parse_qsl(raw, strict_parsing=True, max_num_fields=32, keep_blank_values=True)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError()
        signature = data.pop('hash')
        if not re.fullmatch('[0-9a-f]{64}', signature):
            raise ValueError()
        check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
        secret = hmac.digest(b'WebAppData', bot_token.encode(), 'sha256')
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        age = now - int(data['auth_date'])
        if age < -30 or age > max_age:
            raise ValueError()
        user = json.loads(data['user'])
        if type(user.get('id')) is not int or user['id'] <= 0:
            raise ValueError()
        return user['id']
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise Unauthorized('telegram_auth') from exc


class WebSessions:
    def __init__(self, secret, *, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError('A server-side secret of at least 32 bytes is required')
        self.secret, self.clock = secret, clock

    def _mac(self, purpose, value):
        return hmac.new(self.secret, f'{purpose}:{value}'.encode(), hashlib.sha256).hexdigest()

    def create(self):
        value = f'{secrets.token_urlsafe(24)}.{int(self.clock())}'
        return value + '.' + self._mac('session', value)

    def verify(self, cookie):
        try:
            nonce, stamp, mac = cookie.split('.')
            if not re.fullmatch('[A-Za-z0-9_-]{32}', nonce):
                raise ValueError()
            if not hmac.compare_digest(mac, self._mac('session', nonce + '.' + stamp)):
                raise ValueError()
            if not 0 <= self.clock() - int(stamp) <= 86400:
                raise ValueError()
            return 'web:' + nonce
        except (AttributeError, ValueError) as exc:
            raise Unauthorized('session') from exc

    def csrf(self, cookie):
        self.verify(cookie)
        return self._mac('csrf', cookie)

    def check_csrf(self, cookie, token):
        if not token or not hmac.compare_digest(token, self.csrf(cookie)):
            raise Unauthorized('csrf')
