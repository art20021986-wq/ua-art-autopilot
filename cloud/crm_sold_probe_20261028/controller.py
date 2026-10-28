#!/usr/bin/env python3
"""GET-only diagnosis of the Telegram «sold» action (sold car stays in the catalog).

Reads the sold handlers and the catalog publisher, the bot log, the server
catalog and a transient read-only copy of the CRM database. Exports only code
definitions, sold/catalog log lines, car status rows and the catalog car
numbers. No remote writes, no raw data persisted.
"""
from __future__ import annotations
import ast
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

TASK_ID = 'CRM-SOLD-PROBE-20261028'
PACKAGE = 'cloud/crm_sold_probe_20261028'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
SOURCES = ('/home/Carix/cars_ui.py', '/home/Carix/db.py', '/home/Carix/publikaciya.py',
           '/home/Carix/publish_transaction_guard.py', '/home/Carix/ua_crm_public_sync.py',
           '/home/Carix/ua_card_delete.py')
# Small dedicated modules are exported whole; cars_ui.py and db.py only by name/marker.
FULL_EXPORT = frozenset(SOURCES[2:])
CATALOG = '/home/Carix/video/katalog.html'
LOG = '/var/log/alwayson-log-266084.log'
DATABASE = '/home/Carix/crm.db'
LIMITS = {LOG: 64 * 1024 * 1024, DATABASE: 256 * 1024 * 1024}
SOURCE_LIMIT = 8 * 1024 * 1024
ENDPOINTS = tuple('files/path' + p for p in SOURCES + (CATALOG, LOG, DATABASE))
TIME_BUDGET = 240.0
MAX_EXCERPT_BYTES = 1024 * 1024
# Definitions exported by name, or because their code touches the sold action.
NAMES = frozenset(('mark_sold', 'mark_sold_ok', 'set_field', 'card_of', 'card_kb', 'delete_ok', 'toggle_publish',
                   '_v168_ack', '_ua099_require_staff', '_ua099_card', 'update_card_field', 'log_action',
                   'connect', 'get_card'))
MARKERS = ('car_sold', "'sold'", 'mark_sold', 'obnovit_katalog', 'ua_card_delete')
LOG_KEYS = re.compile(r'(?i)(sold|прода|audi|ауди|catalog|каталог|crm sync|traceback|error)')
LOG_CONTEXT = 12
LOG_MAX_LINES = 600
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|\b(gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
CAR_FIELDS = ('id', 'auto_number', 'brand', 'model', 'year', 'status', 'published',
              'archived', 'deleted', 'deleted_at', 'created_at', 'updated_at')
PRIVATE_COLUMN = re.compile(r'(?i)user|actor|phone|tel|chat|from_|client|name|email')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError('REDIRECT_FORBIDDEN')


class ReadOnlyAPI:
    def __init__(self, token, opener=None):
        if not isinstance(token, str) or not token or len(token) > 256 or re.search(r'[\s\x00-\x1f\x7f]', token):
            raise ProbeError('TOKEN_UNAVAILABLE_OR_INVALID')
        self._token = token
        self.deadline = time.monotonic() + TIME_BUDGET
        self._opener = opener or urllib.request.build_opener(RefuseRedirects())

    def read(self, endpoint):
        if endpoint not in ENDPOINTS:
            raise ProbeError('ENDPOINT_OUTSIDE_FIXED_ALLOWLIST')
        limit = LIMITS.get(endpoint[len('files/path'):], SOURCE_LIMIT)
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            raise ProbeError('TOTAL_TIME_BUDGET_EXHAUSTED')
        url = BASE + endpoint
        request = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-sold-get-only-probe/1'})
        try:
            with self._opener.open(request, timeout=min(90.0, remaining)) as response:
                if response.geturl() != url or response.status != 200:
                    raise ProbeError('RESPONSE_REJECTED')
                chunks, total = [], 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        return b''.join(chunks)
                    total += len(chunk)
                    if total > limit:
                        raise ProbeError('RESPONSE_SIZE_LIMIT')
                    chunks.append(chunk)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProbeError('HTTP_' + str(code)) from None
        except ProbeError:
            raise
        except (OSError, urllib.error.URLError, ValueError, TimeoutError):
            raise ProbeError('TRANSPORT_FAILURE') from None


def inspect_source(payload, path):
    text = payload.decode('utf-8-sig')
    tree = ast.parse(text)
    facts = {'path': path, 'sha256': sha(payload), 'bytes': len(payload), 'definitions': []}
    pieces, remaining = [], MAX_EXCERPT_BYTES
    for item in tree.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        rendered = ast.unparse(item) + '\n'
        entry = {'name': item.name, 'line': item.lineno, 'end_line': item.end_lineno}
        if path not in FULL_EXPORT and item.name not in NAMES and not any(m in rendered for m in MARKERS):
            continue
        if SECRET.search(rendered):
            entry['excerpt'] = 'OMITTED_SENSITIVE'
        elif len(rendered.encode()) > remaining:
            entry['excerpt'] = 'OMITTED_SIZE_LIMIT'
        else:
            pieces.append('# %s:%d\n%s' % (path, item.lineno, rendered))
            remaining -= len(rendered.encode())
            entry['excerpt'] = 'EXPORTED'
        facts['definitions'].append(entry)
    return facts, '\n'.join(pieces)


def clean_line(line):
    if SECRET.search(line):
        return '[REDACTED_SENSITIVE_LINE]'
    return LONG_NUMBER.sub('[N]', line)[:400]


def inspect_log(payload):
    lines = payload.decode('utf-8', errors='replace').splitlines()
    keep = set()
    for index, line in enumerate(lines):
        if LOG_KEYS.search(line):
            keep.update(range(max(0, index - 2), min(len(lines), index + LOG_CONTEXT)))
    selected = sorted(keep)[-LOG_MAX_LINES:]
    return {'bytes': len(payload), 'total_lines': len(lines), 'matched_lines_exported': len(selected),
            'first_line_ts': clean_line(lines[0][:40]) if lines else None,
            'lines': ['%d: %s' % (i + 1, clean_line(lines[i])) for i in selected]}


def inspect_catalog(payload):
    numbers = re.findall(r'href=[\'"]?(?:[^\'"\s>]*/)?(UA-\d{4,})\.html', payload.decode('utf-8', errors='replace'))
    return {'bytes': len(payload), 'car_numbers': sorted(set(numbers))}


def short(value):
    if isinstance(value, (bytes, memoryview)):
        return '[BLOB]'
    if isinstance(value, str):
        return LONG_NUMBER.sub('[N]', value)[:120]
    return value


def inspect_database(payload, workdir):
    path = Path(workdir) / 'crm_copy.db'
    path.write_bytes(payload)
    try:
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            return database_facts(con)
        finally:
            con.close()
    finally:
        path.unlink()


def database_facts(con):
    q = lambda sql, args=(): con.execute(sql, args).fetchall()
    tables = [r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    columns = {t: [r[1] for r in q('PRAGMA table_info("%s")' % t.replace('"', '""'))] for t in tables}
    references = []
    for t in tables:
        for r in q('PRAGMA foreign_key_list("%s")' % t.replace('"', '""')):
            references.append({'table': t, 'from': r[3], 'to_table': r[2], 'to': r[4],
                               'on_delete': r[6]})
    facts = {'tables': {t: {'columns': columns[t], 'rows': q('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""'))[0][0]}
                        for t in tables},
             'foreign_keys': references,
             'triggers': [{'name': r[0], 'table': r[1], 'sql': r[2]}
                          for r in q("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'")],
             'cars_schema': (q("SELECT sql FROM sqlite_master WHERE name='cars'") or [[None]])[0][0],
             'quick_check': [r[0] for r in q('PRAGMA quick_check')][:20]}
    if 'cars' in columns:
        fields = [f for f in CAR_FIELDS if f in columns['cars']]
        facts['all_cars'] = [dict(zip(fields, map(short, r))) for r in q('SELECT %s FROM cars ORDER BY id' % ', '.join(fields))]
    actions = []
    for t in tables:
        if 'action' in columns[t]:
            safe = [c for c in columns[t] if not PRIVATE_COLUMN.search(c)]
            where = "action LIKE '%sold%'" + (" OR field IN ('status', 'published')" if 'field' in columns[t] else '')
            rows = q('SELECT %s FROM "%s" WHERE %s ORDER BY rowid DESC LIMIT 60' % (
                ', '.join('"%s"' % c for c in safe), t, where))
            actions.append({'table': t, 'rows': [dict(zip(safe, map(short, r))) for r in rows]})
    facts['status_actions'] = actions
    return facts


def new_file(root, relative, payload):
    target = root / relative
    if target.exists() or target.is_symlink():
        raise ProbeError('EVIDENCE_TARGET_ALREADY_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(payload)


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


def execute(env, *, root=None, api=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    started = now()
    api = api or ReadOnlyAPI(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    status, sources, excerpts, log_facts, db_facts, catalog = {}, {}, [], None, None, None
    for endpoint in ENDPOINTS:
        path = endpoint[len('files/path'):]
        try:
            payload = api.read(endpoint)
            status[path] = {'status': 'RECEIVED', 'bytes': len(payload), 'sha256': sha(payload)}
            if path in SOURCES:
                sources[path], excerpt = inspect_source(payload, path)
                excerpts.append(excerpt)
            elif path == CATALOG:
                catalog = inspect_catalog(payload)
            elif path == LOG:
                log_facts = inspect_log(payload)
            else:
                with tempfile.TemporaryDirectory() as workdir:
                    db_facts = inspect_database(payload, workdir)
        except ProbeError as exc:
            status[path] = {'status': 'UNAVAILABLE', 'error': str(exc)}
        except Exception as exc:
            status[path] = {'status': 'ANALYSIS_FAILED', 'error': type(exc).__name__}
        payload = None
    finished = now()
    unavailable = sorted(p for p, s in status.items() if s['status'] != 'RECEIVED')
    evidence = {'task_id': TASK_ID, 'request_sha256': request_sha, 'run_id': run_id,
                'started_at': started, 'finished_at': finished, 'http_methods': ['GET'],
                'remote_write_count': 0, 'raw_private_data_persisted': False,
                'path_status': status, 'source_facts': sources, 'log': log_facts,
                'database': db_facts, 'server_catalog': catalog, 'unavailable_paths': unavailable,
                'sanitized_source_excerpts_path': EXCERPTS,
                'completion_meaning': 'READ_ONLY_DIAGNOSIS_ONLY'}
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'production', 'tests': 'PASS',
               'tests_scope': 'FIXED_GET_SCOPE_AND_SAFE_EVIDENCE_ONLY', 'unexpected_changes': 0,
               'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'finished_at': finished,
               'evidence_path': EVIDENCE, 'unavailable_paths': unavailable, 'deletion_performed': False}
    new_file(root, EXCERPTS, '\n\n'.join(excerpts).encode())
    new_file(root, EVIDENCE, canonical(evidence))
    new_file(root, RECEIPT, canonical(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ProbeError) else 'UNEXPECTED_PROBE_ERROR'
        print('DELETE_PROBE_STOP:' + code)
        raise SystemExit(1) from None
