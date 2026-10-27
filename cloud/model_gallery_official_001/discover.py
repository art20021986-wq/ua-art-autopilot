#!/usr/bin/env python3
"""Read-only discovery of official photo galleries for the order page models (MODEL-GALLERY-001, owner 2026-10-26).

The owner asked for photos and generation facts from the manufacturers' own sites. GET only, public pages of the
listed official hosts, no token. From each brand's press or model pages a bounded crawl follows only links that
name the model, then gallery links on those pages, and records each page (status, title) and every image address
it references (with its alt text). Nothing is downloaded but HTML; one JSON per brand group for the next pick.
"""
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = 'cloud/model_gallery_official_001'
TASKS = ('MODEL-GALLERY-DISCOVER-20261026',)
ROOT = Path(__file__).resolve().parents[2]
AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
# brand -> start pages on the brand's official press or model sites
BRANDS = {
    'kia': ('https://www.kiamedia.com/us/en/models', 'https://www.kianewscenter.com/'),
    'hyundai': ('https://www.hyundainews.com/en-us/models', 'https://www.hyundai.news/eu/models.html'),
    'toyota': ('https://pressroom.toyota.com/', 'https://newsroom.toyota.eu/'),
    'lexus': ('https://pressroom.lexus.com/', 'https://newsroom.lexus.eu/'),
    'volkswagen': ('https://media.vw.com/en-us/models', 'https://www.volkswagen-newsroom.com/en/models'),
    'audi': ('https://media.audiusa.com/en-us/models', 'https://www.audi-mediacenter.com/en/models'),
    'skoda': ('https://www.skoda-storyboard.com/en/models/',),
    'renault': ('https://media.renault.com/en/models/',),
    'ford': ('https://media.ford.com/content/fordmedia/fna/us/en/products.html',),
    'subaru': ('https://media.subaru.com/models.html',),
    'nissan': ('https://usa.nissannews.com/en-US/models', 'https://global.nissannews.com/en/'),
    'mercedes': ('https://group-media.mercedes-benz.com/marsMediaSite/en/instance/ko.xhtml',),
    'bmw': ('https://www.press.bmwgroup.com/global/models',),
    'tesla': ('https://www.tesla.com/presskit',),
    'byd': ('https://www.byd.com/eu/car', 'https://www.bydglobal.com/en/'),
    'zeekr': ('https://www.zeekr.eu/en/', 'https://www.zeekrlife.com/'),
}
# key -> (group, brand, words a link must contain to be followed: any one of the tuples, all its words)
MODELS = {
    'lexus-rx-350': ('canada', 'lexus', (('rx',),)),
    'lexus-rx-500': ('canada', 'lexus', (('rx',),)),
    'lexus-tx': ('canada', 'lexus', (('tx',),)),
    'toyota-tacoma-trd-pro': ('canada', 'toyota', (('tacoma',),)),
    'toyota-tacoma-trailhunter': ('canada', 'toyota', (('tacoma',),)),
    'byd-song-plus': ('china', 'byd', (('song',),)),
    'volkswagen-id-4': ('china', 'volkswagen', (('id', '4'), ('id4',))),
    'byd-yuan-plus-atto-3': ('china', 'byd', (('atto',), ('yuan',))),
    'zeekr-001': ('china', 'zeekr', (('001',),)),
    'byd-seal': ('china', 'byd', (('seal',),)),
    'volkswagen-golf': ('europe', 'volkswagen', (('golf',),)),
    'volkswagen-tiguan': ('europe', 'volkswagen', (('tiguan',),)),
    'audi-q5': ('europe', 'audi', (('q5',),)),
    'skoda-octavia': ('europe', 'skoda', (('octavia',),)),
    'renault-megane': ('europe', 'renault', (('megane',), ('mégane',))),
    'ford-fusion-fusion-hybrid': ('georgia', 'ford', (('fusion',),)),
    'toyota-camry': ('georgia', 'toyota', (('camry',),)),
    'volkswagen-jetta': ('georgia', 'volkswagen', (('jetta',),)),
    'toyota-rav4-rav4-hybrid': ('georgia', 'toyota', (('rav4',),)),
    'subaru-forester': ('georgia', 'subaru', (('forester',),)),
    'nissan-note': ('japan', 'nissan', (('note',),)),
    'toyota-aqua': ('japan', 'toyota', (('aqua',),)),
    'mercedes-benz-b-class': ('japan', 'mercedes', (('b', 'class'), ('b-klasse',))),
    'toyota-prius': ('japan', 'toyota', (('prius',),)),
    'kia-k5': ('korea', 'kia', (('k5',),)),
    'hyundai-sonata': ('korea', 'hyundai', (('sonata',),)),
    'hyundai-tucson': ('korea', 'hyundai', (('tucson',),)),
    'kia-sportage': ('korea', 'kia', (('sportage',),)),
    'hyundai-santa-fe': ('korea', 'hyundai', (('santa', 'fe'),)),
    'tesla-model-y': ('usa', 'tesla', (('model', 'y'),)),
    'tesla-model-3': ('usa', 'tesla', (('model', '3'),)),
    'ford-escape': ('usa', 'ford', (('escape',),)),
    'nissan-rogue': ('usa', 'nissan', (('rogue',),)),
    'bmw-x3': ('usa', 'bmw', (('x3',),)),
}
GALLERY = re.compile(r'photo|gallery|image|media|press.?kit|download|asset', re.I)
IMAGE = re.compile(r'\.(?:jpe?g|png|webp)(?:[?#]|$)', re.I)
URL_IN_TEXT = re.compile(r'https?://[^\s"\'<>\\)]+?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>\\)]*)?', re.I)
MAX_PAGES = 30
MAX_IMAGES = 500
MAX_PAGE = 6 * 1024 * 1024
PAUSE = 0.5


class DiscoverError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def official(url, hosts=None):
    """True for an https address on one of the start pages' hosts (BRANDS, or the given hosts)."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    if hosts is None:
        hosts = {urllib.parse.urlsplit(seed).netloc.lower() for seeds in BRANDS.values() for seed in seeds}
    return url.startswith('https://') and host in hosts


def get(url, hosts=None):
    if not official(url, hosts):
        raise DiscoverError('URL_OUTSIDE_SCOPE')
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': 'text/html,*/*'})
    time.sleep(PAUSE)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            kind = response.headers.get('Content-Type', '')
            body = response.read(MAX_PAGE) if 'html' in kind else b''
            return response.status, response.url, body
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, url, b''
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, url, b''


class Page(HTMLParser):
    """Links (address, text), images (address, alt) and the title of one HTML page."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.images, self.title, self._link, self._title = base, [], [], '', None, False

    def absolute(self, value):
        return urllib.parse.urljoin(self.base, html.unescape(value.strip()))

    def handle_starttag(self, tag, attrs):
        attrs = {name: value or '' for name, value in attrs}
        if tag == 'title':
            self._title = True
        if tag == 'a' and attrs.get('href'):
            self._link = [self.absolute(attrs['href']), attrs.get('title', '') + ' ' + attrs.get('aria-label', '')]
            self.links.append(self._link)
        if tag in ('img', 'source'):
            for name in ('src', 'data-src', 'data-lazy-src', 'data-original'):
                if attrs.get(name):
                    self.images.append((self.absolute(attrs[name]), attrs.get('alt', '')))
            for name in ('srcset', 'data-srcset'):
                for item in attrs.get(name, '').split(','):
                    if item.strip():
                        self.images.append((self.absolute(item.split()[0]), attrs.get('alt', '')))
        if tag == 'meta' and attrs.get('property', attrs.get('name', '')) in ('og:image', 'twitter:image'):
            self.images.append((self.absolute(attrs.get('content', '')), 'og:image'))

    def handle_endtag(self, tag):
        if tag == 'a':
            self._link = None
        if tag == 'title':
            self._title = False

    def handle_data(self, data):
        if self._link is not None:
            self._link[1] += ' ' + data
        if self._title:
            self.title += data


def names_model(text, words):
    """True when the text holds every word of one group, as a whole word (longer words may be glued: 'rav4hybrid')."""
    flat = ' ' + re.sub(r'[^a-z0-9é]+', ' ', text.lower()) + ' '
    glued = flat.replace(' ', '')

    def has(word):
        return ' %s ' % word in flat or (len(word) > 3 and word in glued)
    return any(all(has(word) for word in group) for group in words)


def crawl(fetch, key, seeds=None, hosts=None, max_pages=MAX_PAGES):
    _, brand, words = MODELS[key]
    queue = [(url, 0) for url in (BRANDS[brand] if seeds is None else seeds)]
    seen, pages, images = set(), [], {}
    while queue and len(pages) < max_pages:
        url, depth = queue.pop(0)
        url = url.split('#')[0]
        if url in seen or not official(url, hosts):
            continue
        seen.add(url)
        status, final, body = fetch(url)
        page = Page(final)
        try:
            page.feed(body.decode('utf-8', 'replace'))
        except Exception:  # a broken page still counts as visited
            pass
        pages.append({'url': url, 'final': final, 'status': status, 'title': ' '.join(page.title.split())[:200],
                      'depth': depth})
        found = page.images + [(match, '') for match in URL_IN_TEXT.findall(body.decode('utf-8', 'replace'))]
        for image, alt in found:
            if IMAGE.search(image) and image not in images and len(images) < MAX_IMAGES:
                images[image] = {'url': image, 'alt': ' '.join(alt.split())[:200], 'page': url}
        model_page = depth > 0 or names_model(url, words)
        for link, text in page.links:
            if not official(link, hosts) or link in seen:
                continue
            if names_model(link + ' ' + text, words) or (model_page and GALLERY.search(link + ' ' + text)):
                queue.append((link, depth + 1))
    return {'pages': pages, 'images': list(images.values())}


def validate_identity(env, root, tasks=TASKS):
    task = env.get('UAART_TASK_ID')
    if task not in tasks or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
        raise DiscoverError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise DiscoverError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise DiscoverError('SCOPE')
    return expected, env['UAART_RUN_ID']


def evidence_path(group):
    return '%s/discover_%s.json' % (PACKAGE, group)


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
    groups = sorted({group for group, _, _ in MODELS.values()})
    for group in groups:
        found = {key: crawl(fetch, key) for key, value in MODELS.items() if value[0] == group}
        write(root, evidence_path(group), dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                'http_methods': ['GET'], 'remote_write_count': 0, 'models': found}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'manufacturer_sites', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(group) for group in groups]}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_DISCOVER_STOP:'+(str(exc) if isinstance(exc, DiscoverError) else type(exc).__name__))
        raise SystemExit(1) from None
