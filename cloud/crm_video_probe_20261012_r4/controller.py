#!/usr/bin/env python3
"""Read-only: why a downloaded diagnostics video does not reach the diag page.

GET only: top-level bot modules (definitions that download media, publish cards or
build the diagnostics page) and bot log lines since 2026-10-12 04:20 UTC that mention
UA-0020, media, diagnostics, publication or errors. Credential-like lines redacted,
URLs and long numbers masked.
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

TASK_ID = 'CRM-VIDEO-PROBE-20261012-R4'
PACKAGE = 'cloud/crm_video_probe_20261012_r4'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path'
HOME = '/home/Carix/'
LOG = '/var/log/alwayson-log-266084.log'
SERVER_PATH = re.compile(r'/home/Carix/(?:[a-z0-9_]+\.py)?|/var/log/alwayson-log-266084\.log')
LIMIT = 64 * 1024 * 1024
MARKERS = ('media_spool', '_v165_spool', 'def save_media', 'iskhodnoe', 'kadry_diagnostiki', 'diag_video',
           "'condition_videos'", 'CRM sync PASS', 'revision', 'ждёт скачивания', '-diag.html')
LOG_FROM = re.compile(r'^Oct 12 (0[4-9]|1\d|2\d):')
LOG_KEYS = re.compile(r'(?i)UA-0020|media|медиа|diag|диагност|spool|sync|publ|публик|скач|download|ffmpeg|'
                      r'traceback|error|exception|warning')
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
        if not SERVER_PATH.fullmatch(path):
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + path, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-video-probe/4'})
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


def clean(line):
    if SECRET.search(line):
        return '[REDACTED]'
    return LONG_NUMBER.sub('[N]', URL.sub('[URL]', line))[:300]


def excerpts(source, name):
    pieces = []
    nodes = []
    for node in ast.parse(source).body:
        nodes.extend(node.body if isinstance(node, ast.ClassDef) else [node])
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = ast.unparse(node)
            if any(m in text for m in MARKERS):
                pieces.append('# %s:%d\n%s\n' % (name, node.lineno, '\n'.join(clean(x) if SECRET.search(x) else x
                                                                             for x in text.splitlines())))
    return '\n'.join(pieces)


def log_facts(payload):
    lines = payload.decode('utf-8', errors='replace').splitlines()
    picked = [clean(x) for x in lines if LOG_FROM.match(x) and LOG_KEYS.search(x)]
    return {'bytes': len(payload), 'total_lines': len(lines), 'last_line_prefix': clean(lines[-1][:20]) if lines else None,
            'matched': len(picked), 'lines': picked[-600:]}


def collect(reader):
    home = json.loads(reader.server(HOME) or b'{}')
    modules = sorted(n for n, v in home.items() if v.get('type') == 'file' and re.fullmatch(r'[a-z0-9_]+\.py', n))
    parts, scanned = [], {}
    for name in modules:
        raw = reader.server(HOME + name)
        try:
            part = excerpts(raw.decode('utf-8'), name) if raw else ''
        except (SyntaxError, UnicodeDecodeError, ValueError):
            part = ''
        if part:
            scanned[name] = sha(raw)
            parts.append(part)
    return '\n'.join(parts), {'modules_matched': scanned, 'log': log_facts(reader.server(LOG) or b'')}


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
                                      ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode())
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
        print('CRM_VIDEO_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
