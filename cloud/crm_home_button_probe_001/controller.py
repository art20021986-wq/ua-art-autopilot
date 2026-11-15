#!/usr/bin/env python3
"""GET-only facts for the CRM bot «🏠 Главная» button (CRM-HOME-BUTTON-001).

Reads team_bot.py and every bot module it imports (directly or through other modules, files in /home/Carix only):
where the bot sets its command list / menu button, where it sends or removes a reply keyboard, how /start and the
message catcher are registered. Exports team_bot.py (secret lines dropped) and only the definitions that touch
these places in other modules; counts only for the rest. No remote writes, no data.
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

TASK_ID = 'CRM-HOME-BUTTON-PROBE-20261115'
PACKAGE = 'cloud/crm_home_button_probe_001'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
HOME = '/home/Carix/'
ENTRY = ('team_bot.py', 'cars_ui.py', 'start_safe.py', 'run_all.py')
FULL_EXPORT = frozenset(('team_bot.py',))
MODULE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,80}\.py$')
MAX_MODULES = 250
SOURCE_LIMIT = 8 * 1024 * 1024
TIME_BUDGET = 600.0
MAX_EXCERPT_BYTES = 1536 * 1024
NAMES = frozenset(('register', 'catch_message', '_v168_start_guard', 'with_stats_button', 'menu_header',
                   'start', 'show_menu', 'post_init', 'build_application', 'menu_cb'))
MARKERS = ('ReplyKeyboard', 'KeyboardButton(', 'ForceReply', 'set_my_commands', 'set_chat_menu_button',
           'MenuButton', 'process_update', 'update_id', 'post_init')
COUNTS = {
    'reply_keyboard_markup': r'ReplyKeyboardMarkup',
    'reply_keyboard_remove': r'ReplyKeyboardRemove',
    'force_reply': r'ForceReply',
    'keyboard_button': r'\bKeyboardButton\(',
    'set_my_commands': r'set_my_commands',
    'menu_button': r'set_chat_menu_button|MenuButton',
    'start_command_handler': r'CommandHandler\(\s*[\'"]start[\'"]',
    'conversation_handler': r'ConversationHandler\(',
    'message_handler': r'MessageHandler\(',
    'application_handler_stop': r'ApplicationHandlerStop',
    'process_update': r'process_update',
    'update_id': r'update_id',
    'post_init': r'post_init',
}
SECRET = re.compile(r'(?i)(token|password|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b'
                    r'|\b(gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')


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


def allowed(endpoint):
    if endpoint == 'files/path' + HOME:
        return True
    name = endpoint[len('files/path' + HOME):] if endpoint.startswith('files/path' + HOME) else ''
    return bool(MODULE.match(name))


class ReadOnlyAPI:
    def __init__(self, token, opener=None):
        if not isinstance(token, str) or not token or len(token) > 256 or re.search(r'[\s\x00-\x1f\x7f]', token):
            raise ProbeError('TOKEN_UNAVAILABLE_OR_INVALID')
        self._token = token
        self.deadline = time.monotonic() + TIME_BUDGET
        self._opener = opener or urllib.request.build_opener(RefuseRedirects())

    def read(self, endpoint):
        if not allowed(endpoint):
            raise ProbeError('ENDPOINT_OUTSIDE_FIXED_ALLOWLIST')
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            raise ProbeError('TOTAL_TIME_BUDGET_EXHAUSTED')
        url = BASE + endpoint
        request = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-crm-home-button-get-only-probe/1'})
        try:
            with self._opener.open(request, timeout=min(60.0, remaining)) as response:
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


def imports(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split('.')[0])
        elif isinstance(node, ast.Call) and getattr(node.func, 'attr', getattr(node.func, 'id', '')) == 'import_module' \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            found.add(node.args[0].value.split('.')[0])
    return found


def inspect_source(payload, name, budget):
    text = payload.decode('utf-8-sig')
    tree = ast.parse(text)
    facts = {'sha256': sha(payload), 'bytes': len(payload),
             'counts': {k: len(re.findall(p, text)) for k, p in COUNTS.items() if re.search(p, text)},
             'definitions': []}
    pieces = []
    for item in tree.body:
        whole = name in FULL_EXPORT
        names = _names(item)
        if not whole and not names:
            continue
        rendered = ast.unparse(item) + '\n'
        if not whole and not (names & NAMES and name == 'cars_ui.py') and not any(m in rendered for m in MARKERS):
            continue
        entry = {'name': ','.join(sorted(names)) or type(item).__name__, 'line': item.lineno, 'end_line': item.end_lineno}
        if SECRET.search(rendered):
            entry['excerpt'] = 'OMITTED_SENSITIVE'
        elif len(rendered.encode()) > budget[0]:
            entry['excerpt'] = 'OMITTED_SIZE_LIMIT'
        else:
            pieces.append('# %s%s:%d\n%s' % (HOME, name, item.lineno, LONG_NUMBER.sub('[N]', rendered)))
            budget[0] -= len(rendered.encode())
            entry['excerpt'] = 'EXPORTED'
        facts['definitions'].append(entry)
    return facts, imports(tree), '\n'.join(pieces)


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
    listing = json.loads(api.read('files/path' + HOME))
    present = {n for n, v in listing.items() if MODULE.match(n) and v.get('type') == 'file'}
    queue = [n for n in ENTRY if n in present]
    seen, status, sources, excerpts, budget = set(queue), {}, {}, [], [MAX_EXCERPT_BYTES]
    while queue and len(sources) + len(status) < MAX_MODULES:
        name = queue.pop(0)
        try:
            facts, found, excerpt = inspect_source(api.read('files/path' + HOME + name), name, budget)
        except ProbeError as exc:
            status[name] = 'UNAVAILABLE:' + str(exc)
            continue
        except Exception as exc:
            status[name] = 'ANALYSIS_FAILED:' + type(exc).__name__
            continue
        facts['imports_local'] = sorted(m + '.py' for m in found if m + '.py' in present)
        sources[name] = facts
        if excerpt:
            excerpts.append(excerpt)
        for module in facts['imports_local']:
            if module not in seen:
                seen.add(module)
                queue.append(module)
    finished = now()
    totals = {}
    for facts in sources.values():
        for key, value in facts['counts'].items():
            totals[key] = totals.get(key, 0) + value
    evidence = {'task_id': TASK_ID, 'request_sha256': request_sha, 'run_id': run_id,
                'started_at': started, 'finished_at': finished, 'http_methods': ['GET'],
                'remote_write_count': 0, 'raw_private_data_persisted': False,
                'modules_read': len(sources), 'modules_unavailable': status, 'modules_not_reached': sorted(queue),
                'totals': totals, 'source_facts': sources, 'sanitized_source_excerpts_path': EXCERPTS,
                'completion_meaning': 'READ_ONLY_DIAGNOSIS_ONLY'}
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'production', 'tests': 'PASS',
               'tests_scope': 'FIXED_GET_SCOPE_AND_SAFE_EVIDENCE_ONLY', 'unexpected_changes': 0,
               'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'finished_at': finished,
               'evidence_path': EVIDENCE, 'modules_read': len(sources), 'deletion_performed': False}
    new_file(root, EXCERPTS, '\n\n'.join(excerpts).encode())
    new_file(root, EVIDENCE, canonical(evidence))
    new_file(root, RECEIPT, canonical(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ProbeError) else 'UNEXPECTED_PROBE_ERROR'
        print('CRM_HOME_BUTTON_PROBE_STOP:' + code)
        raise SystemExit(1) from None
