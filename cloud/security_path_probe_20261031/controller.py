#!/usr/bin/env python3
"""Read-only security probe: what the site answered to requests for the CRM database or admin paths.

The 2026-10-31 AI crawler probe saw a client calling itself meta-externalagent ask for /crm.db,
/video/../crm.db and /admin. GET only. Server: the web app's access logs (current, .1, rotated .gz),
reduced to the matching requests (date, method, path, status, bytes; no IPs, no user agents beyond the
crawler name). Public: each probe path once; only the status and the response size are kept, never a body.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

PACKAGE = 'cloud/security_path_probe_20261031'
TASKS = ('SECURITY-PATH-PROBE-20261031',)
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
DOMAIN = 'www.uaart.com.ua'
LOG = 'files/path/var/log/%s.access.log' % DOMAIN
SITE = 'https://' + DOMAIN
LIMIT = 64 * 1024 * 1024
ROTATED = 14
# Requests for private files or admin paths, and any path that climbs out of a folder.
SUSPECT = re.compile(r'crm\.db|\.db(?:$|[?#])|/admin|\.\.|%2e%2e|\.env|\.git|\.py(?:$|[?#])|/home/', re.I)
PUBLIC = ('/crm.db', '/video/../crm.db', '/video/%2e%2e/crm.db', '/video/crm.db', '/admin')
LINE = re.compile(r'\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) (\S+) "[^"]*" "([^"]*)"')
AGENT = re.compile(r'(meta-externalagent|Googlebot|bingbot|GPTBot|OAI-SearchBot|YandexBot|curl|python|Go-http-client)', re.I)


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


def get(opener, request):
    for attempt in range(3):
        try:
            with opener.open(request, timeout=90) as response:
                return response.status, response.read(LIMIT), response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code, None, ''
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return 0, None, ''
        time.sleep(2 ** (attempt + 1))


class Reader:
    def __init__(self, token, opener=None, public_opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self._public = public_opener or urllib.request.build_opener(NoRedirect())

    def api(self, endpoint):
        if not re.fullmatch(re.escape(LOG) + r'(?:\.1|\.(?:[2-9]|1[0-4])\.gz)?', endpoint):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        status, body, _ = get(self._opener, urllib.request.Request(API + endpoint, headers={
            'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-security-path-probe/1'}))
        return status, body

    def public(self, path):
        """Status, size and type only; the body is dropped here."""
        if path not in PUBLIC:
            raise ProbeError('PUBLIC_PATH_OUTSIDE_SCOPE')
        status, body, kind = get(self._public, urllib.request.Request(SITE + path, headers={
            'User-Agent': 'uaart-security-path-probe/1', 'Cache-Control': 'no-cache'}))
        return {'http': status, 'bytes': len(body) if body else 0, 'content_type': kind.split(';')[0],
                'sqlite_header': bool(body and body.startswith(b'SQLite format 3'))}


def collect(reader):
    hits, lines, days = [], 0, set()
    for suffix in [''] + ['.1'] + ['.%d.gz' % n for n in range(2, ROTATED + 1)]:
        status, raw = reader.api(LOG + suffix)
        if status != 200 or raw is None:
            if suffix:
                break
            raise ProbeError('LOG_UNAVAILABLE')
        text = (gzip.decompress(raw) if suffix.endswith('.gz') else raw).decode('utf-8', 'replace')
        for line in text.splitlines():
            found = LINE.search(line)
            if not found:
                continue
            lines += 1
            day, method, path, code, size, agent = found.groups()
            days.add(day)
            if SUSPECT.search(path):
                name = AGENT.search(agent)
                hits.append({'day': day, 'method': method, 'path': path[:200], 'status': int(code),
                             'bytes': int(size) if size.isdigit() else 0, 'client': name.group(1) if name else 'other'})
    served = [h for h in hits if h['status'] == 200 and re.search(r'crm\.db|\.db(?:$|[?#])', h['path'], re.I)]
    return {'log_lines': lines, 'log_days': len(days), 'suspect_requests': hits[:300], 'suspect_count': len(hits),
            'database_served': served, 'public': {path: reader.public(path) for path in PUBLIC}}


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
    evidence = PACKAGE + '/evidence.json'
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
        print('SECURITY_PATH_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
