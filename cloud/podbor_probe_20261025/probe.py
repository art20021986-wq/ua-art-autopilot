#!/usr/bin/env python3
"""Read-only copy of the live order page and its same-site assets (owner request 2026-10-25).

GET only, public URLs of www.uaart.com.ua, no token. Saves the order (podbor) page, its
stylesheets, scripts, data files and images as base64 in one JSON file, to find where the
«second model» button is rendered before any change on the site.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = 'cloud/podbor_probe_20261025'
TASKS = ('PODBOR-PROBE-20261025',)
ROOT = Path(__file__).resolve().parents[2]
HOME = 'https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk'
ORIGIN = 'https://www.uaart.com.ua'
AGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'
MAX_FILES = 120
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
REFS = re.compile(r'''(?:href|src)\s*=\s*["']([^"'#]+)["']|srcset\s*=\s*["']([^"']+)["']''', re.I)
CSS_REFS = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''', re.I)
JS_REFS = re.compile(r'''["'`]([^"'`\s]+\.(?:json|js|css))["'`]''', re.I)
KEEP = re.compile(r'\.(css|js|json|webp|png|jpe?g|svg|gif|ico|woff2?)$', re.I)


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_site(base, ref):
    url = urllib.parse.urljoin(base, ref.strip().split()[0])
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'www.uaart.com.ua':
        return None
    return urllib.parse.urlunsplit(parts._replace(fragment=''))


def assets(base, text, css=False, js=False):
    found = []
    if css:
        refs = CSS_REFS.findall(text)
    elif js:
        refs = JS_REFS.findall(text)
    else:
        refs = []
        for single, srcset in REFS.findall(text):
            refs += [single] if single else [item.strip() for item in srcset.split(',')]
    for ref in refs:
        url = same_site(base, ref) if ref and not ref.startswith('data:') else None
        if url and KEEP.search(urllib.parse.urlsplit(url).path) and url not in found:
            found.append(url)
    return found


def get(url):
    if not url.startswith(ORIGIN + '/'):
        raise ProbeError('URL_OUTSIDE_SCOPE')
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read(MAX_FILE + 1)
            return response.status, response.headers.get('Content-Type'), body
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, None, b''
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None, b''


def collect(fetch=get):
    status, kind, body = fetch(HOME)
    if status != 200 or not body.rstrip().endswith(b'</html>'):
        raise ProbeError('HOME_UNAVAILABLE')
    files = {HOME: {'http': status, 'type': kind, 'sha256': sha(body), 'b64': base64.b64encode(body).decode()}}
    queue, total = assets(HOME, body.decode('utf-8', 'replace')), len(body)
    while queue and len(files) < MAX_FILES:
        url = queue.pop(0)
        if url in files:
            continue
        status, kind, data = fetch(url)
        entry = {'http': status, 'type': kind, 'bytes': len(data)}
        if status == 200 and len(data) <= MAX_FILE and total + len(data) <= MAX_TOTAL:
            entry.update(sha256=sha(data), b64=base64.b64encode(data).decode())
            total += len(data)
            if url.split('?')[0].endswith('.css'):
                queue += [u for u in assets(url, data.decode('utf-8', 'replace'), css=True) if u not in files]
            if url.split('?')[0].endswith('.js'):
                queue += [u for u in assets(url, data.decode('utf-8', 'replace'), js=True) if u not in files]
        files[url] = entry
    return {'home': HOME, 'files': files, 'total_bytes': total}


def validate_identity(env, root):
    task = env.get('UAART_TASK_ID')
    if task not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
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
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1)+'\n').encode()


def execute(env, *, root=None, fetch=get):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    evidence = PACKAGE + '/live_podbor.json'
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'], 'remote_write_count': 0,
                                **collect(fetch)}))
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
        print('PODBOR_PROBE_STOP:'+(str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
