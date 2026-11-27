"""Gentle, honest reading of IAAI's open pages: our own client name (no browser imitation), one request at a time,
a pause between requests, a hard cap per run. One responsibility: the network."""
import json
import time
import urllib.error
import urllib.request

UA = 'UAArtAutopilot/1.0 (+https://uaart.com.ua)'
PAUSE = 4  # seconds between requests
MAX_PAGE = 6 * 1024 * 1024
MAX_PHOTO = 4 * 1024 * 1024


class Closed(RuntimeError):
    """IAAI refused us (403/418/429 or a challenge page): the run stops and nothing more is asked this hour."""


class Client:
    def __init__(self, limit, sleep=time.sleep):
        self.limit, self.sleep, self.requests = limit, sleep, 0

    def get(self, url, limit=MAX_PAGE, accept='text/html'):
        if self.requests >= self.limit:
            raise Closed('REQUEST_CAP')
        if self.requests:
            self.sleep(PAUSE)
        self.requests += 1
        request = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                kind, body = response.headers.get('Content-Type', ''), response.read(limit + 1)
        except urllib.error.HTTPError as error:
            if error.code in (403, 418, 429, 503):
                raise Closed('HTTP_%d' % error.code) from None
            raise
        if len(body) > limit:
            raise ValueError('TOO_LARGE')
        if b'_Incapsula_Resource' in body[:100000] or b'captcha' in body[:100000].lower():
            raise Closed('CHALLENGE')
        return kind, body

    def page(self, url):
        return self.get(url)[1].decode('utf-8', 'replace')

    def json(self, url):
        return json.loads(self.get(url, accept='application/json')[1])

    def photo(self, url):
        kind, body = self.get(url, MAX_PHOTO, 'image/*')
        if not kind.startswith('image/'):
            raise ValueError('NOT_AN_IMAGE')
        return body
