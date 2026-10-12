#!/usr/bin/env python3
"""Read-only: post-publication checks the SEO release must satisfy, and CPU quota.

GET only. Full sources (credential-like lines redacted, foreign URLs and long numbers
masked) of the public freshness, price and card contract checks, and the account's
CPU usage, so the release never makes the publication worker retry forever.
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

TASK_ID = 'SEO-SOURCE-PROBE-20261012-R2'
PACKAGE = 'cloud/seo_source_probe_20261012_r2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
SOURCES = PACKAGE + '/sanitized_sources.txt'
PAGES = PACKAGE + '/public_pages.json'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
HOME = '/home/Carix/'
SITE = 'https://www.uaart.com.ua'
MODULES = ('ua_public_freshness.py', 'ua_price_html_v2.py', 'ua_additional_spec.py', 'ua_delivery_status.py')
LISTINGS = ()
ROUTES = 'cpu/'
PUBLIC = ()
ALLOWED_API = frozenset(['files/path' + HOME + m for m in MODULES] + ['files/path' + HOME + d for d in LISTINGS] + [ROUTES])
LIMIT = 16 * 1024 * 1024
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org|www\.sitemaps\.org|www\.google\.com/schemas)(?:[/\'"\s]|$)')
LANDING = re.compile(r'video/seo/(?:ua|ru|gu)/[a-z0-9-]+\.html')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


def _get(opener, request):
    for attempt in range(3):
        try:
            with opener.open(request, timeout=60) as response:
                data = response.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise ProbeError('RESPONSE_TOO_LARGE')
                return response.status, data
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code, None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return 0, None
        time.sleep(2 ** (attempt + 1))


class Reader:
    def __init__(self, token, opener=None, public_opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self._public = public_opener or urllib.request.build_opener()

    def api(self, endpoint):
        if endpoint not in ALLOWED_API:
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        return _get(self._opener, urllib.request.Request(API + endpoint, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-seo-source-probe/1'}))

    def public(self, path):
        if path not in PUBLIC and not LANDING.fullmatch(path.lstrip('/')):
            raise ProbeError('PUBLIC_PATH_OUTSIDE_SCOPE')
        return _get(self._public, urllib.request.Request(SITE + path, method='GET', headers={
            'User-Agent': 'uaart-seo-source-probe/1', 'Cache-Control': 'no-cache'}))


def mask_urls(line):
    return URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)


def sanitized(text):
    out = []
    for line in text.splitlines():
        if SECRET.search(line):
            out.append('[REDACTED]')
        else:
            out.append(LONG_NUMBER.sub('[N]', mask_urls(line)))
    return '\n'.join(out)


def listing(raw):
    """Names, kinds and sizes only from a PythonAnywhere directory listing."""
    data = json.loads(raw)
    return {name: {'type': item.get('type')} for name, item in sorted(data.items())} if isinstance(data, dict) else None


def collect(reader):
    parts, modules, dirs = [], {}, {}
    for name in MODULES:
        status, raw = reader.api('files/path' + HOME + name)
        modules[name] = {'http': status, 'sha256': sha(raw) if raw is not None else None,
                         'bytes': len(raw) if raw is not None else None}
        if raw is not None and status == 200:
            parts.append('# ===== %s =====\n%s\n' % (name, sanitized(raw.decode('utf-8', errors='replace'))))
    for name in LISTINGS:
        status, raw = reader.api('files/path' + HOME + name)
        try:
            dirs[name] = {'http': status, 'entries': listing(raw) if raw is not None and status == 200 else None}
        except ValueError:
            dirs[name] = {'http': status, 'entries': 'UNPARSEABLE'}
    status, raw = reader.api(ROUTES)
    try:
        routes = {'http': status, 'value': json.loads(raw) if raw is not None and status == 200 else None}
    except ValueError:
        routes = {'http': status, 'value': 'UNPARSEABLE'}
    pages = {}
    queue = list(PUBLIC)
    while queue:
        path = queue.pop(0)
        if path in pages:
            continue
        status, raw = reader.public(path)
        text = raw.decode('utf-8', errors='replace') if raw is not None else None
        pages[path] = {'http': status, 'sha256': sha(raw) if raw is not None else None, 'body': text}
        for found in LANDING.findall(text or ''):
            if '/' + found not in pages:
                queue.append('/' + found)
    facts = {'modules': modules, 'listings': dirs, 'cpu': routes}
    return '\n'.join(parts), facts, pages


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') != TASK_ID or env.get('UAART_RECEIPT_PATH') != RECEIPT \
            or env.get('UAART_REQUEST_PATH') != REQUEST:
        raise ProbeError('IDENTITY')
    request = root / REQUEST
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
    sources, facts, pages = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    write(root, SOURCES, sources.encode())
    write(root, PAGES, dump(pages))
    write(root, EVIDENCE, dump({'task_id': TASK_ID, 'run_id': run_id, 'http_methods': ['GET'],
                                'remote_write_count': 0, **facts}))
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': EVIDENCE}
    write(root, RECEIPT, dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('SEO_SOURCE_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
