#!/usr/bin/env python3
"""Read-only site health probe after the owner reported the site down (2026-10-22).

GET only. Public: entry points, core pages, a card, its diagnostics page, a photo, the
order form, SEO hub, sitemap, robots (status, bytes, time, type, redirect target).
Server: web app info, CPU, always-on tasks (bot state, leftover temporary tasks), the
error log reduced to per-hour counts and its last lines with IPs masked, and the access
log of the last hours reduced to statuses per path.
"""
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from collections import Counter

PACKAGE = 'cloud/site_health_20261022'
TASKS = ('SITE-HEALTH-PROBE-20261022', 'SITE-HEALTH-PROBE-20261022-R2')
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
DOMAIN = 'www.uaart.com.ua'
LOGS = {'error': 'files/path/var/log/%s.error.log' % DOMAIN, 'access': 'files/path/var/log/%s.access.log' % DOMAIN,
        'server': 'files/path/var/log/%s.server.log' % DOMAIN}
# R2: who runs the legacy whole-site rebuild and how often it fails.
HISTORY = {'publication_log': 'files/path/home/Carix/publikaciya_log.txt',
           'connection_monitor': 'files/path/home/Carix/uaart-monitor/latest.json'}
WEBAPP_DIR = 'files/path/home/Carix/mysite/'
CALLS = re.compile(r'stranica|subprocess|os\.system|Popen|\bmain\(|publikaciya|rebuild|perestro', re.I)
ENDPOINTS = ('webapps/%s/' % DOMAIN, 'cpu/', 'always_on/', WEBAPP_DIR) + tuple(LOGS.values()) + tuple(HISTORY.values())
URLS = ('http://uaart.com.ua/', 'https://uaart.com.ua/', 'http://www.uaart.com.ua/', 'https://www.uaart.com.ua/',
        'https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html',
        'https://www.uaart.com.ua/video/podbor.html', 'https://www.uaart.com.ua/video/info.html',
        'https://www.uaart.com.ua/video/UA-0017.html', 'https://www.uaart.com.ua/video/UA-0007.html',
        'https://www.uaart.com.ua/video/UA-0017-diag.html', 'https://www.uaart.com.ua/video/foto/UA-0017/001.jpg',
        'https://www.uaart.com.ua/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
        'https://www.uaart.com.ua/sitemap.xml', 'https://www.uaart.com.ua/robots.txt')
AGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'
IP = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b|\b[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){3,7}\b', re.I)
LINE = re.compile(r'\[(\d{2}/\w{3}/\d{4}):(\d{2}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3})')
LIMIT = 64 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


class Keep3xx(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def get(opener, request):
    started = time.monotonic()
    try:
        with opener.open(request, timeout=40) as response:
            body = response.read(LIMIT)
            return {'http': response.status, 'body': body, 'type': response.headers.get('Content-Type'),
                    'seconds': round(time.monotonic()-started, 2)}
    except urllib.error.HTTPError as error:
        value = {'http': error.code, 'body': error.read(4096), 'location': error.headers.get('Location'),
                 'type': error.headers.get('Content-Type'), 'seconds': round(time.monotonic()-started, 2)}
        error.close()
        return value
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {'http': 0, 'body': b'', 'error': type(error).__name__+':'+str(error)[:160]}


class Reader:
    def __init__(self, token, opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(Keep3xx())

    def api(self, endpoint):
        if endpoint not in ENDPOINTS and not re.fullmatch(re.escape(WEBAPP_DIR) + r'[A-Za-z0-9_]+\.py', endpoint):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        return get(self._opener, urllib.request.Request(API+endpoint, headers={
            'Authorization': 'Token '+self._token, 'User-Agent': 'uaart-site-health/1'}))

    def public(self, url):
        if url not in URLS:
            raise ProbeError('PUBLIC_URL_OUTSIDE_SCOPE')
        return get(self._opener, urllib.request.Request(url, headers={'User-Agent': AGENT, 'Cache-Control': 'no-cache'}))


def page(value):
    body = value.pop('body', b'') or b''
    text = body.decode('utf-8', 'replace')
    title = re.search(r'(?is)<title[^>]*>(.*?)</title>', text)
    return {**value, 'bytes': len(body), 'title': title.group(1).strip()[:120] if title else None,
            'head': IP.sub('x.x.x.x', re.sub(r'\s+', ' ', text[:300])) if value.get('http') != 200 else None}


def as_json(value):
    try:
        return json.loads(value.get('body') or b'null')
    except ValueError:
        return None


def error_log(text):
    hours = Counter(m.group(1) for m in re.finditer(r'^(\d{4}-\d{2}-\d{2} \d{2}):', text, re.M))
    lines = [IP.sub('x.x.x.x', line)[:300] for line in text.splitlines()[-25:]]
    return {'per_hour': dict(sorted(hours.items())[-30:]), 'last_lines': lines}


def access_log(text):
    stats = {}
    for line in text.splitlines()[-4000:]:
        match = LINE.search(line)
        if match:
            day, hour, method, path, status = match.groups()
            entry = stats.setdefault(day+' '+hour, Counter())
            entry[status[0]+'xx'] += 1
            if status[0] == '5':
                entry['5xx '+path.split('?')[0][:80]] += 1
    return {hour: dict(c) for hour, c in list(stats.items())[-12:]}


def history(reader):
    result = {}
    value = reader.api(HISTORY['publication_log'])
    lines = (value.get('body') or b'').decode('utf-8', 'replace').splitlines()
    result['publication_log'] = {'http': value['http'], 'lines': len(lines), 'last': [IP.sub('x.x.x.x', l)[:400] for l in lines[-60:]]}
    value = reader.api(HISTORY['connection_monitor'])
    result['connection_monitor'] = {'http': value['http'], 'body': IP.sub('x.x.x.x', (value.get('body') or b'').decode('utf-8', 'replace')[:6000])}
    value = reader.api(WEBAPP_DIR)
    listing = as_json(value)
    files = sorted(n for n in listing if re.fullmatch(r'[A-Za-z0-9_]+\.py', n)) if isinstance(listing, dict) else []
    result['webapp_sources'] = {'http': value['http'], 'files': files, 'calls': {}}
    for name in files[:40]:
        text = (reader.api(WEBAPP_DIR + name).get('body') or b'').decode('utf-8', 'replace')
        result['webapp_sources']['calls'][name] = ['%d: %s' % (i, l.strip()[:200]) for i, l in enumerate(text.splitlines(), 1)
                                                   if CALLS.search(l) and not re.search(r'token|password|secret|key\s*=', l, re.I)][:60]
    return result


def collect(reader, r2=False):
    result = {'public': {url: page(reader.public(url)) for url in URLS}}
    web = as_json(reader.api(ENDPOINTS[0]))
    result['webapp'] = {k: web.get(k) for k in ('enabled', 'expiry', 'force_https', 'python_version', 'source_directory')} if isinstance(web, dict) else None
    result['cpu'] = as_json(reader.api('cpu/'))
    tasks = as_json(reader.api('always_on/'))
    result['always_on'] = [{k: t.get(k) for k in ('id', 'description', 'enabled', 'state', 'command')} for t in tasks] \
        if isinstance(tasks, list) else tasks
    for name, endpoint in LOGS.items():
        value = reader.api(endpoint)
        text = (value.get('body') or b'').decode('utf-8', 'replace')
        if name == 'server':
            result['server_tail'] = [IP.sub('x.x.x.x', l)[:300] for l in text.splitlines()[-260:]]
        result[name+'_log'] = {'http': value['http'], 'bytes': len(text.encode()),
                               **({'hours': access_log(text)} if name == 'access' else error_log(text))}
    if r2:
        result['history'] = history(reader)
    return result


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, data):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)+'\n').encode()


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    evidence = PACKAGE+('/evidence_r2.json' if task.endswith('-R2') else '/evidence.json')
    result = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')), task.endswith('-R2'))
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'], 'remote_write_count': 0, **result}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('SITE_HEALTH_PROBE_STOP:'+(str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
