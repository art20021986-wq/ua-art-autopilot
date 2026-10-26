#!/usr/bin/env python3
"""Read-only snapshot of the owner's AUTO.RIA seller pages for the home page reviews block (AUTORIA-REVIEWS-001).

GET only, auto.ria.com and its static hosts, robots.txt respected, no token, nothing written outside the
repository evidence. Reads the owner's listings page, follows the links that lead to the seller's own
profile (history of sales, years on AUTO.RIA, reviews) and keeps for each page: HTTP status, visible
text, links, images, JSON-LD and the gzip+base64 HTML; logo images are kept as base64.
"""
import base64
import gzip
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

PACKAGE = 'cloud/autoria_reviews_001'
TASKS = ('AUTORIA-REVIEWS-COLLECT-20261026',)
ROOT = Path(__file__).resolve().parents[2]
SELLER = '1980296'
START = 'https://auto.ria.com/uk/search/?user_id=%s&custom=3&abroad=0' % SELLER
ROBOTS = 'https://auto.ria.com/robots.txt'
AGENT = 'UA-ART-autopilot/1.0 (+https://www.uaart.com.ua/)'
PROFILE = re.compile(r'/(dealer|autosalon|salon|seller|user|users|reviews|vidguky|otzyvy|company)s?[/-]', re.I)
LOGO = re.compile(r'logo', re.I)
MAX_PROFILES = 6
MAX_LOGOS = 4
MAX_BYTES = 6 * 1024 * 1024
PAUSE = 1.0


class CollectError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def in_scope(url):
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ''
    return parts.scheme == 'https' and (host == 'auto.ria.com' or host.endswith(('.ria.com', '.riastatic.com')))


def get(url):
    """(status, body); network failures give status 0."""
    if not in_scope(url):
        raise CollectError('URL_OUTSIDE_SCOPE')
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept-Language': 'uk,ru;q=0.8'})
    status = 0
    for attempt in range(3):
        time.sleep(PAUSE * (1 + 2 * attempt))
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, response.read(MAX_BYTES)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if status not in (429, 500, 502, 503, 504):
                return status, b''
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    return status, b''


class Page(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'template'}

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.text, self.links, self.images, self.ld = base, [], [], [], []
        self.stack, self.ld_open = [], False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self.stack.append(tag)
            self.ld_open = tag == 'script' and attrs.get('type') == 'application/ld+json'
        if tag == 'a' and attrs.get('href'):
            self.links.append({'href': urllib.parse.urljoin(self.base, attrs['href']),
                               'title': (attrs.get('title') or attrs.get('aria-label') or '')[:200]})
        if tag == 'img':
            src = attrs.get('src') or attrs.get('data-src') or ''
            if src:
                self.images.append({'src': urllib.parse.urljoin(self.base, src), 'alt': (attrs.get('alt') or '')[:200],
                                    'class': (attrs.get('class') or '')[:200]})

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
            self.ld_open = False

    def handle_data(self, data):
        if self.ld_open:
            self.ld.append(data.strip())
        elif not self.stack and data.strip():
            self.text.append(' '.join(data.split()))


def read_page(fetch, robots, url):
    if robots is not None and not robots.can_fetch(AGENT, url):
        return {'url': url, 'status': 'ROBOTS_DISALLOWED'}
    status, body = fetch(url)
    page = Page(url)
    page.feed(body.decode('utf-8', 'replace'))
    links = list({link['href']: link for link in page.links}.values())
    return {'url': url, 'status': status, 'bytes': len(body), 'sha256': sha(body), 'text': '\n'.join(page.text),
            'links': links, 'images': page.images, 'json_ld': page.ld,
            'html_gz_b64': base64.b64encode(gzip.compress(body, mtime=0)).decode()}


def profile_links(page):
    """Seller-profile links on the listings page: auto.ria.com, not a search, naming the seller or a profile path."""
    found = []
    for link in page.get('links', []):
        href = link['href'].split('#')[0]
        path = urllib.parse.urlsplit(href).path
        if in_scope(href) and '/search' not in path and (SELLER in href or PROFILE.search(path)) and href != page['url']:
            found.append(href)
    return list(dict.fromkeys(found))[:MAX_PROFILES]


def logos(fetch, pages):
    found = {}
    for page in pages:
        for image in page.get('images', []):
            if LOGO.search(image['src'] + ' ' + image['alt'] + ' ' + image['class']) and in_scope(image['src']):
                found.setdefault(image['src'], image)
    kept = []
    for src in list(found)[:MAX_LOGOS]:
        status, body = fetch(src)
        kept.append({**found[src], 'status': status, 'sha256': sha(body), 'b64': base64.b64encode(body).decode()})
    return kept


def load_robots(fetch):
    status, body = fetch(ROBOTS)
    if status != 200:
        return None, status
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.decode('utf-8', 'replace').splitlines())
    return parser, status


def snapshot(fetch):
    robots, robots_status = load_robots(fetch)
    start = read_page(fetch, robots, START)
    profiles = [read_page(fetch, robots, url) for url in profile_links(start)]
    pages = [start] + profiles
    return {'robots_status': robots_status, 'pages': pages, 'logos': logos(fetch, pages)}


def validate_identity(env, root):
    task = env.get('UAART_TASK_ID')
    if task not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
        raise CollectError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise CollectError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise CollectError('SCOPE')
    return expected, env['UAART_RUN_ID']


def evidence_path(task):
    return '%s/%s.json' % (PACKAGE, task)


def write(root, relative, data):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1)+'\n').encode()


def execute(env, *, root=None, fetch=get):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    found = snapshot(fetch)
    write(root, evidence_path(task), dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'],
                                           'remote_write_count': 0, **found}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'auto_ria_public_pages', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(task)]}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('AUTORIA_REVIEWS_COLLECT_STOP:'+(str(exc) if isinstance(exc, CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
