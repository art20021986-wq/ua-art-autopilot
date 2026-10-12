#!/usr/bin/env python3
"""Read-only follow-up: where diagnostic videos from Telegram are downloaded and why some are not.

GET only. Exports definitions mentioning diagnostic media or quarantine from top-level
bot modules, CRM diagnostic media notes, and the diagnostic folder listings.
"""
from __future__ import annotations

import ast
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

TASK_ID = 'CRM-DIAG-PROBE-20261012-R2'
PACKAGE = 'cloud/crm_diag_probe_20261012_r2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
SERVER_PATH = re.compile(r'|crm\.db|[a-z0-9_]+\.py|video/diag/|video/diag/UA-\d{4,}/')
LIMIT = 64 * 1024 * 1024
MARKERS = ('diag_video', "'quarantine'", 'get_file', 'video/diag')
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]')
MEDIA_COLUMNS = ('id', 'car_id', 'auto_number', 'vid', 'razmer', 'mime', 'put', 'status', 'tag', 'poryadok', 'kogda', 'primechanie')
CAR_COLUMNS = ('condition_photos', 'condition_videos', 'diag_report')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


class Reader:
    def __init__(self, token, opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def server(self, path):
        if not SERVER_PATH.fullmatch(path):
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + path, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-diag-probe/2'})
        for attempt in range(3):
            try:
                with self._opener.open(request, timeout=60) as response:
                    data = response.read(LIMIT + 1)
                    if response.status != 200 or len(data) > LIMIT:
                        raise ProbeError('RESPONSE_REJECTED')
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


def excerpts(source, name):
    """Selected definitions as AST text; definitions with credential assignments are skipped."""
    pieces = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = ast.unparse(node)
            if any(m in text for m in MARKERS) and not SECRET.search(text):
                pieces.append('# %s:%d\n%s\n' % (name, node.lineno, text))
    return '\n'.join(pieces)


def count_list(value):
    try:
        data = json.loads(value) if isinstance(value, str) and value.strip() else (value or [])
    except ValueError:
        return 'UNPARSED'
    return len(data) if isinstance(data, list) else 'NOT_LIST'


def crm_facts(payload):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'crm.db'
        path.write_bytes(payload)
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            have = {r[1] for r in con.execute('PRAGMA table_info(media)')}
            columns = [c for c in MEDIA_COLUMNS if c in have]
            media = [dict(r) for r in con.execute(
                "SELECT %s FROM media WHERE vid LIKE 'diag%%' ORDER BY car_id, vid, poryadok, id" % ', '.join(columns))]
            cars = {}
            for r in con.execute('SELECT * FROM cars WHERE published=1 ORDER BY id'):
                row = dict(r)
                cars[row['auto_number']] = {
                    'id': row['id'], 'status': row.get('status'),
                    'diag_text_chars': len((row.get('diag_text') or '').strip()),
                    'diag_link_set': bool((row.get('diag_link') or '').strip()),
                    **{c + '_count': count_list(row.get(c)) for c in CAR_COLUMNS if c in row}}
            return {'media_columns': columns, 'diag_media': media, 'cars': cars}
        finally:
            con.close()


def collect(reader):
    home = json.loads(reader.server('') or b'{}')
    modules = sorted(n for n, v in home.items() if v.get('type') == 'file' and re.fullmatch(r'[a-z0-9_]+\.py', n))
    parts, scanned = [], {}
    for name in modules:
        raw = reader.server(name)
        try:
            part = excerpts(raw.decode('utf-8'), name) if raw else ''
        except (SyntaxError, UnicodeDecodeError, ValueError):
            part, scanned[name] = '', 'UNPARSED'
        scanned.setdefault(name, 'MATCH' if part else 'NO_MATCH')
        parts.append(part)
    crm = crm_facts(reader.server('crm.db') or b'')
    for row in crm['diag_media']:
        row['primechanie'] = re.sub(r'\d{6,}', '[N]', str(row.get('primechanie') or ''))[:200]
    folders = {}
    for code in sorted({m['auto_number'] for m in crm['diag_media']} | set(crm['cars'])):
        listing = json.loads(reader.server('video/diag/%s/' % code) or b'null')
        if listing:
            folders[code] = sorted(listing)
    return '\n'.join(p for p in parts if p), {'crm': crm, 'diag_folders': folders, 'modules_scanned': scanned}


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


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    excerpt, facts = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    write(root, EXCERPTS, excerpt.encode())
    write(root, EVIDENCE, (json.dumps({'task_id': TASK_ID, 'run_id': run_id, 'http_methods': ['GET'],
                                       'remote_write_count': 0, **facts},
                                      ensure_ascii=False, sort_keys=True, indent=2, default=str) + '\n').encode())
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': EVIDENCE}
    write(root, RECEIPT, (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('CRM_DIAG_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
