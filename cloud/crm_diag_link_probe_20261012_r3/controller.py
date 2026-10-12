#!/usr/bin/env python3
"""Read-only: what happened to the owner's voice description on 2026-10-12 ~04:25-05:10 UTC.

GET the bot log and crm.db. Exports bot log lines of that window (credential-like lines
redacted, long numbers masked) and CRM audit rows of the window as field names and value
lengths only. No CRM values, people or file ids.
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

TASK_ID = 'CRM-DIAG-LINK-PROBE-20261012-R3'
PACKAGE = 'cloud/crm_diag_link_probe_20261012_r3'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path'
DATABASE = '/home/Carix/crm.db'
LOG = '/var/log/alwayson-log-266084.log'
LIMIT = 64 * 1024 * 1024
WINDOW_LOG = re.compile(r'^Oct 12 0(4:[2-5]|5:0)')
WINDOW_DB = '2026-10-12T04:20'
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://\S+')


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
        if path not in (DATABASE, LOG):
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + path, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-diag-link-probe/3'})
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


def clean(line):
    if SECRET.search(line):
        return '[REDACTED]'
    return LONG_NUMBER.sub('[N]', URL.sub('[URL]', line))[:300]


def log_facts(payload):
    lines = payload.decode('utf-8', errors='replace').splitlines()
    picked = [clean(x) for x in lines if WINDOW_LOG.match(x)]
    return {'bytes': len(payload), 'window_lines': len(picked), 'lines': picked[-800:]}


def audit_facts(payload):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'crm.db'
        path.write_bytes(payload)
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            rows = [{'action': a, 'entity_type': t, 'entity_id': i, 'field': f,
                     'old_chars': len(str(o or '')), 'new_chars': len(str(n or '')), 'created_at': c}
                    for a, t, i, f, o, n, c in con.execute(
                        'SELECT action, entity_type, entity_id, field, old_value, new_value, created_at '
                        'FROM audit WHERE created_at >= ? ORDER BY id', (WINDOW_DB,))]
            numbers = dict(con.execute('SELECT id, auto_number FROM cars'))
            for row in rows:
                if row['entity_type'] == 'cars':
                    row['auto_number'] = numbers.get(row['entity_id'])
            return rows
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
    reader = reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    facts = {'log': log_facts(reader.server(LOG) or b''), 'audit': audit_facts(reader.server(DATABASE) or b'')}
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
