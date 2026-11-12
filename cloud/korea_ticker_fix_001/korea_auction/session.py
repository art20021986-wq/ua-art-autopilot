"""Logged-in session to the auction account: few, spaced requests; cookies kept."""
import http.cookiejar
import time
import urllib.parse
import urllib.request

BASE = 'https://jpauto.auction'
_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
LOGIN_FAILED = 'LOGIN_FAILED'


class Session:
    def __init__(self, pause=3.0):
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._pause = pause
        self.requests = 0

    def fetch(self, path, data=None):
        """GET (or POST when data is given) -> (final_url, html)."""
        if self.requests:
            time.sleep(self._pause)
        self.requests += 1
        headers = {'User-Agent': _UA, 'Accept-Language': 'en'}
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers.update({'Referer': BASE + '/', 'Origin': BASE})
        req = urllib.request.Request(urllib.parse.urljoin(BASE, path), data=body, headers=headers)
        with self._opener.open(req, timeout=60) as r:
            return r.geturl(), r.read(32 * 1024 * 1024).decode('utf-8', 'replace')

    def login(self, email, password):
        self.fetch('/')
        url, html = self.fetch('/login/login', {'data[Bidder][email]': email.strip(),
                                                 'data[Bidder][password]': password.strip()})
        if 'data[Bidder][password]' in html:
            raise RuntimeError(LOGIN_FAILED)
        return url
