#!/usr/bin/env python3
"""GET-only diagnosis of why some CRM edits did not reach the site.

Reads the CRM-to-site sync state, the publication guard and the bot log.
Exports revision/retry facts, publication definitions and sync log lines.
No remote writes, no raw data persisted.
"""
from __future__ import annotations
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

TASK_ID = 'CRM-SYNC-STATE-PROBE-20261012'
PACKAGE = 'cloud/crm_sync_state_probe_20261012'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
SOURCES = ('/home/Carix/publish_transaction_guard.py',)
LOG = '/var/log/alwayson-log-266084.log'
STATE_FILE = '/home/Carix/.crm_public_sync_state.json'
LIMITS = {LOG: 64 * 1024 * 1024, STATE_FILE: 8 * 1024 * 1024}
SOURCE_LIMIT = 8 * 1024 * 1024
ENDPOINTS = tuple('files/path' + p for p in SOURCES + (LOG, STATE_FILE))
TIME_BUDGET = 240.0
MAX_EXCERPT_BYTES = 256 * 1024
# Definitions exported by name, or because their code touches the catalog.
NAMES = frozenset(('publish_one', 'rebuild_catalog'))
MARKERS = ('katalog', 'catalog')
LOG_KEYS = re.compile(r'(?i)(CRM sync|UA-0012|UA-0014|UA-0017|UA-0023|publication|публикац|catalog|каталог)')
LOG_CONTEXT = 12
LOG_MAX_LINES = 600
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|\b(gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<![\d-])\+?\d[\d\s()]{8,}\d(?![\d-])')


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
            'User-Agent': 'uaart-sync-state-get-only-probe/1'})
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
        if item.name not in NAMES and not any(m in rendered for m in MARKERS):
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


def inspect_state(payload):
    """Sync state holds only ids, car codes, hashes, timestamps and error texts."""
    state = json.loads(payload)
    clean = lambda text: clean_line(str(text))[:300]
    return {'version': state.get('version'), 'baseline_at': state.get('baseline_at'),
            'last_success': state.get('last_success'),
            'catalog_retry': {k: clean(v) if k == 'code' else v for k, v in (state.get('catalog_retry') or {}).items()},
            'revisions': {i: {'code': r.get('code'), 'delivery_status': r.get('delivery_status')}
                          for i, r in sorted((state.get('revisions') or {}).items())},
            'retry': {i: {'count': r.get('count'), 'after': r.get('after'), 'error': clean(r.get('error', ''))}
                      for i, r in sorted((state.get('retry') or {}).items())}}


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
    status, sources, excerpts, log_facts, state_facts = {}, {}, [], None, None
    for endpoint in ENDPOINTS:
        path = endpoint[len('files/path'):]
        try:
            payload = api.read(endpoint)
            status[path] = {'status': 'RECEIVED', 'bytes': len(payload), 'sha256': sha(payload)}
            if path in SOURCES:
                sources[path], excerpt = inspect_source(payload, path)
                excerpts.append(excerpt)
            elif path == LOG:
                log_facts = inspect_log(payload)
            else:
                state_facts = inspect_state(payload)
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
                'sync_state': state_facts, 'unavailable_paths': unavailable,
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
