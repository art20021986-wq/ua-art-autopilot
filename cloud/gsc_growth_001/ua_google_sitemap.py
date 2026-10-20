"""Ask Google to re-read the sitemap after it changes (Search Console API, service account).

Best effort like IndexNow: short timeouts, a failure is returned, never raised, so
publication never waits on or fails because of Google. The key stays on the server.
"""
from pathlib import Path
import urllib.parse
import urllib.request

HOME = Path('/home/Carix')
# The owner uploaded the key from an iPhone; its extension may be dropped or become .txt.
KEYS = tuple(HOME/('uaart-autopilot-110fb4d36d23' + ext) for ext in ('.json', '', '.txt'))
SITE = 'https://www.uaart.com.ua/'
SITEMAP = SITE + 'sitemap.xml'
SCOPE = 'https://www.googleapis.com/auth/webmasters'
ENDPOINT = 'https://www.googleapis.com/webmasters/v3/sites/%s/sitemaps/%s'
TIMEOUT = 10


def _token(key):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    class Bounded(Request):
        def __call__(self, *args, **kwargs):
            kwargs['timeout'] = TIMEOUT
            return super().__call__(*args, **kwargs)

    credentials = service_account.Credentials.from_service_account_file(str(key), scopes=[SCOPE])
    credentials.refresh(Bounded())
    return credentials.token


def submit(keys=KEYS, token=_token, opener=urllib.request.urlopen):
    key = next((k for k in keys if k.is_file()), None)
    if key is None:
        return {'status': 'SKIP', 'reason': 'KEY_MISSING'}
    try:
        request = urllib.request.Request(
            ENDPOINT % (urllib.parse.quote(SITE, safe=''), urllib.parse.quote(SITEMAP, safe='')),
            data=b'', method='PUT', headers={'Authorization': 'Bearer ' + token(key)})
        with opener(request, timeout=TIMEOUT) as response:
            return {'status': 'PASS', 'http': response.status}
    except Exception as error:
        return {'status': 'FAIL', 'error': (type(error).__name__ + ':' + str(error))[:160]}
