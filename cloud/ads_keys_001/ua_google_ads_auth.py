"""Google Ads API access of UA ART (ADS-KEYS-001, owner «Да» 2026-11-25).

One place for the server-side secrets and the one-time OAuth consent:
- the owner's bot message gives the developer token and the OAuth client id and secret (save_client);
- auth_url() makes the consent link with a single-use state, valid 30 minutes;
- the site's callback (ua_google_ads_oauth_web) exchanges the code for the refresh token (complete).
The secrets live in one file outside the site folders, mode 600; values are never logged or echoed.
"""
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
import urllib.parse
import urllib.request

KEYS_PATH = Path('/home/Carix/google_ads_api.json')
STATE_PATH = Path('/home/Carix/.google_ads_oauth_state.json')
REDIRECT_URI = 'https://www.uaart.com.ua/api/google-ads/oauth'
SCOPE = 'https://www.googleapis.com/auth/adwords'
AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
LOGIN_CUSTOMER_ID = '9054959760'  # manager account «UA ART Manager»
CUSTOMER_ID = '4680747874'  # advertiser account «UA ART comapny LLC»
STATE_SECONDS = 1800


class AuthError(Exception):
    """A short reason, safe to show (never a secret value)."""


def _write(path, value):
    """Atomic JSON write, mode 600 from the first byte."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.google-ads-')
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(path=None):
    try:
        return json.loads(Path(path or KEYS_PATH).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def save_client(developer_token, client_id, client_secret, path=None, now=time.time):
    """Keep the three keys; a refresh token stays only while the OAuth client is the same."""
    data = load(path)
    if data.get('client_id') != client_id or data.get('client_secret') != client_secret:
        data.pop('refresh_token', None)
    data.update(developer_token=developer_token, client_id=client_id, client_secret=client_secret,
                login_customer_id=LOGIN_CUSTOMER_ID, customer_id=CUSTOMER_ID, saved_at=int(now()))
    _write(path or KEYS_PATH, data)


def auth_url(path=None, state_path=None, now=time.time):
    """The consent link for the owner; a new single-use state replaces any earlier one."""
    client_id = load(path).get('client_id')
    if not client_id:
        raise AuthError('NO_CLIENT')
    state = secrets.token_urlsafe(32)
    _write(state_path or STATE_PATH, {'state': state, 'expires': int(now()) + STATE_SECONDS})
    query = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': REDIRECT_URI, 'scope': SCOPE,
             'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'true', 'state': state}
    return AUTH_ENDPOINT + '?' + urllib.parse.urlencode(query)


def consume_state(state, state_path=None, now=time.time):
    """True once for the current, unexpired state; the state is removed whatever the answer."""
    path = Path(state_path or STATE_PATH)
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return False
    path.unlink(missing_ok=True)
    return (isinstance(state, str) and hmac.compare_digest(state, str(saved.get('state', '')))
            and now() <= saved.get('expires', 0))


def complete(code, state, path=None, state_path=None, opener=urllib.request.urlopen, now=time.time):
    """Exchange the consent code for the refresh token and keep it."""
    if not consume_state(state, state_path, now):
        raise AuthError('STATE')
    data = load(path)
    if not data.get('client_id') or not data.get('client_secret'):
        raise AuthError('NO_CLIENT')
    body = urllib.parse.urlencode({'code': code, 'client_id': data['client_id'], 'client_secret': data['client_secret'],
                                   'redirect_uri': REDIRECT_URI, 'grant_type': 'authorization_code'}).encode()
    request = urllib.request.Request(TOKEN_ENDPOINT, data=body, method='POST',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with opener(request, timeout=30) as response:
            answer = json.loads(response.read(65536))
    except Exception as error:
        raise AuthError('TOKEN_EXCHANGE:' + type(error).__name__) from None
    refresh = answer.get('refresh_token')
    if not refresh:
        raise AuthError('NO_REFRESH_TOKEN')
    data.update(refresh_token=refresh, authorized_at=int(now()))
    _write(path or KEYS_PATH, data)
