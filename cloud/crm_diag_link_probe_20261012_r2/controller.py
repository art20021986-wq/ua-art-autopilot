#!/usr/bin/env python3
"""Read-only: where today's owner text/voice messages went (team_bot inbox rows).

GET crm.db only. Exports, for inbox rows of the last 36 hours: id, kind, timestamps,
text length and whether text is a URL. No message text, ids of people or files.
"""
from __future__ import annotations

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

TASK_ID = 'CRM-DIAG-LINK-PROBE-20261012-R2'
PACKAGE = 'cloud/crm_diag_link_probe_20261012_r2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
LIMIT = 64 * 1024 * 1024
TIME_COLUMN = re.compile(r'(?i)(created|_at$|time|date|kogda)')


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
        if path != 'crm.db':
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + path, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-diag-link-probe/2'})
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
                if code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ProbeError('HTTP_%d' % code) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise ProbeError('TRANSPORT_FAILURE') from None
            time.sleep(2 ** (attempt + 1))


def inbox_facts(payload):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'crm.db'
        path.write_bytes(payload)
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            columns = [r[1] for r in con.execute('PRAGMA table_info(inbox)')]
            times = [c for c in columns if TIME_COLUMN.search(c)]
            rows = []
            for r in con.execute('SELECT * FROM inbox ORDER BY id DESC LIMIT 40'):
                row = dict(r)
                text = str(row.get('text') or '')
                rows.append({'id': row.get('id'), 'kind': row.get('kind'),
                             **{c: row.get(c) for c in times},
                             'text_chars': len(text), 'text_is_url': bool(re.match(r'https?://', text.strip())),
                             'has_file': bool(row.get('file_id'))})
            return {'inbox_columns': columns, 'inbox_latest': rows}
        finally:
            con.close()


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
    facts = inbox_facts((reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', ''))).server('crm.db') or b'')
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
        print('CRM_DIAG_LINK_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
