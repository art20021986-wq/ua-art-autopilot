#!/usr/bin/env python3
"""Read-only acceptance of SEO-GROWTH-001 on the live site.

GET only. Public: robots.txt, sitemap.xml, catalog, every published card and every
URL in the sitemap; each page is reduced to SEO facts (status, title, JSON-LD types,
links block, hreflang). Server: the publication worker's state file reduced to
per-card revision progress and retry errors (no CRM data).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

PACKAGE = 'cloud/seo_growth_verify_20261012'
TASKS = ('SEO-GROWTH-VERIFY-20261012', 'SEO-GROWTH-VERIFY-20261012-R2', 'SEO-GROWTH-VERIFY-20261012-R3')
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
STATE = '.crm_public_sync_state.json'
SITE = 'https://www.uaart.com.ua'
LIMIT = 8 * 1024 * 1024
PAGE = re.compile(r'/video/(?:UA-[0-9]{4,}\.html|seo/(?:ua|ru|gu)/[a-z0-9-]+\.html|(?:index|katalog|podbor|info)\.html)')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get(opener, request):
    for attempt in range(3):
        try:
            with opener.open(request, timeout=60) as response:
                return response.status, response.read(LIMIT)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code, None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return 0, None
        time.sleep(2 ** (attempt + 1))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


class Reader:
    def __init__(self, token, opener=None, public_opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self._public = public_opener or urllib.request.build_opener()

    def state(self):
        return get(self._opener, urllib.request.Request(API + STATE, headers={
            'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-seo-verify/1'}))

    def public(self, path):
        if path not in ('/robots.txt', '/sitemap.xml') and not PAGE.fullmatch(path):
            raise ProbeError('PUBLIC_PATH_OUTSIDE_SCOPE')
        return get(self._public, urllib.request.Request(SITE + path + '?seo_verify=%d' % time.time_ns(), headers={
            'User-Agent': 'uaart-seo-verify/1', 'Cache-Control': 'no-cache'}))


def facts(html):
    titles = re.findall(r'<title[^>]*>(.*?)</title>', html, re.S)
    ld = re.findall(r'<script type="application/ld\+json" id="ua-seo-ld">(.*?)</script>', html, re.S)
    types = []
    for block in ld:
        try:
            types = sorted({str(node.get('@type')) for node in json.loads(block).get('@graph', [])})
        except ValueError:
            types = ['INVALID_JSON']
    return {'title': titles[0].strip() if len(titles) == 1 else None, 'title_count': len(titles),
            'h1_count': len(re.findall(r'<h1\b', html)), 'ld_types': types, 'ld_blocks': len(ld),
            'links_block': html.count('id="ua-seo-links"'),
            'hreflang': sorted(re.findall(r'hreflang="([a-zA-Z-]+)"', html)),
            'canonical': re.findall(r'<link rel="canonical" href="([^"]+)"', html)[:2],
            'codes': sorted(set(re.findall(r'UA-[0-9]{4,}', html)))[:30], 'bytes': len(html.encode())}


def worker(raw):
    state = json.loads(raw)
    revisions = state.get('revisions', {})
    return {'cards': len(revisions),
            'retry': {key: {'count': value.get('count'), 'error': str(value.get('error', ''))[:240]}
                      for key, value in sorted(state.get('retry', {}).items())},
            'catalog_retry': state.get('catalog_retry'),
            'last_success': state.get('last_success')}


def collect(reader):
    result = {'pages': {}}
    status, raw = reader.public('/robots.txt')
    result['robots'] = {'http': status, 'body': raw.decode('utf-8', 'replace') if raw else None}
    status, raw = reader.public('/sitemap.xml')
    sitemap = raw.decode('utf-8', 'replace') if raw else ''
    entries = re.findall(r'<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?', sitemap)
    result['sitemap'] = {'http': status, 'urls': len(entries), 'with_lastmod': sum(1 for _, m in entries if m),
                         'lastmod_dates': sorted({m for _, m in entries if m}),
                         'landings': sorted(u for u, _ in entries if '/seo/' in u)}
    paths = ['/video/katalog.html'] + [u[len(SITE):] for u, _ in entries]
    status, raw = reader.public('/video/katalog.html')
    catalog = raw.decode('utf-8', 'replace') if raw else ''
    paths += ['/video/%s.html' % c for c in sorted(set(re.findall(r'href="(UA-[0-9]{4,})\.html"', catalog)))]
    for path in dict.fromkeys(paths):
        status, raw = reader.public(path)
        result['pages'][path] = dict(http=status, **(facts(raw.decode('utf-8', 'replace')) if raw else {}))
    status, raw = reader.state()
    result['worker'] = worker(raw) if status == 200 and raw else {'http': status}
    cards = {p: v for p, v in result['pages'].items() if re.fullmatch(r'/video/UA-[0-9]{4,}\.html', p)}
    result['summary'] = {
        'cards': len(cards),
        'cards_seo_done': sum(1 for v in cards.values() if v.get('links_block') == 1 and v.get('ld_blocks') == 1
                              and 'из Кореи' in (v.get('title') or '')),
        'landings_ok': sum(1 for p, v in result['pages'].items() if '/seo/' in p and v.get('http') == 200),
        'non_200': sorted(p for p, v in result['pages'].items() if v.get('http') != 200)}
    return result


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, data):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    evidence = PACKAGE + '/evidence%s.json' % task[len('SEO-GROWTH-VERIFY-20261012'):].lower().replace('-', '_')
    result = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'],
                                'remote_write_count': 0, **result}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('SEO_VERIFY_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
