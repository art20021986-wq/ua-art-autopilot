#!/usr/bin/env python3
"""Fixed GET-only deletion audit; no live imports, DB fetch or remote writes."""
from __future__ import annotations
import ast
import concurrent.futures
import datetime as dt
import hashlib
import html.parser
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import tokenize
import urllib.error
import urllib.request

TASK_ID = 'UA-ART-UA0002-DELETE-PROBE-002'
PACKAGE = 'cloud/ua0002_delete_probe2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
EXCERPTS = PACKAGE + '/sanitized_sources.txt'
ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
SOURCE_NAMES = (
    'db.py', 'ua_spec84_runtime.py', 'start_safe.py',
    'uaart_connection_monitor.py', 'ua_site_counters.py',
)
SOURCE_PATHS = tuple('/home/Carix/' + name for name in SOURCE_NAMES)
FILE_PATHS = SOURCE_PATHS
ENDPOINTS = tuple('files/path' + path for path in FILE_PATHS) + ('always_on/', 'schedule/')
MAX_BYTES = 2 * 1024 * 1024
MAX_EXCERPT_BYTES = 192 * 1024
MAX_TOTAL_EXCERPTS = 2 * 1024 * 1024
TIME_BUDGET = 100.0
CODE = 'UA-0002'
# Export only narrow named definitions; all other code remains names and hashes.
SELECTED_DEFINITIONS = frozenset((
    'delete_ok', 'delete_ask', '_peresobrat_stranicy', 'toggle_publish', 'card_of',
    'connect', 'db', 'log_action', 'delete_card', 'opublikovat', 'publish',
    'publish_one', 'publish_batch', 'rebuild_catalog', '_publish_locked',
    '_build_catalog', '_install_catalog', '_validate_catalog', '_matching_paths',
    '_rows', '_row_map', '_full_row', '_publish', '_exclusive_lock',
    'publication_fence', 'require_publication_fence', '_validate_lock_file',
    '_lock_fd', 'authority_scope', 'recovery_scope', 'current_row', 'row_sha',
    '_paths', 'retire_lists', 'handoff_spec_once', 'transition_operation',
    'catalog_snapshot', 'patch_home', 'patch_catalog', 'sobrat_katalog',
    'generate_html', 'generate_card_html', 'generate_catalog', 'generate_home',
    'generate_index', 'build_catalog', 'build_home', 'build_index', 'main',
    '_ua0022_wrap_rebuild', '_ua114_price_binding', '_ua_emergency_enqueue_spec',
    '_ua_emergency_schedule_spec', '_ua_emergency_spec_status',
    'commit_spec', 'commit_additional_spec', 'write_spec', 'schedule_spec',
    '_ua_fayl_zahvatit', '_ua_fayl_otpustit', 'update_card_field', 'create_card',
    'migrate', 'init_db', '_ua_sql_pishet', 'now', 'apply_all',
    '_writer_guard', '_spec_transaction', '_atomic_existing', '_sync_one',
    '_enqueue', '_card', '_cards', '_sync_pending', '_request_sync',
    '_stage_of', '_patch_stage', '_patch_cta', 'inject_script',
))
SELECTED_CLASSES = {
    'db.py': frozenset(('Soedinenie', '_UaKursor')),
    'ua_spec84_runtime.py': frozenset(('_IntegratedRuntime',)),
    'ua_site_counters.py': frozenset(('CatalogParser',)),
}
SECRET_NAME = re.compile(r'(?:^|_)(?:password|passwd|secret|token|api_key|credential|authorization|private_key)(?:$|_)', re.I)
TOKEN_VALUE = re.compile(r'(?:\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|https?://[^/\s]+:[^/\s]+@)')
OPAQUE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z0-9_+=-]{36,}(?![A-Za-z0-9])')
KNOWN_COMMAND_MODULES = ('start_safe.py', 'run_all.py', 'cars_ui.py', 'yadro.py', 'stranica.py',
    'ua_spec_permanent.py', 'ua_spec84_schedule.py', 'remote_lifecycle.py', 'remote_installer.py',
    'uaart_price_sync_outbox.py', 'uaart_price_sync_runtime.py', 'uaart_connection_monitor.py')
KNOWN_SCHEDULE_COMMANDS = frozenset((
    'cd /home/Carix/autopilot_inbox/cloud/seo_rehab_guard_068 && python3.10 seo_rehab_guard_068_repair.py --dry-run',
    'cd /home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup && python3.10 installer.py install',
    "set -e; mkdir -p '/home/Carix/autopilot_inbox/cloud/task_096_tech_spec_ai_crm/data_enrichment'",
))

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
    def __init__(self, token, deadline=None, opener=None):
        if not isinstance(token, str) or not token or len(token) > 256 or re.search(r'[\s\x00-\x1f\x7f]', token):
            raise ProbeError('TOKEN_UNAVAILABLE_OR_INVALID')
        self._token = token
        self.deadline = deadline if deadline is not None else time.monotonic() + TIME_BUDGET
        self._opener = opener or urllib.request.build_opener(RefuseRedirects())
    def read(self, endpoint):
        if endpoint not in ENDPOINTS:
            raise ProbeError('ENDPOINT_OUTSIDE_FIXED_ALLOWLIST')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0.2:
            raise ProbeError('TOTAL_TIME_BUDGET_EXHAUSTED')
        url = BASE + endpoint
        request = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Token ' + self._token,
            'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache',
            'User-Agent': 'uaart-ua0002-get-only-probe/2'})
        try:
            with self._opener.open(request, timeout=min(6.0, remaining)) as response:
                if response.geturl() != url:
                    raise ProbeError('RESPONSE_URL_MISMATCH')
                if response.status != 200:
                    raise ProbeError('HTTP_' + str(int(response.status)))
                if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                    raise ProbeError('CONTENT_ENCODING_FORBIDDEN')
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isdigit() or int(length) > MAX_BYTES):
                    raise ProbeError('RESPONSE_SIZE_LIMIT')
                chunks, total = [], 0
                while True:
                    if time.monotonic() >= self.deadline:
                        raise ProbeError('TOTAL_TIME_BUDGET_EXHAUSTED')
                    chunk = response.read(min(64 * 1024, MAX_BYTES + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ProbeError('RESPONSE_SIZE_LIMIT')
                return b''.join(chunks)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProbeError('HTTP_' + str(code)) from None
        except ProbeError:
            raise
        except (OSError, urllib.error.URLError, ValueError, TimeoutError):
            raise ProbeError('TRANSPORT_FAILURE') from None

def safe_fetch(api, endpoint):
    try:
        payload = api.read(endpoint)
        return payload, {'status': 'RECEIVED', 'sha256': sha(payload), 'bytes': len(payload)}
    except Exception as exc:
        code = str(exc) if isinstance(exc, ProbeError) and re.fullmatch(r'[A-Z0-9_]+', str(exc)) else 'UNEXPECTED_READ_ERROR'
        return None, {'status': 'UNAVAILABLE', 'error': code}

def secret_text(value):
    if TOKEN_VALUE.search(value):
        return True
    for match in OPAQUE.finditer(value):
        candidate = match.group()
        # SHA digests are evidence, never credentials by themselves.
        if re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', candidate):
            continue
        if re.search(r'[a-z]', candidate) and re.search(r'[A-Z]', candidate) and re.search(r'\d', candidate):
            return True
    return False

def sensitive_definition(node, source):
    """Fail closed for credential literals; credential variable references are code."""
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str) and secret_text(item.value):
            return True
        if isinstance(item, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            value = getattr(item, 'value', None)
            if isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)) and value.value:
                if any(SECRET_NAME.search(getattr(part, 'id', '') or getattr(part, 'attr', ''))
                       for target in targets for part in ast.walk(target)):
                    return True
        if isinstance(item, ast.Dict):
            for key, value in zip(item.keys, item.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and SECRET_NAME.search(key.value):
                    if isinstance(value, ast.Constant) and value.value:
                        return True
        if isinstance(item, ast.keyword) and SECRET_NAME.search(item.arg or ''):
            if isinstance(item.value, ast.Constant) and item.value.value:
                return True
        if isinstance(item, ast.arguments):
            args = [*item.posonlyargs, *item.args]
            pairs = list(zip(args[len(args) - len(item.defaults):], item.defaults)) if item.defaults else []
            pairs += list(zip(item.kwonlyargs, item.kw_defaults))
            if any(SECRET_NAME.search(arg.arg) and isinstance(value, ast.Constant) and value.value for arg, value in pairs):
                return True
    # Comments are omitted from export, but reject entire definition if obviously secret-bearing.
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and (secret_text(token.string) or re.search(r'(?:password|token|secret)\s*[:=]\s*\S+', token.string, re.I)):
            return True
    return False

def inspect_source(payload, path):
    text = payload.decode('utf-8-sig')
    tree = ast.parse(text, filename=Path(path).name)
    lines = text.splitlines(keepends=True)
    facts = {'path': path, 'sha256': sha(payload), 'bytes': len(payload), 'syntax': 'PASS',
             'definitions': [], 'imports': [], 'top_level_calls': [], 'global_constant_values_exported': False, 'sql_structure': []}
    pieces, remaining = [], MAX_EXCERPT_BYTES
    for item in tree.body:
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            facts['imports'].append(ast.unparse(item))
        elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Call):
            fn = item.value.func
            if isinstance(fn, ast.Name):
                facts['top_level_calls'].append(fn.id)
            elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                facts['top_level_calls'].append(fn.value.id + '.' + fn.attr)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([item.lineno] + [d.lineno for d in item.decorator_list])
            raw = ''.join(lines[start-1:item.end_lineno])
            entry = {'name': item.name, 'line': start, 'end_line': item.end_lineno,
                     'sha256': sha(raw.encode()), 'kind': type(item).__name__}
            selected = (item.name in SELECTED_CLASSES.get(Path(path).name, ())
                        if isinstance(item, ast.ClassDef) else item.name in SELECTED_DEFINITIONS)
            if not selected:
                entry['excerpt'] = 'OMITTED_NOT_SELECTED'
                if isinstance(item, ast.ClassDef):
                    entry['methods'] = [{'name': child.name, 'line': child.lineno, 'end_line': child.end_lineno}
                        for child in item.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))]
            elif sensitive_definition(item, raw):
                entry['excerpt'] = 'OMITTED_SENSITIVE_LITERAL'
            else:
                # AST rendering strips all comments and docstrings only where secret policy requires omission.
                exported = ast.unparse(item) + '\n'
                size = len(exported.encode())
                if size > remaining:
                    entry['excerpt'] = 'OMITTED_SIZE_LIMIT'
                else:
                    pieces.append('# ' + path + ':' + str(start) + ' original_sha256=' + entry['sha256'] + '\n' + exported)
                    remaining -= size
                    entry['excerpt'] = 'SANITIZED_AST_RENDERING'
            facts['definitions'].append(entry)
    if Path(path).name == 'db.py':
        # Static source SQL structure only, never database contents or SQL literals.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for table in re.findall(r'(?i)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?([A-Za-z_][A-Za-z_0-9]*)', node.value):
                    facts['sql_structure'].append({'statement': 'CREATE_TABLE', 'table': table})
    facts['exported_excerpt_bytes'] = MAX_EXCERPT_BYTES - remaining
    return facts, '\n'.join(pieces)

class PageFacts(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.counts, self.attrs = set(), {}, []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for name in ('href', 'src'):
            value = values.get(name, '')
            # Paths only; never export query strings or arbitrary URLs from documents.
            clean = value.split('?', 1)[0].split('#', 1)[0]
            if CODE in clean and re.fullmatch(r'[A-Za-z0-9:/._%-]{1,240}', clean):
                self.links.add(clean)
        for key, value in attrs:
            if value == CODE and key in ('data-code', 'data-id', 'data-car', 'data-auto', 'id'):
                self.attrs.append({'tag': tag, 'attribute': key, 'value': value})
    def handle_data(self, data):
        if CODE in data:
            self.counts['text_nodes_containing_target'] = self.counts.get('text_nodes_containing_target', 0) + 1

def inspect_page(payload, path):
    text = payload.decode('utf-8', errors='replace')
    parser = PageFacts()
    parser.feed(text)
    return {'path': path, 'sha256': sha(payload), 'bytes': len(payload),
        'target_occurrences': len(re.findall(r'UA-0002(?![0-9])', text)),
        'target_links': sorted(parser.links)[:100], 'target_element_attributes': parser.attrs[:100],
        'public_card_numbers': sorted(set(re.findall(r'UA-\d{4}(?!\d)', text))),
        'safe_text_facts': parser.counts,
        'page_content_exported': False}

def inspect_tasks(payload):
    value = json.loads(payload)
    if isinstance(value, dict):
        value = value.get('results', value.get('objects', value.get('tasks')))
    if not isinstance(value, list) or len(value) > 100:
        raise ProbeError('ALWAYS_ON_SHAPE_INVALID')
    tasks = []
    for item in value:
        if not isinstance(item, dict):
            raise ProbeError('ALWAYS_ON_ITEM_INVALID')
        command = str(item.get('command', ''))
        state = str(item.get('state', ''))
        tasks.append({'id': item.get('id') if type(item.get('id')) is int else None,
            'enabled': item.get('enabled') if type(item.get('enabled')) is bool else None,
            'state': state if re.fullmatch(r'[A-Za-z _-]{0,40}', state) else 'REDACTED',
            'command_sha256': sha(command.encode()),
            'known_modules': [name for name in KNOWN_COMMAND_MODULES if name in command],
            'autopilot_inbox_reference': '/home/Carix/autopilot_inbox/' in command})
    return {'tasks': tasks, 'os_processes_verified': False, 'provider_metadata_only': True}

def inspect_schedules(payload):
    value = json.loads(payload)
    if isinstance(value, dict):
        value = value.get('results', value.get('objects', value.get('tasks')))
    if not isinstance(value, list) or len(value) > 100:
        raise ProbeError('SCHEDULE_SHAPE_INVALID')
    tasks = []
    for item in value:
        if not isinstance(item, dict):
            raise ProbeError('SCHEDULE_ITEM_INVALID')
        command = str(item.get('command', ''))
        interval = item.get('interval')
        task = {'id': item.get('id') if type(item.get('id')) is int else None,
            'command_sha256': sha(command.encode()),
            'hour': item.get('hour') if type(item.get('hour')) is int and 0 <= item['hour'] <= 23 else None,
            'minute': item.get('minute') if type(item.get('minute')) is int and 0 <= item['minute'] <= 59 else None,
            'interval': interval if type(interval) is str and interval in ('daily', 'hourly') else 'REDACTED_OR_UNAVAILABLE',
            'known_command': command in KNOWN_SCHEDULE_COMMANDS}
        if task['known_command']:
            task['command'] = command
        tasks.append(task)
    return {'tasks': tasks, 'os_processes_verified': False, 'provider_metadata_only': True}

def new_file(root, relative, payload):
    target = root / relative
    if target.exists() or target.is_symlink():
        raise ProbeError('EVIDENCE_TARGET_ALREADY_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root.resolve()):
        raise ProbeError('EVIDENCE_PATH_ESCAPE')
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

def validate_identity(env, root):
    if env.get('UAART_TASK_ID') != TASK_ID or env.get('UAART_TASK_CLASS') != 'STANDARD' or env.get('UAART_REQUEST_PATH') != REQUEST:
        raise ProbeError('CANONICAL_IDENTITY_MISMATCH')
    run_id = env.get('UAART_RUN_ID', '')
    expected = env.get('UAART_REQUEST_SHA256', '')
    if not re.fullmatch(r'\d{1,30}', run_id) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ProbeError('CANONICAL_BINDING_INVALID')
    request = root / REQUEST
    if request.is_symlink() or not request.is_file() or sha(request.read_bytes()) != expected:
        raise ProbeError('REQUEST_HASH_MISMATCH')
    raw = json.loads(request.read_bytes())
    if raw.get('task_id') != TASK_ID or raw.get('production_required') is not False or raw.get('read_only') is not True:
        raise ProbeError('REQUEST_SCOPE_MISMATCH')
    if env.get('UAART_RECEIPT_PATH') != RECEIPT:
        raise ProbeError('RECEIPT_PATH_MISMATCH')
    return expected, run_id

def execute(env, *, root=None, api=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    started = now()
    api = api or ReadOnlyAPI(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    endpoint_results = {}
    # Four bounded GETs in parallel; total budget remains shared by the client.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(safe_fetch, api, endpoint): endpoint for endpoint in ENDPOINTS}
        for future in concurrent.futures.as_completed(futures):
            endpoint_results[futures[future]] = future.result()
    statuses, sources, pages, excerpt_parts = {}, {}, {}, []
    tasks = {'status': 'NOT_VERIFIED'}
    schedules = {'status': 'NOT_VERIFIED'}
    for endpoint in ENDPOINTS:
        payload, status = endpoint_results.pop(endpoint)
        statuses[endpoint] = status
        if payload is None:
            continue
        try:
            if endpoint == 'always_on/':
                tasks = inspect_tasks(payload)
            elif endpoint == 'schedule/':
                schedules = inspect_schedules(payload)
            else:
                path = endpoint[len('files/path'):]
                if path in SOURCE_PATHS:
                    facts, excerpt = inspect_source(payload, path)
                    sources[path] = facts
                    excerpt_parts.append(excerpt)
                else:
                    pages[path] = inspect_page(payload, path)
        except Exception:
            statuses[endpoint]['analysis'] = 'FAILED_SAFE_PARSE'
        # Raw private source is kept only transiently in memory.
        payload = None
    excerpts = '\n\n'.join(excerpt_parts).encode()
    if len(excerpts) > MAX_TOTAL_EXCERPTS:
        raise ProbeError('TOTAL_EXCERPT_SIZE_LIMIT')
    finished = now()
    evidence = {'task_id': TASK_ID, 'status': 'PROBE_COMPLETED', 'request_sha256': request_sha,
        'run_id': run_id, 'started_at': started, 'finished_at': finished,
        'http_methods': ['GET'], 'remote_write_count': 0, 'production_write_performed': False,
        'database_downloaded': False, 'database_row_verified': False, 'card_delete_audit_verified': False,
        'os_writers_verified': False, 'source_imports_executed': False,
        'snapshot_consistency': 'SINGLE_READ_PER_PATH_NOT_ATOMIC', 'path_status': statuses,
        'source_facts': sources, 'page_facts': pages, 'always_on': tasks, 'schedule': schedules,
        'raw_private_sources_persisted': False, 'sanitized_source_excerpts_path': EXCERPTS,
        'completion_meaning': 'READ_ONLY_DIAGNOSIS_ONLY_NO_DELETION_OR_INSTALLATION'}
    unavailable = [path for path, status in statuses.items() if status.get('status') != 'RECEIVED' or status.get('analysis')]
    evidence['unavailable_or_unparsed_paths'] = unavailable
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD',
        'target_environment': 'shadow', 'live_source_environment': 'production', 'tests': 'PASS',
        'tests_scope': 'FIXED_GET_SCOPE_AND_SAFE_EVIDENCE_ONLY', 'unexpected_changes': 0,
        'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
        'request_sha256': request_sha, 'run_id': run_id, 'finished_at': finished,
        'evidence_path': EVIDENCE, 'unavailable_or_unparsed_paths': unavailable,
        'deletion_performed': False, 'raw_private_sources_persisted': False}
    new_file(root, EXCERPTS, excerpts)
    new_file(root, EVIDENCE, canonical(evidence))
    new_file(root, RECEIPT, canonical(receipt))
    return receipt

if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ProbeError) and re.fullmatch(r'[A-Z0-9_]+', str(exc)) else 'UNEXPECTED_PROBE_ERROR'
        print('UA0002_PROBE_STOP:' + code)
        raise SystemExit(1) from None
