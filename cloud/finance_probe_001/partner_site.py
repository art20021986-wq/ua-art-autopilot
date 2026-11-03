"""Read the partner's official public pages on the runner (FINANCE-001): facts and logo for the finance page.

GET only, robots.txt respected, host fixed to hapai.kiev.ua, bounded sizes. From each page: title, meta
description, headings, visible text blocks, image/icon candidates for the logo. Logo candidates are saved
as files for the release to copy (a partner logo is served from our site, not hot-linked).
"""
from html.parser import HTMLParser
import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

HOST = 'hapai.kiev.ua'
ORIGIN = 'https://' + HOST
PAGES = ('/ua', '/ua/leasing', '/ua/auto-ria', '/ua/avto-iz-es', '/ua/questions/podbor-avto')
AGENT = 'Mozilla/5.0 (compatible; UA-ART-partner-check/1.0)'
MAX_PAGE = 3 * 1024 * 1024
MAX_IMAGE = 1024 * 1024
IMAGE_TYPES = {'image/svg+xml': 'svg', 'image/png': 'png', 'image/webp': 'webp', 'image/jpeg': 'jpg',
               'image/x-icon': 'ico', 'image/vnd.microsoft.icon': 'ico'}
SKIP = {'script', 'style', 'noscript', 'svg', 'template'}
BLOCK = {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'td', 'th', 'dt', 'dd', 'div', 'span', 'a', 'button', 'strong', 'b'}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.headings, self.texts, self.images, self.icons = '', {}, [], [], [], []
        self._skip, self._stack, self._buffer = 0, [], []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or '') for k, v in attrs}
        if tag in SKIP:
            self._skip += 1
        if tag == 'meta' and (a.get('name') or a.get('property')):
            self.meta[(a.get('name') or a.get('property')).lower()] = a.get('content', '')
        if tag == 'link' and 'icon' in a.get('rel', '').lower():
            self.icons.append(a.get('href', ''))
        if tag == 'img':
            self.images.append({k: a.get(k, '') for k in ('src', 'alt', 'class', 'width', 'height')})
        if tag in BLOCK or tag == 'title':
            self._flush()
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag in BLOCK or tag == 'title':
            self._flush(tag)

    def handle_data(self, data):
        if not self._skip:
            self._buffer.append(data)

    def _flush(self, closing=None):
        text = ' '.join(''.join(self._buffer).split())
        self._buffer = []
        tag = self._stack[-1] if self._stack else ''
        if closing and self._stack and self._stack[-1] == closing:
            self._stack.pop()
        if not text:
            return
        if tag == 'title':
            self.title = text
        elif tag in ('h1', 'h2', 'h3', 'h4'):
            self.headings.append((tag, text))
        elif text not in self.texts:
            self.texts.append(text)


def get(url, limit):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != HOST:
        raise ValueError('FOREIGN_HOST')
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept-Language': 'uk,ru;q=0.8'})
    with urllib.request.urlopen(request, timeout=30) as response:
        if urllib.parse.urlsplit(response.geturl()).hostname != HOST:
            raise ValueError('REDIRECT_FOREIGN_HOST')
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError('TOO_LARGE')
        return response.status, response.headers.get_content_type(), body


def robots():
    parser = urllib.robotparser.RobotFileParser()
    try:
        _, _, body = get(ORIGIN + '/robots.txt', 256 * 1024)
        parser.parse(body.decode('utf-8', 'replace').splitlines())
    except urllib.error.HTTPError:
        parser.parse([])
    return parser


def logo_candidates(pages):
    seen = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        for image in page['images']:
            if re.search(r'logo', image['src'] + image['class'] + image['alt'], re.I):
                seen.append(image['src'])
        seen += page['icons'] + [page['meta'].get('og:image', '')]
    return [u for i, u in enumerate(seen) if u and u not in seen[:i]][:12]


def collect(fetch=get):
    allowed = robots() if fetch is get else None
    pages = {}
    for path in PAGES:
        url = ORIGIN + path
        if allowed is not None and not allowed.can_fetch(AGENT, url):
            pages[path] = 'ROBOTS_DISALLOW'
            continue
        try:
            status, _, body = fetch(url, MAX_PAGE)
        except Exception as error:
            pages[path] = type(error).__name__ + ':' + str(error)[:120]
            continue
        page = Page()
        page.feed(body.decode('utf-8', 'replace'))
        page.close()
        pages[path] = {'status': status, 'title': page.title, 'meta': page.meta, 'headings': page.headings,
                       'texts': [t for t in page.texts if 3 <= len(t) <= 600][:400], 'images': page.images[:80],
                       'icons': page.icons}
    files = {}
    for source in logo_candidates(pages):
        url = urllib.parse.urljoin(ORIGIN + '/', source)
        try:
            _, kind, body = fetch(url, MAX_IMAGE)
        except Exception as error:
            files[url] = {'error': type(error).__name__}
            continue
        if kind not in IMAGE_TYPES:
            files[url] = {'error': 'TYPE:' + kind}
            continue
        files[url] = {'type': kind, 'bytes': body, 'sha256': hashlib.sha256(body).hexdigest(),
                      'name': hashlib.sha256(url.encode()).hexdigest()[:12] + '.' + IMAGE_TYPES[kind]}
    return pages, files
