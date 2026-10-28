#!/usr/bin/env python3
"""GET-only facts for the CRM button «Фото главной страницы» (HOME-PHOTO-001).

Reads the bot entry point and menu code, the photo intake router, the home page
first screen, the order media folder and the Python package folders (names only:
is Pillow / numpy / OpenCV / onnxruntime already there). Exports code
definitions, the first-screen markup and package names. No remote writes.
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

TASK_ID = 'HOME-PHOTO-PROBE-20261028'
PACKAGE = 'cloud/home_photo_probe_20261028'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
TEAM_BOT = '/home/Carix/team_bot.py'
SOURCES = (TEAM_BOT, '/home/Carix/cars_ui.py', '/home/Carix/crm_photo_intake.py')
# team_bot.py and crm_photo_intake.py are exported whole (secret lines dropped); cars_ui.py by name/marker.
FULL_EXPORT = frozenset((TEAM_BOT, '/home/Carix/crm_photo_intake.py'))
HOME = '/home/Carix/video/index.html'
ORDER_DIR = '/home/Carix/video/order/'
ENDPOINTS = tuple('files/path' + p for p in SOURCES + (HOME, ORDER_DIR)) + ('always_on/',)
# Package folders are discovered level by level, only inside these roots.
LISTING = re.compile(r'^files/path/(usr/local/lib|usr/lib/python3/dist-packages|home/Carix/\.local/lib)'
                     r'(/python3\.\d{1,2}(/(site|dist)-packages)?)?/$')
PACKAGE_NAMES = re.compile(r'(?i)^(pil|pillow|numpy|cv2|opencv|onnxruntime|rembg|torch|scipy|skimage|scikit_image'
                           r'|telegram|python_telegram_bot)([-_.].*)?$')
SOURCE_LIMIT = 8 * 1024 * 1024
TIME_BUDGET = 240.0
MAX_EXCERPT_BYTES = 1024 * 1024
NAMES = frozenset(('with_stats_button', 'menu_header', 'register', 'catch_message', 'cars_list',
                   '_ua099_require_staff', 'start', 'menu', 'main_menu', 'owner_menu', 'is_staff', 'is_owner',
                   'HIDE', 'MORE'))
MARKERS = ('with_stats_button', 'cards_cars', 'crm_leads', 'InlineKeyboardMarkup(rows')
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b'
                    r'|\b(gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
HERO = re.compile(r'<section class="hero ua-order-first">.*?</section>', re.S)
STYLE_IDS = re.compile(r'<style id="([^"]+)"')


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
        if endpoint not in ENDPOINTS and not LISTING.match(endpoint):
            raise ProbeError('ENDPOINT_OUTSIDE_FIXED_ALLOWLIST')
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            raise ProbeError('TOTAL_TIME_BUDGET_EXHAUSTED')
        url = BASE + endpoint
        request = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-home-photo-get-only-probe/1'})
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
                    if total > SOURCE_LIMIT:
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


def _names(item):
    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {item.name}
    if isinstance(item, (ast.Assign, ast.AnnAssign)):
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        return {t.id for t in targets if isinstance(t, ast.Name)}
    return set()


def inspect_source(payload, path):
    text = payload.decode('utf-8-sig')
    tree = ast.parse(text)
    facts = {'path': path, 'sha256': sha(payload), 'bytes': len(payload), 'definitions': []}
    pieces, remaining = [], MAX_EXCERPT_BYTES
    for item in tree.body:
        whole = path in FULL_EXPORT
        names = _names(item)
        if not whole and not names:
            continue
        rendered = ast.unparse(item) + '\n'
        if not whole and not names & NAMES and not any(m in rendered for m in MARKERS):
            continue
        entry = {'name': ','.join(sorted(names)) or type(item).__name__, 'line': item.lineno,
                 'end_line': item.end_lineno}
        if SECRET.search(rendered):
            entry['excerpt'] = 'OMITTED_SENSITIVE'
        elif len(rendered.encode()) > remaining:
            entry['excerpt'] = 'OMITTED_SIZE_LIMIT'
        else:
            pieces.append('# %s:%d\n%s' % (path, item.lineno, LONG_NUMBER.sub('[N]', rendered)))
            remaining -= len(rendered.encode())
            entry['excerpt'] = 'EXPORTED'
        facts['definitions'].append(entry)
    return facts, '\n'.join(pieces)


def inspect_home(payload):
    text = payload.decode('utf-8')
    heroes = HERO.findall(text)
    return {'sha256': sha(payload), 'bytes': len(payload), 'hero_count': len(heroes),
            'hero': heroes[0] if len(heroes) == 1 else None, 'style_ids': STYLE_IDS.findall(text),
            'audi_photo_references': text.count('/video/order/audi_owner.jpg')}


def inspect_listing(payload):
    listing = json.loads(payload)
    return {name: {'type': value.get('type')} for name, value in sorted(listing.items())}


def inspect_always_on(payload):
    tasks = json.loads(payload)
    return [{'id': t.get('id'), 'enabled': t.get('enabled'), 'state': t.get('state'),
             'command': None if SECRET.search(str(t.get('command'))) else t.get('command')} for t in tasks]


def discover_packages(api, status):
    """Walk only the allowed package roots; keep folder names that match PACKAGE_NAMES."""
    found, queue = {}, ['files/path/usr/local/lib/', 'files/path/usr/lib/python3/dist-packages/',
                        'files/path/home/Carix/.local/lib/']
    while queue:
        endpoint = queue.pop(0)
        try:
            listing = inspect_listing(api.read(endpoint))
            status[endpoint] = {'status': 'RECEIVED', 'entries': len(listing)}
        except ProbeError as exc:
            status[endpoint] = {'status': 'UNAVAILABLE', 'error': str(exc)}
            continue
        except Exception as exc:
            status[endpoint] = {'status': 'ANALYSIS_FAILED', 'error': type(exc).__name__}
            continue
        for name, value in listing.items():
            child = endpoint + name + '/'
            if value['type'] == 'directory' and LISTING.match(child):
                queue.append(child)
            elif endpoint.endswith('-packages/') and PACKAGE_NAMES.match(name):
                found.setdefault(endpoint[len('files/path'):], []).append(name)
    return found


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
    status, sources, excerpts, home, order_dir, always_on = {}, {}, [], None, None, None
    for endpoint in ENDPOINTS:
        try:
            payload = api.read(endpoint)
            status[endpoint] = {'status': 'RECEIVED', 'bytes': len(payload), 'sha256': sha(payload)}
            path = endpoint[len('files/path'):]
            if path in SOURCES:
                sources[path], excerpt = inspect_source(payload, path)
                excerpts.append(excerpt)
            elif path == HOME:
                home = inspect_home(payload)
            elif path == ORDER_DIR:
                order_dir = inspect_listing(payload)
            else:
                always_on = inspect_always_on(payload)
        except ProbeError as exc:
            status[endpoint] = {'status': 'UNAVAILABLE', 'error': str(exc)}
        except Exception as exc:
            status[endpoint] = {'status': 'ANALYSIS_FAILED', 'error': type(exc).__name__}
    packages = discover_packages(api, status)
    finished = now()
    unavailable = sorted(e for e in ENDPOINTS if status[e]['status'] != 'RECEIVED')
    evidence = {'task_id': TASK_ID, 'request_sha256': request_sha, 'run_id': run_id,
                'started_at': started, 'finished_at': finished, 'http_methods': ['GET'],
                'remote_write_count': 0, 'raw_private_data_persisted': False,
                'endpoint_status': status, 'source_facts': sources, 'home': home, 'order_dir': order_dir,
                'always_on': always_on, 'packages': packages, 'unavailable_endpoints': unavailable,
                'sanitized_source_excerpts_path': EXCERPTS,
                'completion_meaning': 'READ_ONLY_DIAGNOSIS_ONLY'}
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'production', 'tests': 'PASS',
               'tests_scope': 'FIXED_GET_SCOPE_AND_SAFE_EVIDENCE_ONLY', 'unexpected_changes': 0,
               'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'finished_at': finished,
               'evidence_path': EVIDENCE, 'unavailable_endpoints': unavailable, 'deletion_performed': False}
    new_file(root, EXCERPTS, '\n\n'.join(excerpts).encode())
    new_file(root, EVIDENCE, canonical(evidence))
    new_file(root, RECEIPT, canonical(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ProbeError) else 'UNEXPECTED_PROBE_ERROR'
        print('HOME_PHOTO_PROBE_STOP:' + code)
        raise SystemExit(1) from None
