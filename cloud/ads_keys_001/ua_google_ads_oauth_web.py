"""The site's service address for the one-time Google Ads consent (ADS-KEYS-001, owner «Да» 2026-11-25).

A WSGI wrapper: only GET /api/google-ads/oauth is handled here, every other request goes on to the site unchanged.
Google returns the owner here after «Разрешить» with ?code=…&state=…; the code is exchanged for the refresh token by
ua_google_ads_auth. The page is a short status text, not indexed, nothing is cached; no secret is ever shown.
"""
from html import escape
import logging
import urllib.parse

log = logging.getLogger(__name__)

PATH = '/api/google-ads/oauth'
MARK = 'ua-google-ads-oauth'
PAGES = {
    'ok': ('200 OK', 'Готово ✅', 'Доступ к Google Ads сохранён. Это окно можно закрыть.'),
    'denied': ('200 OK', 'Отменено', 'Разрешение не выдано. Чтобы повторить, пришлите ключи боту CRM ещё раз.'),
    'expired': ('400 Bad Request', 'Ссылка устарела',
                'Пришлите ключи боту CRM ещё раз — он пришлёт новую ссылку.'),
    'incomplete': ('400 Bad Request', 'Ссылка неполная', 'Откройте ссылку из сообщения бота CRM.'),
    'failed': ('502 Bad Gateway', 'Не получилось', 'Google не подтвердил доступ. Попробуйте ещё раз через минуту.'),
}


def page(kind):
    status, title, text = PAGES[kind]
    body = ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s — UA ART</title></head>'
            '<body id="%s" style="font-family:sans-serif;margin:40px 20px;text-align:center"><h1>%s</h1><p>%s</p>'
            '</body></html>' % (escape(title), MARK, escape(title), escape(text))).encode('utf-8')
    return status, body


def answer(environ):
    """The page kind for one callback request."""
    query = urllib.parse.parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=False)
    if 'error' in query:
        return 'denied'
    code, state = query.get('code', [''])[0], query.get('state', [''])[0]
    if not code or not state:
        return 'incomplete'
    import ua_google_ads_auth as auth
    try:
        auth.complete(code, state)
    except auth.AuthError as error:
        log.warning('Google Ads OAuth: %s', str(error)[:60])
        return 'expired' if str(error) == 'STATE' else 'failed'
    return 'ok'


class OAuthApp:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO', '') != PATH or environ.get('REQUEST_METHOD', 'GET') != 'GET':
            return self.application(environ, start_response)
        status, body = page(answer(environ))
        start_response(status, [('Content-Type', 'text/html; charset=utf-8'), ('Cache-Control', 'no-store'),
                                ('X-Robots-Tag', 'noindex'), ('Referrer-Policy', 'no-referrer'),
                                ('Content-Length', str(len(body)))])
        return [body]


def mount(application):
    """The site's WSGI application with the consent callback in front of it."""
    return OAuthApp(application)
