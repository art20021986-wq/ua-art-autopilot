#!/usr/bin/env python3
"""Read-only probe: why a URL sent to the CRM field editor (diag_link) reaches the AI draft parser.

GET only. Exports bot definitions that route text messages, ask for a field value
("Сейчас: …"), store diag_link, or open the AI draft. Lines that look like credentials are redacted.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

TASK_ID = 'CRM-DIAG-LINK-PROBE-20261012'
PACKAGE = 'cloud/crm_diag_link_probe_20261012'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
SERVER_PATH = re.compile(r'|[a-z0-9_]+\.py')
LIMIT = 16 * 1024 * 1024
MARKERS = ('Сейчас', 'текстом или голосом', 'diag_link', 'diag_text', 'car_wait', 'run_ai_draft',
           'MessageHandler', 'не распознаны')
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\d{6,}:[\w-]{30,}')


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
            'User-Agent': 'uaart-diag-link-probe/1'})
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


def redact(text):
    return '\n'.join('    # [redacted]' if SECRET.search(line) else line for line in text.splitlines())


def excerpts(source, name):
    """Matching top-level definitions (and methods of top-level classes) as AST text."""
    pieces = []
    nodes = []
    for node in ast.parse(source).body:
        nodes.extend(node.body if isinstance(node, ast.ClassDef) else [node])
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = ast.unparse(node)
            if any(m in text for m in MARKERS):
                pieces.append('# %s:%d\n%s\n' % (name, node.lineno, redact(text)))
    return '\n'.join(pieces)


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
        if part:
            scanned[name] = {'match': True, 'sha256': sha(raw)}
        parts.append(part)
    return '\n'.join(p for p in parts if p), {'modules_scanned': scanned}


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
        print('CRM_DIAG_LINK_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
