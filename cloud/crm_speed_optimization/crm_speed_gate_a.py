#!/usr/bin/env python3
'''CRM-SPEED-001 Gate A engine.

This module contains fail-closed, read-mostly logic that:
  * resolves a bounded set of live production inputs under /home/Carix
    (paths only, never recursively scanned),
  * builds AST-based, anchor-checked patched candidate copies of those
    inputs in an isolated per-run directory under
    /home/Carix/qa/crm_speed_task020/<run_id>/,
  * compiles and statically validates the candidates,
  * writes a machine-readable receipt.json and a human-readable REPORT.md.

This module never imports or executes any live CRM/bot/site module, never
writes into production paths, never restarts any process, and never
publishes UA-0009. Missing or ambiguous anchors cause that candidate to be
left unmodified and the overall run to be BLOCKED. A successful run reports
GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL, never deployed or fixed.
'''

import ast
import difflib
import hashlib
import inspect
import json
import os
import stat
import sqlite3
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Optional

CONTEXT_BUNDLE_SHA256 = '2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c'
MEMORY_VERSION_READ = 4

DEFAULT_SOURCE_BASE = '/home/Carix'
LOCK_STALE_SECONDS = 900

KNOWN_BACKUP_SHA256 = 'b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913'
BACKUP_ARCHIVE_REL = 'backups/crm_speed_20260827_1038_before.tar.gz'

REQUIRED_RELATIVE = [
    '.local/lib/python3.10/site-packages/usercustomize.py',
    '.local/lib/python3.13/site-packages/usercustomize.py',
    'start_safe.py',
    'run_all.py',
    'cars_ui.py',
    'avtoperedacha.py',
    'samokontrol.py',
    'db.py',
    'team_bot.py',
    'stranica.py',
    'crm.db',
]
OPTIONAL_RELATIVE = ['yadro.py', 'master_card.py']

NON_TRANSFORM_CANDIDATES = ['db.py', 'team_bot.py', 'stranica.py']


class MissingInput(Exception):
    pass


class SymlinkRejected(Exception):
    pass


@dataclass
class TransformResult:
    ok: bool
    new_source: Optional[str]
    diff: Optional[str]
    anchors_matched: int
    reason: Optional[str]


# ---------------------------------------------------------------------------
# Fingerprinting and bounded input resolution
# ---------------------------------------------------------------------------

def fingerprint_file(path):
    if os.path.islink(path):
        raise SymlinkRejected(path)
    if not os.path.isfile(path):
        raise MissingInput(path)
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return {
        'path': path,
        'size': st.st_size,
        'mode': oct(stat.S_IMODE(st.st_mode)),
        'mtime_ns': st.st_mtime_ns,
        'sha256': h.hexdigest(),
    }


def resolve_required_inputs(source_base):
    info = {}
    blockers = []
    for rel in REQUIRED_RELATIVE:
        full = os.path.join(source_base, rel)
        try:
            info[rel] = fingerprint_file(full)
        except SymlinkRejected:
            blockers.append('symlink_rejected: ' + rel)
        except MissingInput:
            blockers.append('missing_required_input: ' + rel)
    for rel in OPTIONAL_RELATIVE:
        full = os.path.join(source_base, rel)
        try:
            info[rel] = fingerprint_file(full)
        except (SymlinkRejected, MissingInput):
            pass
    return (len(blockers) == 0, info, blockers)


def verify_backup_archive(source_base, expected_sha=None):
    expected_sha = expected_sha or os.environ.get('CRM_SPEED_BACKUP_SHA256', KNOWN_BACKUP_SHA256)
    full = os.path.join(source_base, BACKUP_ARCHIVE_REL)
    try:
        fp = fingerprint_file(full)
    except (SymlinkRejected, MissingInput) as exc:
        return (False, None, 'backup_archive_unavailable: ' + str(exc))
    if fp['sha256'] != expected_sha:
        return (False, fp['sha256'], 'backup_archive_sha256_mismatch')
    return (True, fp['sha256'], None)


# ---------------------------------------------------------------------------
# SafeWriter: the only permitted write surface, bounded to a QA run dir
# ---------------------------------------------------------------------------

class SafeWriter(object):
    def __init__(self, base_dir):
        self.base_dir = os.path.realpath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve(self, rel_path):
        if os.path.isabs(rel_path):
            raise ValueError('absolute paths not allowed: ' + rel_path)
        candidate = os.path.realpath(os.path.join(self.base_dir, rel_path))
        try:
            common = os.path.commonpath([candidate, self.base_dir])
        except ValueError:
            raise ValueError('path escapes base dir: ' + rel_path)
        if common != self.base_dir:
            raise ValueError('path escapes base dir: ' + rel_path)
        return candidate

    def write_bytes(self, rel_path, data):
        target = self._resolve(rel_path)
        if os.path.islink(target) or (os.path.exists(target) and not os.path.isfile(target)):
            raise ValueError('refusing to write non-regular target: ' + rel_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target), prefix='.crm_speed_tmp_')
        try:
            with os.fdopen(fd, 'wb') as fh:
                fh.write(data)
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return target

    def write_text(self, rel_path, text):
        return self.write_bytes(rel_path, text.encode('utf-8'))


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _attr_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return None
    return list(reversed(parts))


def _make_diff(old, new, filename):
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=filename + '.orig', tofile=filename + '.candidate')
    return ''.join(diff)


def _compile_check(source, filename):
    try:
        compile(source, filename, 'exec')
        return True, None
    except SyntaxError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Candidate A: usercustomize.py must not start CRM/bot/generator work on import
# ---------------------------------------------------------------------------

FORBIDDEN_MODULES = {'team_bot', 'run_all', 'start_safe', 'avtoperedacha', 'stranica', 'samokontrol', 'cars_ui'}
STARTUP_CALL_NAMES = {'start', 'run', 'main', 'bootstrap'}


def transform_usercustomize(source, filename='usercustomize.py'):
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return TransformResult(False, None, None, 0, 'syntax_error: ' + str(exc))
    new_body = []
    removed = 0
    for node in tree.body:
        remove = False
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                if top in FORBIDDEN_MODULES:
                    remove = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in FORBIDDEN_MODULES:
                remove = True
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            chain = _attr_chain(node.value.func)
            if chain and chain[-1] in STARTUP_CALL_NAMES:
                remove = True
        if remove:
            removed += 1
        else:
            new_body.append(node)
    if removed == 0:
        return TransformResult(True, source, '', 0, 'no_forbidden_anchors_found_already_inert')
    tree.body = new_body
    try:
        new_source = ast.unparse(ast.fix_missing_locations(tree))
    except Exception as exc:
        return TransformResult(False, None, None, removed, 'unparse_failed: ' + str(exc))
    diff = _make_diff(source, new_source, filename)
    return TransformResult(True, new_source, diff, removed, None)


# ---------------------------------------------------------------------------
# Candidate A2: start_safe.py / run_all.py singleton guard
# ---------------------------------------------------------------------------

SINGLETON_MARKER = '_CRM_SPEED_SINGLETON_GUARD'

SINGLETON_GUARD_SOURCE = '''
_CRM_SPEED_SINGLETON_GUARD = True
import os as _crm_speed_os
import sys as _crm_speed_sys
import time as _crm_speed_time


def _crm_speed_acquire_singleton_lock(lock_path):
    lock_dir = _crm_speed_os.path.dirname(lock_path) or '.'
    _crm_speed_os.makedirs(lock_dir, exist_ok=True)
    try:
        fd = _crm_speed_os.open(lock_path, _crm_speed_os.O_CREAT | _crm_speed_os.O_EXCL | _crm_speed_os.O_WRONLY)
    except FileExistsError:
        try:
            with open(lock_path, 'r') as fh:
                existing = fh.read().strip()
        except OSError:
            existing = ''
        message = 'CRM-SPEED singleton guard: another instance already holds ' + lock_path + ' (' + existing + '). Exiting.'
        _crm_speed_sys.stderr.write(message)
        return None
    payload = str(_crm_speed_os.getpid()) + ' ' + str(_crm_speed_time.time())
    _crm_speed_os.write(fd, payload.encode('utf-8'))
    _crm_speed_os.close(fd)
    return lock_path


def _crm_speed_release_singleton_lock(lock_path):
    try:
        _crm_speed_os.remove(lock_path)
    except OSError:
        pass
'''


def transform_singleton_entry(source, filename='start_safe.py'):
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return TransformResult(False, None, None, 0, 'syntax_error: ' + str(exc))
    main_node = None
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == '__name__'
                    and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value == '__main__'):
                main_node = node
                break
    if main_node is None:
        return TransformResult(False, None, None, 0, 'missing_anchor: no if __name__ == __main__ block found')
    if SINGLETON_MARKER in source:
        return TransformResult(True, source, '', 1, 'singleton_guard_already_present')
    guard_tree = ast.parse(SINGLETON_GUARD_SOURCE)
    insertion_index = 0
    for i, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insertion_index = i + 1
        else:
            break
    tree.body = tree.body[:insertion_index] + guard_tree.body + tree.body[insertion_index:]
    lock_name = filename.replace('/', '_').replace('.', '_') + '.lock'
    call_snippet = (
        "_crm_speed_lock_path = _crm_speed_os.path.join(_crm_speed_os.path.dirname("
        "_crm_speed_os.path.abspath(__file__)), 'qa', 'crm_speed_task020', '" + lock_name + "')\n"
        "_crm_speed_lock_handle = _crm_speed_acquire_singleton_lock(_crm_speed_lock_path)\n"
        "if _crm_speed_lock_handle is None:\n"
        "    _crm_speed_sys.exit(0)\n"
    )
    call_tree = ast.parse(call_snippet)
    main_node.body = call_tree.body + main_node.body
    try:
        new_source = ast.unparse(ast.fix_missing_locations(tree))
    except Exception as exc:
        return TransformResult(False, None, None, 1, 'unparse_failed: ' + str(exc))
    diff = _make_diff(source, new_source, filename)
    return TransformResult(True, new_source, diff, 1, None)


def _exercise_singleton_guard_template():
    ns = {}
    exec(compile(SINGLETON_GUARD_SOURCE, 'singleton_guard_template.py', 'exec'), ns)
    with tempfile.TemporaryDirectory() as td:
        lock_path = os.path.join(td, 'test.lock')
        first = ns['_crm_speed_acquire_singleton_lock'](lock_path)
        second = ns['_crm_speed_acquire_singleton_lock'](lock_path)
        ns['_crm_speed_release_singleton_lock'](lock_path)
        return (first == lock_path) and (second is None)


# ---------------------------------------------------------------------------
# Candidate B/C: avtoperedacha.py debounce queue, no subprocess, short DB ownership
# ---------------------------------------------------------------------------

REQUIRED_AVTOPEREDACHA_FUNCS = {'kolonki_cars', 'otpechatok', 'shag'}
REBUILD_QUEUE_MARKER = '_CRM_SPEED_REBUILD_QUEUE'
SUBPROCESS_ATTRS = {'run', 'Popen', 'call', 'check_call', 'check_output'}

REBUILD_QUEUE_TEMPLATE = '''
_CRM_SPEED_REBUILD_QUEUE = True
import threading as _crm_speed_threading

_crm_speed_rebuild_lock = _crm_speed_threading.Lock()
_crm_speed_rebuild_state = {
    'pending': False,
    'in_progress': False,
    'callback': None,
    'debounce_seconds': 0.5,
    'timer': None,
}


def set_rebuild_callback(callback):
    _crm_speed_rebuild_state['callback'] = callback


def _crm_speed_run_rebuild_now():
    with _crm_speed_rebuild_lock:
        if _crm_speed_rebuild_state['in_progress']:
            _crm_speed_rebuild_state['pending'] = True
            return
        _crm_speed_rebuild_state['in_progress'] = True
        _crm_speed_rebuild_state['pending'] = False
        callback = _crm_speed_rebuild_state['callback']
    try:
        if callback is not None:
            callback()
    finally:
        with _crm_speed_rebuild_lock:
            _crm_speed_rebuild_state['in_progress'] = False
            reschedule = _crm_speed_rebuild_state['pending']
        if reschedule:
            _crm_speed_enqueue_rebuild()


def _crm_speed_enqueue_rebuild():
    with _crm_speed_rebuild_lock:
        existing_timer = _crm_speed_rebuild_state.get('timer')
        if existing_timer is not None and existing_timer.is_alive():
            _crm_speed_rebuild_state['pending'] = True
            return
        timer = _crm_speed_threading.Timer(_crm_speed_rebuild_state['debounce_seconds'], _crm_speed_run_rebuild_now)
        timer.daemon = True
        _crm_speed_rebuild_state['timer'] = timer
        timer.start()
'''


def _is_subprocess_call(call):
    chain = _attr_chain(call.func)
    if not chain:
        return False
    if chain[0] == 'subprocess' and len(chain) >= 2 and chain[1] in SUBPROCESS_ATTRS:
        return True
    if chain[0] == 'os' and len(chain) >= 2 and chain[1] == 'system':
        return True
    return False


def _ensure_sqlite_timeout(tree, seconds=5):
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            chain = _attr_chain(node.func)
            if chain and chain[-1] == 'connect' and 'sqlite3' in chain:
                has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
                if not has_timeout:
                    node.keywords.append(ast.keyword(arg='timeout', value=ast.Constant(value=seconds)))
                    count += 1
    return count


def transform_avtoperedacha(source, filename='avtoperedacha.py'):
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return TransformResult(False, None, None, 0, 'syntax_error: ' + str(exc))

    found_funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    missing = REQUIRED_AVTOPEREDACHA_FUNCS - found_funcs
    if missing:
        return TransformResult(False, None, None, 0, 'missing_anchor_functions: ' + ','.join(sorted(missing)))

    class SubprocessRemover(ast.NodeTransformer):
        def __init__(self):
            self.removed = 0

        def visit_Expr(self, node):
            call = node.value
            awaited = isinstance(call, ast.Await)
            if awaited:
                call = call.value
            if isinstance(call, ast.Call) and _is_subprocess_call(call):
                self.removed += 1
                new_call = ast.Call(func=ast.Name(id='_crm_speed_enqueue_rebuild', ctx=ast.Load()), args=[], keywords=[])
                return ast.copy_location(ast.Expr(value=new_call), node)
            return node

    remover = SubprocessRemover()
    tree = remover.visit(tree)
    ast.fix_missing_locations(tree)

    timeout_added = _ensure_sqlite_timeout(tree)
    already_has_queue = REBUILD_QUEUE_MARKER in source

    if remover.removed == 0 and timeout_added == 0 and already_has_queue:
        return TransformResult(True, source, '', len(REQUIRED_AVTOPEREDACHA_FUNCS), 'already_transformed_no_further_changes')

    if not already_has_queue:
        queue_tree = ast.parse(REBUILD_QUEUE_TEMPLATE)
        insertion_index = 0
        for i, node in enumerate(tree.body):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insertion_index = i + 1
            else:
                break
        tree.body = tree.body[:insertion_index] + queue_tree.body + tree.body[insertion_index:]

    try:
        new_source = ast.unparse(ast.fix_missing_locations(tree))
    except Exception as exc:
        return TransformResult(False, None, None, remover.removed, 'unparse_failed: ' + str(exc))

    diff = _make_diff(source, new_source, filename)
    anchors_total = len(REQUIRED_AVTOPEREDACHA_FUNCS) + remover.removed + timeout_added
    return TransformResult(True, new_source, diff, anchors_total, None)


# ---------------------------------------------------------------------------
# Candidate C: samokontrol.py short DB ownership (busy timeout)
# ---------------------------------------------------------------------------

REQUIRED_SAMOKONTROL_FUNCS = {'kolonki', 'proverit_bazu'}


def transform_samokontrol(source, filename='samokontrol.py'):
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return TransformResult(False, None, None, 0, 'syntax_error: ' + str(exc))
    found_funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    missing = REQUIRED_SAMOKONTROL_FUNCS - found_funcs
    if missing:
        return TransformResult(False, None, None, 0, 'missing_anchor_functions: ' + ','.join(sorted(missing)))
    added = _ensure_sqlite_timeout(tree)
    if added == 0:
        return TransformResult(True, source, '', len(REQUIRED_SAMOKONTROL_FUNCS), 'timeout_already_present')
    try:
        new_source = ast.unparse(ast.fix_missing_locations(tree))
    except Exception as exc:
        return TransformResult(False, None, None, added, 'unparse_failed: ' + str(exc))
    diff = _make_diff(source, new_source, filename)
    return TransformResult(True, new_source, diff, len(REQUIRED_SAMOKONTROL_FUNCS) + added, None)


# ---------------------------------------------------------------------------
# Candidate D: cars_ui.py administrator routes become text-only
# ---------------------------------------------------------------------------

REQUIRED_ADMIN_FUNCS = ['gallery', 'video_gallery', 'diag_photo_show', 'diag_video_show']
MEDIA_SEND_ATTRS = {'reply_photo', 'reply_video', 'send_photo', 'send_video', 'reply_media_group', 'send_media_group'}
TEXT_ONLY_MARKER = '_CRM_SPEED_TEXT_ONLY_ADMIN'

TEXT_ONLY_HELPER_TEMPLATE = '''
_CRM_SPEED_TEXT_ONLY_ADMIN = True
import inspect as _crm_speed_inspect


def _crm_speed_format_media_summary_text(kind='media', label=None, count=None):
    parts = [str(kind)]
    if count is not None:
        parts.append('x' + str(count))
    if label:
        parts.append(str(label))
    return '[CRM] ' + ' '.join(parts)


def _crm_speed_send_text_media_summary_sync(target, kind='media', label=None, count=None):
    text = _crm_speed_format_media_summary_text(kind, label, count)
    sender = getattr(target, 'reply_text', None) or getattr(target, 'send_message', None)
    if sender is None:
        return None
    return sender(text)


async def _crm_speed_send_text_media_summary_async(target, kind='media', label=None, count=None):
    text = _crm_speed_format_media_summary_text(kind, label, count)
    sender = getattr(target, 'reply_text', None) or getattr(target, 'send_message', None)
    if sender is None:
        return None
    result = sender(text)
    if _crm_speed_inspect.isawaitable(result):
        result = await result
    return result
'''


def find_reachable_media_calls(source, func_names):
    tree = ast.parse(source)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in func_names:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr in MEDIA_SEND_ATTRS:
                    hits.append((node.name, sub.func.attr, getattr(sub, 'lineno', -1)))
    return hits


def transform_cars_ui(source, filename='cars_ui.py'):
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return TransformResult(False, None, None, 0, 'syntax_error: ' + str(exc))

    func_nodes = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in REQUIRED_ADMIN_FUNCS:
            func_nodes[node.name] = node
    missing = set(REQUIRED_ADMIN_FUNCS) - set(func_nodes)
    if missing:
        return TransformResult(False, None, None, 0, 'missing_anchor_functions: ' + ','.join(sorted(missing)))

    counters = {'replaced': 0}

    class MediaCallRewriter(ast.NodeTransformer):
        def visit_Expr(self, node):
            self.generic_visit(node)
            value = node.value
            awaited = isinstance(value, ast.Await)
            call = value.value if awaited else value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in MEDIA_SEND_ATTRS:
                counters['replaced'] += 1
                target_expr = call.func.value
                attr = call.func.attr
                if 'video' in attr:
                    kind = 'video'
                elif 'photo' in attr:
                    kind = 'photo'
                else:
                    kind = 'media'
                helper_name = '_crm_speed_send_text_media_summary_async' if awaited else '_crm_speed_send_text_media_summary_sync'
                new_call = ast.Call(
                    func=ast.Name(id=helper_name, ctx=ast.Load()),
                    args=[target_expr],
                    keywords=[ast.keyword(arg='kind', value=ast.Constant(value=kind))],
                )
                new_value = ast.Await(value=new_call) if awaited else new_call
                return ast.copy_location(ast.Expr(value=new_value), node)
            return node

    rewriter = MediaCallRewriter()
    for name, node in func_nodes.items():
        node.body = [rewriter.visit(stmt) for stmt in node.body]
        ast.fix_missing_locations(node)

    replaced = counters['replaced']
    already_has_helpers = TEXT_ONLY_MARKER in source

    if replaced == 0 and already_has_helpers:
        return TransformResult(True, source, '', len(func_nodes), 'already_text_only_no_media_calls_found')

    if not already_has_helpers:
        helper_tree = ast.parse(TEXT_ONLY_HELPER_TEMPLATE)
        insertion_index = 0
        for i, node in enumerate(tree.body):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insertion_index = i + 1
            else:
                break
        tree.body = tree.body[:insertion_index] + helper_tree.body + tree.body[insertion_index:]

    try:
        new_source = ast.unparse(ast.fix_missing_locations(tree))
    except Exception as exc:
        return TransformResult(False, None, None, replaced, 'unparse_failed: ' + str(exc))

    diff = _make_diff(source, new_source, filename)
    return TransformResult(True, new_source, diff, replaced + len(func_nodes), None)


# ---------------------------------------------------------------------------
# Candidate processing pipeline
# ---------------------------------------------------------------------------

TRANSFORM_MAP = {
    '.local/lib/python3.10/site-packages/usercustomize.py': transform_usercustomize,
    '.local/lib/python3.13/site-packages/usercustomize.py': transform_usercustomize,
    'start_safe.py': transform_singleton_entry,
    'run_all.py': transform_singleton_entry,
    'avtoperedacha.py': transform_avtoperedacha,
    'samokontrol.py': transform_samokontrol,
    'cars_ui.py': transform_cars_ui,
}


def _process_candidates(source_base, writer, input_info):
    candidates = {}
    candidate_sources = {}
    orig_sources = {}
    core_ok = True
    compile_ok_all = True

    for rel, transform_fn in TRANSFORM_MAP.items():
        if rel not in input_info:
            candidates[rel] = {'status': 'SKIPPED_MISSING_INPUT'}
            core_ok = False
            continue
        full_path = os.path.join(source_base, rel)
        try:
            with open(full_path, 'r', encoding='utf-8') as fh:
                source_text = fh.read()
        except OSError as exc:
            candidates[rel] = {'status': 'READ_ERROR', 'error': str(exc)}
            core_ok = False
            continue
        orig_sources[rel] = source_text
        result = transform_fn(source_text, rel)
        safe_name = rel.replace('/', '__')
        writer.write_text(safe_name + '.orig.py', source_text)
        entry = {'anchors_matched': result.anchors_matched, 'reason': result.reason}
        if result.ok and result.new_source is not None:
            compile_ok, compile_err = _compile_check(result.new_source, rel)
            writer.write_text(safe_name + '.candidate.py', result.new_source)
            writer.write_text(safe_name + '.diff', result.diff or '')
            entry['status'] = 'TRANSFORMED'
            entry['compiles'] = compile_ok
            entry['compile_error'] = compile_err
            entry['candidate_sha256'] = hashlib.sha256(result.new_source.encode('utf-8')).hexdigest()
            candidate_sources[rel] = result.new_source
            if not compile_ok:
                compile_ok_all = False
                core_ok = False
        else:
            entry['status'] = 'BLOCKED_LEFT_UNMODIFIED'
            core_ok = False
        candidates[rel] = entry

    for rel in NON_TRANSFORM_CANDIDATES:
        if rel not in input_info:
            candidates[rel] = {'status': 'SKIPPED_MISSING_INPUT'}
            continue
        full_path = os.path.join(source_base, rel)
        try:
            with open(full_path, 'r', encoding='utf-8') as fh:
                source_text = fh.read()
        except OSError as exc:
            candidates[rel] = {'status': 'READ_ERROR', 'error': str(exc)}
            continue
        compile_ok, compile_err = _compile_check(source_text, rel)
        safe_name = rel.replace('/', '__')
        writer.write_text(safe_name + '.orig.py', source_text)
        candidates[rel] = {
            'status': 'SNAPSHOT_ONLY_NO_TRANSFORM_DEFINED',
            'compiles': compile_ok,
            'compile_error': compile_err,
        }
        if not compile_ok:
            compile_ok_all = False

    return candidates, candidate_sources, orig_sources, core_ok, compile_ok_all


def _percentile(values, pct):
    if not values:
        return None
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    d0 = values_sorted[f] * (c - k)
    d1 = values_sorted[c] * (k - f)
    return d0 + d1


def _measure_synthetic_admin_latency(samples=20):
    ns = {}
    exec(compile(TEXT_ONLY_HELPER_TEMPLATE, 'text_only_helper_template.py', 'exec'), ns)

    class FakeTarget(object):
        def reply_text(self, text):
            time.sleep(0.001)
            return 'ok'

    target = FakeTarget()
    durations = []
    for _ in range(samples):
        start = time.perf_counter()
        ns['_crm_speed_send_text_media_summary_sync'](target, kind='photo', count=3)
        durations.append(time.perf_counter() - start)
    return durations


def _run_behavior_validations(candidate_sources, orig_sources):
    checks = {}

    cars_src = candidate_sources.get('cars_ui.py')
    if cars_src:
        hits = find_reachable_media_calls(cars_src, REQUIRED_ADMIN_FUNCS)
        checks['cars_ui_text_only_ok'] = (len(hits) == 0)
        checks['cars_ui_media_hits'] = hits
    else:
        checks['cars_ui_text_only_ok'] = False
        checks['cars_ui_media_hits'] = None

    avt_src = candidate_sources.get('avtoperedacha.py')
    if avt_src:
        tree = ast.parse(avt_src)
        remaining = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_subprocess_call(n)]
        checks['avtoperedacha_no_subprocess_ok'] = (len(remaining) == 0)
    else:
        checks['avtoperedacha_no_subprocess_ok'] = False

    singleton_ok = True
    for rel in ('start_safe.py', 'run_all.py'):
        src = candidate_sources.get(rel)
        if not src or SINGLETON_MARKER not in src:
            singleton_ok = False
    if singleton_ok:
        singleton_ok = _exercise_singleton_guard_template()
    checks['singleton_guard_ok'] = singleton_ok

    det_ok = True
    for rel, fn in TRANSFORM_MAP.items():
        orig = orig_sources.get(rel)
        if orig is None:
            continue
        first = fn(orig, rel)
        for _ in range(9):
            again = fn(orig, rel)
            if (again.ok, again.new_source, again.anchors_matched) != (first.ok, first.new_source, first.anchors_matched):
                det_ok = False
    checks['deterministic_repeat_ok'] = det_ok

    latency_samples = _measure_synthetic_admin_latency()
    p95 = _percentile(latency_samples, 95)
    checks['synthetic_latency_p95_seconds'] = p95
    checks['synthetic_latency_ok'] = bool(p95 is not None and p95 <= 2.0)

    return checks


# ---------------------------------------------------------------------------
# UA-0009 bounded, read-only evidence
# ---------------------------------------------------------------------------

MAX_TABLES_SCANNED = 25
MAX_COLUMNS_SCANNED = 25


def inspect_ua0009_readonly(db_path, keyword='UA-0009', timeout=3.0):
    if os.path.islink(db_path) or not os.path.isfile(db_path):
        return {'ok': False, 'reason': 'db_unavailable'}
    uri = 'file:' + os.path.abspath(db_path) + '?mode=ro'
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.OperationalError as exc:
        return {'ok': False, 'reason': 'connect_failed: ' + str(exc)}
    matches = []
    try:
        conn.execute('PRAGMA query_only = ON;')
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()][:MAX_TABLES_SCANNED]
        for table in tables:
            try:
                cur2 = conn.execute('PRAGMA table_info(' + table + ');')
                cols = [c[1] for c in cur2.fetchall()][:MAX_COLUMNS_SCANNED]
            except sqlite3.OperationalError:
                continue
            for col in cols:
                try:
                    query = 'SELECT COUNT(*) FROM ' + table + ' WHERE ' + col + ' LIKE ?'
                    cur3 = conn.execute(query, ('%' + keyword + '%',))
                    count = cur3.fetchone()[0]
                    if count:
                        matches.append({'table': table, 'column': col, 'count': count})
                except sqlite3.OperationalError:
                    continue
        quick_check_row = conn.execute('PRAGMA quick_check;').fetchone()
        return {'ok': True, 'matches': matches, 'quick_check': quick_check_row[0] if quick_check_row else None}
    except sqlite3.OperationalError as exc:
        return {'ok': False, 'reason': 'locked_or_error: ' + str(exc)}
    finally:
        conn.close()


def _run_ua0009_stage(source_base, input_info):
    checks = {}
    if 'crm.db' not in input_info:
        checks['ua0009_inspection_ok'] = False
        checks['ua0009_evidence'] = {'reason': 'crm_db_missing'}
        return checks
    db_path = os.path.join(source_base, 'crm.db')
    before_fp = input_info['crm.db']
    result = inspect_ua0009_readonly(db_path)
    try:
        after_fp = fingerprint_file(db_path)
    except (SymlinkRejected, MissingInput) as exc:
        checks['ua0009_inspection_ok'] = False
        checks['ua0009_evidence'] = {'reason': 'refingerprint_failed: ' + str(exc)}
        return checks
    unchanged = (before_fp['sha256'] == after_fp['sha256'])
    checks['ua0009_db_fingerprint_unchanged'] = unchanged
    checks['ua0009_inspection_ok'] = bool(result.get('ok')) and unchanged
    checks['ua0009_evidence'] = {
        'quick_check': result.get('quick_check'),
        'match_count': len(result.get('matches', [])) if result.get('ok') else None,
        'reason': result.get('reason'),
    }
    return checks


def _check_ua0009_not_public():
    url = os.environ.get('CRM_SPEED_UA0009_URL')
    if not url:
        return {'status': 'SKIPPED_NO_URL_CONFIGURED'}
    import urllib.error
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        resp = opener.open(url, timeout=5)
        code = resp.getcode()
        resp.close()
        if code in (404, 410):
            return {'status': 'NOT_SERVED', 'http_code': code}
        return {'status': 'AMBIGUOUS', 'http_code': code}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return {'status': 'NOT_SERVED', 'http_code': exc.code}
        return {'status': 'AMBIGUOUS', 'http_code': exc.code}
    except Exception as exc:
        return {'status': 'AMBIGUOUS', 'error': str(exc)}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _render_markdown_report(receipt):
    lines = []
    lines.append('# CRM-SPEED-001 Gate A report')
    lines.append('')
    lines.append('- run_id: ' + str(receipt.get('run_id')))
    lines.append('- status: ' + str(receipt.get('status')))
    lines.append('- production_write: ' + str(receipt.get('production_write')))
    lines.append('- context_bundle_sha256: ' + str(receipt.get('context_bundle_sha256')))
    lines.append('- memory_version_read: ' + str(receipt.get('memory_version_read')))
    lines.append('')
    lines.append('## Blockers')
    blockers = receipt.get('blockers') or []
    if blockers:
        for b in blockers:
            lines.append('- ' + str(b))
    else:
        lines.append('- none')
    lines.append('')
    lines.append('## Checks')
    for key, value in (receipt.get('checks') or {}).items():
        lines.append('- ' + str(key) + ': ' + str(value))
    lines.append('')
    lines.append('## Candidates')
    for rel, entry in (receipt.get('candidates') or {}).items():
        lines.append('- ' + str(rel) + ': ' + str(entry.get('status')))
    lines.append('')
    lines.append('## Next safe action')
    lines.append(str(receipt.get('next_safe_action')))
    return '\n'.join(lines) + '\n'


def _finalize(receipt, writer):
    receipt['finished_at_utc'] = _now_iso()
    receipt['production_write'] = 'NO'
    if receipt['status'] == 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL':
        receipt['next_safe_action'] = 'Awaiting independent ChatGPT review and explicit owner approval before any Gate B production install.'
    else:
        receipt['next_safe_action'] = 'Resolve listed blockers. No production or CRM changes were made.'
    payload = json.dumps(receipt, indent=2, sort_keys=True, default=str)
    writer.write_text('receipt.json', payload)
    writer.write_text('REPORT.md', _render_markdown_report(receipt))
    return receipt


def _finalize_without_writer(receipt):
    receipt['finished_at_utc'] = _now_iso()
    receipt['production_write'] = 'NO'
    receipt['next_safe_action'] = 'Resolve blockers. QA directory could not be created or locked. No production or CRM changes were made.'
    return receipt


def _run_gate_a_locked(source_base, qa_base, run_id, receipt):
    run_dir = os.path.join(qa_base, run_id)
    writer = SafeWriter(run_dir)

    inputs_ok, input_info, input_blockers = resolve_required_inputs(source_base)
    backup_ok, backup_sha, backup_blocker = verify_backup_archive(source_base)
    receipt['progress_percent'] = 20
    receipt['required_inputs'] = input_info
    receipt['checks'] = {
        'inputs_resolved_ok': inputs_ok,
        'backup_verified_ok': backup_ok,
    }
    blockers = list(input_blockers)
    if backup_blocker:
        blockers.append(backup_blocker)
    if not inputs_ok or not backup_ok:
        receipt['status'] = 'BLOCKED'
        receipt['blockers'] = blockers
        return _finalize(receipt, writer)

    receipt['progress_percent'] = 40
    candidates_meta, candidate_sources, orig_sources, core_ok, compile_ok_all = _process_candidates(source_base, writer, input_info)
    receipt['candidates'] = candidates_meta
    receipt['checks']['all_core_candidates_ok'] = core_ok

    receipt['progress_percent'] = 60
    receipt['checks']['all_candidates_compile_ok'] = compile_ok_all

    receipt['progress_percent'] = 80
    behavior_checks = _run_behavior_validations(candidate_sources, orig_sources)
    receipt['checks'].update(behavior_checks)

    receipt['progress_percent'] = 100
    ua_checks = _run_ua0009_stage(source_base, input_info)
    receipt['checks'].update(ua_checks)
    receipt['ua0009_publication_check'] = _check_ua0009_not_public()

    reinputs_ok, reinput_info, _reinput_blockers = resolve_required_inputs(source_base)
    unchanged_all = reinputs_ok and all(
        input_info.get(k, {}).get('sha256') == reinput_info.get(k, {}).get('sha256') for k in input_info
    )
    receipt['checks']['protected_inputs_unchanged'] = unchanged_all
    if not unchanged_all:
        blockers.append('unexpected_protected_change_detected')

    checks = receipt['checks']
    all_checks_ok = (
        core_ok and compile_ok_all and unchanged_all
        and bool(checks.get('cars_ui_text_only_ok'))
        and bool(checks.get('avtoperedacha_no_subprocess_ok'))
        and bool(checks.get('singleton_guard_ok'))
        and bool(checks.get('deterministic_repeat_ok'))
        and bool(checks.get('ua0009_inspection_ok'))
        and bool(checks.get('synthetic_latency_ok'))
    )

    if all_checks_ok and not blockers:
        receipt['status'] = 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL'
    else:
        receipt['status'] = 'BLOCKED'
    receipt['blockers'] = blockers
    return _finalize(receipt, writer)


def run_gate_a(source_base=None, qa_base=None):
    source_base = source_base or os.environ.get('CRM_SPEED_SOURCE_BASE', DEFAULT_SOURCE_BASE)
    qa_base = qa_base or os.environ.get('CRM_SPEED_QA_BASE', os.path.join(source_base, 'qa', 'crm_speed_task020'))
    run_id = 'run_' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '_' + uuid.uuid4().hex[:8]
    receipt = {
        'task': 'CRM-SPEED-001',
        'run_id': run_id,
        'started_at_utc': _now_iso(),
        'source_base': source_base,
        'qa_base': qa_base,
        'status': 'IN_PROGRESS',
        'progress_percent': 0,
        'blockers': [],
        'candidates': {},
        'context_bundle_sha256': CONTEXT_BUNDLE_SHA256,
        'memory_version_read': MEMORY_VERSION_READ,
        'production_write': 'NO',
    }

    try:
        os.makedirs(qa_base, exist_ok=True)
    except OSError as exc:
        receipt['status'] = 'BLOCKED'
        receipt['blockers'].append('cannot_create_qa_base: ' + str(exc))
        return _finalize_without_writer(receipt)

    lock_path = os.path.join(qa_base, 'gate_a.lock')
    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, (str(os.getpid()) + ' ' + _now_iso()).encode('utf-8'))
    except FileExistsError:
        stale = False
        try:
            age = time.time() - os.path.getmtime(lock_path)
            if age > LOCK_STALE_SECONDS:
                os.remove(lock_path)
                stale = True
        except OSError:
            pass
        if stale:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, (str(os.getpid()) + ' ' + _now_iso()).encode('utf-8'))
            except OSError as exc:
                receipt['status'] = 'BLOCKED'
                receipt['blockers'].append('lock_unavailable_after_stale_check: ' + str(exc))
                return _finalize_without_writer(receipt)
        else:
            receipt['status'] = 'BLOCKED'
            receipt['blockers'].append('gate_a_lock_held_by_another_run')
            return _finalize_without_writer(receipt)

    try:
        return _run_gate_a_locked(source_base, qa_base, run_id, receipt)
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                os.remove(lock_path)
            except OSError:
                pass


def main():
    receipt = run_gate_a()
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0 if receipt.get('status') == 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL' else 1


if __name__ == '__main__':
    sys.exit(main())
