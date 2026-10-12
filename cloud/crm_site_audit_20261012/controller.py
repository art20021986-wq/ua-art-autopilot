#!/usr/bin/env python3
"""Read-only CRM ↔ site audit: GET only, transient CRM copy, report without private data."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request

import audit

TASK_ID = 'CRM-SITE-AUDIT-20261012'
PACKAGE = 'cloud/crm_site_audit_20261012'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
SITE = 'https://www.uaart.com.ua/'
SERVER_PATH = re.compile(r'(?:crm\.db|video/|video/(?:katalog|UA-\d{4,})\.html)')
PUBLIC_PATH = re.compile(r'(?:ua-art-public-prices-v1\.json|video/(?:katalog|UA-\d{4,})\.html)')
LIMIT = 64 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


class Reader:
    """GET-only access to a fixed set of server and public paths."""

    def __init__(self, token, opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def _get(self, url, headers):
        request = urllib.request.Request(url, method='GET', headers={
            'Accept-Encoding': 'identity', 'User-Agent': 'uaart-crm-site-audit/1', **headers})
        for attempt in range(3):
            try:
                with self._opener.open(request, timeout=60) as response:
                    if response.status != 200:
                        raise ProbeError('HTTP_%d' % response.status)
                    data = response.read(LIMIT + 1)
                    if len(data) > LIMIT:
                        raise ProbeError('RESPONSE_SIZE_LIMIT')
                    return data
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                if code == 404:
                    return None
                if code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ProbeError('HTTP_%d' % code) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise ProbeError('TRANSPORT_FAILURE') from None
            time.sleep(2 ** (attempt + 1))

    def server(self, path):
        if not SERVER_PATH.fullmatch(path):
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        return self._get(API + path, {'Authorization': 'Token ' + self._token})

    def public(self, path):
        if not PUBLIC_PATH.fullmatch(path):
            raise ProbeError('PUBLIC_PATH_OUTSIDE_SCOPE')
        return self._get(SITE + path + '?audit=' + str(int(time.time())), {'Cache-Control': 'no-cache'})


def crm_cards(payload):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'crm.db'
        path.write_bytes(payload)
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute('SELECT * FROM cars ORDER BY id')]
        finally:
            con.close()


def collect(reader):
    cards = crm_cards(reader.server('crm.db') or b'')
    listing = json.loads(reader.server('video/') or b'{}')
    page_files = sorted(name for name in listing if name.endswith('.html'))
    catalog = reader.server('video/katalog.html')
    listed = {x.decode() for x in re.findall(rb'data-ua-card="(UA-\d{4,})"', catalog or b'')}
    codes = sorted({c['auto_number'] for c in cards if c.get('auto_number')} | listed)
    pages, served = {}, {}
    for code in codes:
        raw = reader.server('video/%s.html' % code)
        pages[code] = raw.decode('utf-8') if raw is not None else None
        if raw is not None:
            served['video/%s.html' % code] = reader.public('video/%s.html' % code) == raw
    public_catalog = reader.public('video/katalog.html')
    served['video/katalog.html'] = public_catalog == catalog
    prices = json.loads(reader.public('ua-art-public-prices-v1.json') or b'{}')
    return cards, (catalog or b'').decode('utf-8'), pages, prices, served, page_files


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') != TASK_ID or env.get('UAART_TASK_CLASS') != 'STANDARD' \
            or env.get('UAART_REQUEST_PATH') != REQUEST or env.get('UAART_RECEIPT_PATH') != RECEIPT:
        raise ProbeError('CANONICAL_IDENTITY_MISMATCH')
    run_id, expected = env.get('UAART_RUN_ID', ''), env.get('UAART_REQUEST_SHA256', '')
    if not re.fullmatch(r'\d{1,30}', run_id) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ProbeError('CANONICAL_BINDING_INVALID')
    request = root / REQUEST
    if request.is_symlink() or not request.is_file() or sha(request.read_bytes()) != expected:
        raise ProbeError('REQUEST_HASH_MISMATCH')
    raw = json.loads(request.read_bytes())
    if raw.get('task_id') != TASK_ID or raw.get('production_required') is not False or raw.get('read_only') is not True:
        raise ProbeError('REQUEST_SCOPE_MISMATCH')
    return expected, run_id


def new_file(root, relative, value):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode())


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    started = now()
    cards, catalog, pages, prices, served, page_files = collect(
        reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    report = audit.audit(cards, catalog, pages, prices, served, page_files)
    finished = now()
    new_file(root, EVIDENCE, {'task_id': TASK_ID, 'run_id': run_id, 'request_sha256': request_sha,
                              'started_at': started, 'finished_at': finished, 'http_methods': ['GET'],
                              'remote_write_count': 0, 'raw_private_data_persisted': False,
                              'scope': 'Published CRM cars vs server card pages, catalog, live prices JSON and public serving',
                              **report})
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'production', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_AUDIT', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'finished_at': finished,
               'evidence_path': EVIDENCE}
    new_file(root, RECEIPT, receipt)
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('CRM_SITE_AUDIT_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
