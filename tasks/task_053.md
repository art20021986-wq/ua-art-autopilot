# TASK 053 — CRM-SPEED-001 launcher class-body closure and test-contract repair

## Scope

Continue from exact controller snapshot 6466b4c3601c45ba922a28e2897e44072d48b01d. TASK 048 restored candidate_transforms.py and passed 42/42 correct legacy/focused checks, but a manual probe found one real launcher fail-open:
- class body expression value = appmod.VALUE -> incorrectly OK;
- method annotation x: appmod.Type inside that class -> incorrectly OK.

Also correct two false assertions in test_task_048_candidate_restore.py and migrate test_task_046_ast_sqlite.py away from the incompatible clean-room APIs introduced by rejected TASK 046. Complete current contents of all three files are embedded below.

Embedded SHA-256:
580c6aed909067632a410480d67f00cd4f0d7f17cbc6fefa667acd63a93bb870  candidate_transforms.py
90eb37b87ddbd473a0a44b2b819a810bd5570da343f6977326ce8a29533f5d92  test_task_046_ast_sqlite.py
f153404acdfbe65ac7f69b36df44003871015e70b366dc7a86794973ecdfc488  test_task_048_candidate_restore.py

## Safety

Work only under cloud/crm_speed_optimization/ plus cloud/latest_status.md and cloud/owner_reply.md. Claude authors all code/test changes.

Never execute Gate A, use network/PythonAnywhere, install candidates, or modify Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, UA-0009, or tasks/.

Markers:
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Return complete files only. Do not return or change sqlite_ownership.py, crm_speed_gate_a.py, or unrelated tests.

## 1. Class definition-time import safety

Preserve the entire embedded candidate_transforms.py and all accepted TASK 048 behavior. Make a minimal fail-closed extension to transform_launcher_singleton.

For every moved application/local/third-party import alias, detect references in every expression that executes before the main guard:
- top-level function/async-function decorators, positional/keyword defaults, argument annotations and return annotations;
- class decorators, bases and keywords;
- class-body assignments, annotated assignments, expressions, conditions, comprehensions and other executed statements;
- decorators/defaults/annotations of methods defined in a class;
- nested class definition-time surfaces and executed class bodies.

Do not descend into ordinary function/method bodies because those run later and resolve global imports after the main guard. A helper may implement a definition-time AST visitor that explicitly stops at function bodies while inspecting their definition-time surface.

Any moved-alias reference in a definition-time expression must return BLOCKED with candidate=None. Preserve future-import compilation, application-import relocation order, duplicate exit 78 before import, and generated signal-handler restoration.

Add strong tests for class assignment, method annotation/default/decorator and nested class surface -> BLOCKED; ordinary method-body appmod reference -> OK and application import remains after guard acquisition.

## 2. Correct rejected TASK 046 tests to the canonical contract

Update test_task_046_ast_sqlite.py without weakening behavioral coverage:

Candidate transforms:
- use result["candidate"], result["reasons"], stable status/candidate/reasons/metadata schema; never expect result["code"];
- positive alias test means an alias-resolved subprocess callable such as import subprocess as sp plus a literal "stranica.py" command;
- verify no surviving generator ast.Call outside the generator definition by parsing AST, not brittle text splitting/substrings;
- retain Expr and Return positives and every unsupported-context/spawn negative.

SQLite:
- use sqlite_ownership.transform_short_ownership(source, {"fetch_rows"}), which returns complete source or raises AnchorNotFoundError;
- positive tests compile/execute that returned source;
- negative cursor-return/escape uses assertRaises(AnchorNotFoundError);
- public API assertions require the accepted names AnchorNotFoundError, transform_short_ownership, OwnershipEvidence, collect_ua0009_ownership_evidence and compare_ownership_evidence;
- do not require rejected clean-room names transform_sqlite_ownership or OwnershipBlocked;
- preserve runtime success/connect-failure/execute-failure/fetch-failure, close order, timeout and immutable-row strength.

## 3. Correct TASK 048 false assertions

Update test_task_048_candidate_restore.py:

- module-level compatibility list must contain only actual embedded baseline module APIs: _ok, _blocked, generate_runtime_support_source, transform_usercustomize, transform_launcher_singleton, transform_avtoperedacha_rebuild, transform_sqlite_short_ownership, check_db_closed_before_slow_work_candidate;
- separately execute/inspect generate_runtime_support_source() and prove generated runtime defines CrossProcessLock, SingletonGuard and RebuildQueue;
- replace the substring assertion that mistakes def gen() for a call with an AST walk proving no direct gen ast.Call outside the generator definition;
- keep all other tests and add the class definition-time cases from section 1.

## Acceptance

Run:
- Python compile for every package .py;
- complete corrected test_task_046_ast_sqlite and test_task_048_candidate_restore;
- legacy candidate-related TASK 038/041 classes;
- manual class-body and method-annotation probes.

No skip/expected failure. Do not claim whole-package green: a small SQLite literal-compatibility edit and orchestrator closure remain separate.

## Deliverables — exactly six files

1. cloud/crm_speed_optimization/candidate_transforms.py
2. cloud/crm_speed_optimization/test_task_046_ast_sqlite.py
3. cloud/crm_speed_optimization/test_task_048_candidate_restore.py
4. cloud/crm_speed_optimization/TASK_053_REPORT.md
5. cloud/latest_status.md
6. cloud/owner_reply.md

Status: PARTIAL_TASK_053_LAUNCHER_TEST_CONTRACT_READY_FOR_CONTROLLER_AUDIT
Never claim READY_FOR_GATE_A.

## Exact input files

<BEGIN_CANDIDATE_TRANSFORMS_PY>
"""candidate_transforms.py (TASK 041 baseline, restored and repaired under TASK 048)

One canonical, fail-closed, standard-library-only, AST/token-aware
candidate-transform module for CRM-SPEED-001. Never imports or executes
an input application source. Regex is never used for broad rewriting;
only AST-anchored, exact structural rewrites are performed.

Every transform function returns the stable contract:

    {
        "status": "OK" | "BLOCKED",
        "candidate": str | None,
        "reasons": [bounded deterministic strings],
        "metadata": {bounded deterministic structural evidence},
    }

On missing/ambiguous/unsupported anchors, BLOCKED is returned with
candidate=None -- an unsafe original is never silently passed through as
an accepted candidate. Reasons/metadata never contain source bodies,
secrets, PII, or absolute production paths (only bounded structural
names, counts and line numbers).

cars_ui.py transforms remain the sole responsibility of
cars_ui_transform.transform_cars_ui; this module never duplicates that
logic.

TASK 041 corrections over TASK 038:

- transform_usercustomize now uses a POSITIVE harmless-import allowlist
  (ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS) in addition to the existing
  forbidden-import removal set. Any import that is neither explicitly
  forbidden (removed) nor explicitly allowed (kept) BLOCKS the whole
  transform instead of silently passing through.
- transform_launcher_singleton preserves the module docstring and every
  leading `from __future__` import before injecting the runtime import,
  and a duplicate start now writes one bounded diagnostic to stderr and
  exits with the stable code 78 instead of 3.
- transform_avtoperedacha_rebuild now requires structural call-graph
  proof (a zero-argument in-module generator with at least one proven
  in-process call site AND at least one proven, alias-resolved,
  literal-matched process-spawn site for that same generator) instead of
  function-name hints and a global spawn replacement.

TASK 048 corrections over TASK 041 (this file is a repair, not a
rewrite -- TASK 046's clean-room 12 KB replacement was rejected and is
not used as a baseline anywhere in this file):

- transform_avtoperedacha_rebuild's rewrite pass now also supports the
  exact `Return(Call)` trigger context (previously only `Expr(Call)` was
  rewritten; a Return-context trigger silently survived the rewrite and
  was then correctly, but for the wrong reason, rejected by the
  post-transform proof). A post-transform check now also explicitly
  rejects any surviving *module-level* `_queue.enqueue()` statement so a
  bare, unconditional module-level trigger can never execute the queue
  at import time.
- transform_launcher_singleton now actually relocates statically
  resolvable application/local/third-party import and from-import nodes
  into the single module-level `if __name__ == "__main__":` guard, after
  guard.install() succeeds and before the original main actions, instead
  of leaving all imports untouched at module scope. Relative imports,
  star imports and relocation ambiguity BLOCK. Any decorator, class
  base/keyword, function/class default, or definition-time-evaluated
  annotation that references a moved alias BLOCKS (NameError-at-import
  prevention); ordinary function-body references remain permitted.
- The generated RUNTIME_SUPPORT_SOURCE's SingletonGuard now records the
  previous SIGINT/SIGTERM handlers at successful install time and its
  cleanup() restores every handler it changed (in addition to releasing
  the lock), idempotently; repeated cleanup() calls never raise and never
  re-restore incorrectly. The generated per-signal wrapper now delegates
  through the guard's full cleanup() path before calling a callable
  previous handler.
"""
from __future__ import annotations

import ast
import copy

import sqlite_ownership

RUNTIME_MODULE_NAME = "crm_speed_runtime"

CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES = {
    "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
    "threading", "multiprocessing", "subprocess",
}

# Positive allowlist: standard-library imports explicitly known to be
# inert for usercustomize.py purposes. Anything not in this set and not
# in the forbidden-removal set above BLOCKS the transform.
ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS = frozenset({"sys"})

# Positive allowlist: standard-library imports explicitly known to be
# inert to keep above the launcher's main guard. Everything else that is
# statically resolvable (application/local/third-party, and any stdlib
# module not in this bounded list) is relocated inside the guard.
ALLOWED_PRE_GUARD_STDLIB_IMPORTS = frozenset({
    "sys", "os", "signal", "atexit", "time", "typing", "dataclasses",
    "enum", "json", "re", "math", "itertools", "functools", "collections",
    "copy", "io", "logging", "pathlib",
})

SPAWN_MODULE_CANDIDATES = {"subprocess", "os", "multiprocessing"}
SPAWN_ATTR_NAMES = {
    "Popen", "system", "call", "run", "check_call", "check_output",
    "spawnl", "spawnv", "posix_spawn",
}
SPAWN_DIRECT_IMPORT_NAMES = {"Popen", "system", "call", "run", "check_call", "check_output"}


def _ok(candidate, reasons=None, metadata=None):
    return {
        "status": "OK",
        "candidate": candidate,
        "reasons": list(reasons or []),
        "metadata": dict(metadata or {}),
    }


def _blocked(reasons, metadata=None):
    return {
        "status": "BLOCKED",
        "candidate": None,
        "reasons": list(reasons or []),
        "metadata": dict(metadata or {}),
    }


def _call_qualname(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = func.value.id + "."
        return base + func.attr
    return ""


def _is_pure_literal(node):
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) \
            and isinstance(node.operand, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all((k is None or _is_pure_literal(k)) for k in node.keys) and \
            all(_is_pure_literal(v) for v in node.values)
    return False


def _is_main_guard(test):
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
        left = test.left
        right = test.comparators[0]

        def _is_name_dunder(n):
            return isinstance(n, ast.Name) and n.id == "__name__"

        def _is_main_const(n):
            return isinstance(n, ast.Constant) and n.value == "__main__"

        if (_is_name_dunder(left) and _is_main_const(right)) or \
                (_is_main_const(left) and _is_name_dunder(right)):
            return True
    return False


# ---------------------------------------------------------------------------
# 2.3: deterministic generated runtime support candidate
# ---------------------------------------------------------------------------

RUNTIME_SUPPORT_SOURCE = r'''"""crm_speed_runtime.py (generated candidate support module).

Minimal canonical CrossProcessLock, SingletonGuard, and RebuildQueue
runtime shared by generated launcher and rebuild candidates. Standard
library only. Does not acquire any lock, start any thread, or perform
any I/O at import time. Callback failures record only a bounded
sanitized category ("CallbackError:<ExceptionClass>"), never str(exc).
"""
from __future__ import annotations

import atexit
import fcntl
import os
import secrets
import signal
import stat
import tempfile
import threading
import time


def _process_start_time(pid):
    try:
        with open("/proc/%s/stat" % pid, "r") as fh:
            data = fh.read()
        end = data.rfind(")")
        if end == -1:
            return None
        rest = data[end + 2:].split()
        if len(rest) <= 19:
            return None
        return rest[19]
    except Exception:
        return None


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return None
    return True


class LockEvidence:
    __slots__ = ("pid", "start_time", "token", "acquired_at")

    def __init__(self, pid, start_time, token, acquired_at):
        self.pid = pid
        self.start_time = start_time
        self.token = token
        self.acquired_at = acquired_at

    def to_line(self):
        return "%s|%s|%s|%s\n" % (self.pid, self.start_time, self.token, self.acquired_at)

    @staticmethod
    def parse(line):
        if not line:
            return None
        parts = line.strip().split("|")
        if len(parts) != 4:
            return None
        try:
            return LockEvidence(int(parts[0]), parts[1], parts[2], float(parts[3]))
        except ValueError:
            return None


def _owner_status(evidence):
    if evidence is None:
        return "absent"
    alive = _pid_alive(evidence.pid)
    if alive is None:
        return "unknown"
    if not alive:
        return "dead"
    current = _process_start_time(evidence.pid)
    if current is None or not evidence.start_time:
        return "unknown"
    if current != evidence.start_time:
        return "dead"
    return "live"


def _validate_parent(path):
    parent = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(parent):
        raise ValueError("parent directory does not exist: %s" % parent)
    if os.path.islink(parent):
        raise ValueError("parent directory must not be a symlink")
    return os.path.realpath(parent)


class CrossProcessLock:
    def __init__(self, path, stale_after_seconds=300, label=None):
        self.path = os.path.abspath(path)
        self._validated_parent = _validate_parent(self.path)
        self.guard_path = self.path + ".guard"
        self.stale_after_seconds = stale_after_seconds
        self.label = label
        self.token = secrets.token_hex(16)
        self._owned = False
        self._owned_lock = threading.Lock()
        self._atexit_registered = False

    def _open_guard(self):
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.guard_path, os.O_CREAT | os.O_RDWR | nofollow, 0o600)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            raise ValueError("guard path is not a regular file")
        return fd

    @staticmethod
    def _try_flock(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _read_evidence(self):
        try:
            with open(self.path, "r") as fh:
                return LockEvidence.parse(fh.readline())
        except Exception:
            return None

    def acquire(self):
        current_parent = os.path.dirname(self.path)
        if not os.path.isdir(current_parent):
            return False
        if os.path.realpath(current_parent) != self._validated_parent:
            return False
        try:
            guard_fd = self._open_guard()
        except Exception:
            return False
        try:
            if not self._try_flock(guard_fd):
                return False
            existing = self._read_evidence()
            status = _owner_status(existing)
            if status in ("live", "unknown"):
                return False
            evidence = LockEvidence(os.getpid(), _process_start_time(os.getpid()) or "", self.token, time.time())
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(dir=self._validated_parent, prefix=".lock_tmp_")
            except Exception:
                return False
            try:
                with os.fdopen(tmp_fd, "w") as fh:
                    fh.write(evidence.to_line())
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                try:
                    if os.path.lexists(tmp_path):
                        os.unlink(tmp_path)
                except Exception:
                    pass
                return False
            recheck = self._read_evidence()
            if recheck is None or recheck.token != self.token:
                return False
            self._owned = True
            with self._owned_lock:
                if not self._atexit_registered:
                    atexit.register(self.release)
                    self._atexit_registered = True
            return True
        finally:
            try:
                fcntl.flock(guard_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(guard_fd)
            except Exception:
                pass

    def release(self):
        with self._owned_lock:
            if not self._owned:
                return
            self._owned = False
        try:
            parent = os.path.dirname(self.path)
            if not os.path.isdir(parent):
                return
            try:
                guard_fd = self._open_guard()
            except Exception:
                return
            try:
                if not self._try_flock(guard_fd):
                    return
                current = self._read_evidence()
                if current is not None and current.token == self.token:
                    try:
                        os.unlink(self.path)
                    except Exception:
                        pass
            finally:
                try:
                    fcntl.flock(guard_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    os.close(guard_fd)
                except Exception:
                    pass
        except Exception:
            pass


class SingletonGuard(CrossProcessLock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._installed_handlers = {}
        self._handlers_lock = threading.Lock()

    def install(self):
        if not self.acquire():
            return False
        for name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                previous = signal.getsignal(sig)

                def _handler(signum, frame, _previous=previous, _self=self):
                    _self.cleanup()
                    if callable(_previous):
                        _previous(signum, frame)

                signal.signal(sig, _handler)
                with self._handlers_lock:
                    self._installed_handlers[sig] = previous
            except Exception:
                pass
        return True

    def cleanup(self):
        with self._handlers_lock:
            handlers = list(self._installed_handlers.items())
            self._installed_handlers = {}
        for sig, previous in handlers:
            try:
                signal.signal(sig, previous)
            except Exception:
                pass
        self.release()


class RebuildQueue:
    _ACK_TIMEOUT_SECONDS = 0.5

    def __init__(self, callback, lock_path, error_handler=None):
        if callback is None or not callable(callback):
            raise ValueError("RebuildQueue requires an explicit bound callable callback")
        self._callback = callback
        self._lock_path = lock_path
        self._error_handler = error_handler
        self._cv = threading.Condition()
        self._pending = False
        self._running = False
        self._stopped = False
        self._worker = None
        self._pending_ack_event = None
        self.runs = 0
        self.coalesced = 0
        self.errors = []

    def enqueue(self):
        with self._cv:
            if self._stopped:
                return "stopped"
            if self._running:
                self._pending = True
                self.coalesced += 1
                self._cv.notify_all()
                return "coalesced"
            self._pending = True
            ack_event = threading.Event()
            self._pending_ack_event = ack_event
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True)
                self._worker.start()
            self._cv.notify_all()
        ack_event.wait(timeout=self._ACK_TIMEOUT_SECONDS)
        return "accepted"

    def _loop(self):
        while True:
            with self._cv:
                while not self._pending and not self._stopped:
                    self._cv.wait(timeout=1)
                if self._stopped and not self._pending:
                    return
                self._pending = False
                self._running = True
                ack_event = self._pending_ack_event
                self._pending_ack_event = None
            acquired = False
            lock = None
            try:
                try:
                    lock = CrossProcessLock(self._lock_path)
                    acquired = lock.acquire()
                except Exception as exc:
                    with self._cv:
                        self.errors.append(type(exc).__name__)
                    acquired = False
                finally:
                    if ack_event is not None:
                        ack_event.set()
                if acquired:
                    try:
                        self._callback()
                        with self._cv:
                            self.runs += 1
                    except Exception as exc:
                        with self._cv:
                            self.errors.append("CallbackError:" + type(exc).__name__)
                        if self._error_handler is not None:
                            try:
                                self._error_handler(exc)
                            except Exception:
                                pass
            except Exception as exc:
                with self._cv:
                    self.errors.append(type(exc).__name__)
            finally:
                if acquired and lock is not None:
                    try:
                        lock.release()
                    except Exception:
                        pass
                with self._cv:
                    self._running = False
                    self._cv.notify_all()

    def shutdown(self, timeout=5):
        with self._cv:
            self._stopped = True
            self._cv.notify_all()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)

    def is_idle(self):
        with self._cv:
            return not self._running and not self._pending
'''


def generate_runtime_support_source():
    """Return the deterministic crm_speed_runtime.py candidate source.
    Does not acquire a lock, start a thread, or perform I/O."""
    return RUNTIME_SUPPORT_SOURCE


# ---------------------------------------------------------------------------
# 2.1: usercustomize candidates (both Python versions share this logic)
# ---------------------------------------------------------------------------

def transform_usercustomize(source, version):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    new_body = []
    reasons = []
    for idx, node in enumerate(tree.body):
        if idx == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            new_body.append(node)
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            new_body.append(node)
            continue
        if isinstance(node, ast.Import):
            kept = []
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES:
                    reasons.append(f"removed_forbidden_import:{alias.name}")
                    continue
                if top in ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS:
                    kept.append(alias)
                    continue
                return _blocked(reasons + [f"unknown_import_blocked:{alias.name}"])
            if kept:
                new_node = ast.Import(names=kept)
                ast.copy_location(new_node, node)
                new_body.append(new_node)
            continue
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES:
                reasons.append(f"removed_forbidden_import_from:{node.module}")
                continue
            if top in ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS:
                new_body.append(node)
                continue
            return _blocked(reasons + [f"unknown_import_from_blocked:{node.module}"])
        if isinstance(node, ast.Assign):
            if _is_pure_literal(node.value):
                new_body.append(node)
                continue
            return _blocked(reasons + [f"unsupported_top_level_assign:line{getattr(node,'lineno','?')}"])
        if isinstance(node, ast.AnnAssign):
            if node.value is None or _is_pure_literal(node.value):
                new_body.append(node)
                continue
            return _blocked(reasons + [f"unsupported_top_level_annassign:line{getattr(node,'lineno','?')}"])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.decorator_list:
                return _blocked(reasons + [f"decorated_definition_blocked:line{getattr(node,'lineno','?')}"])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
                for d in defaults:
                    if not _is_pure_literal(d):
                        return _blocked(reasons + [f"unsafe_default_expr:line{getattr(node,'lineno','?')}"])
                for arg in list(node.args.args) + list(node.args.kwonlyargs) + \
                        ([node.args.vararg] if node.args.vararg else []) + \
                        ([node.args.kwarg] if node.args.kwarg else []):
                    if arg is not None and arg.annotation is not None and not _is_pure_literal(arg.annotation) \
                            and not isinstance(arg.annotation, ast.Name):
                        return _blocked(reasons + [f"unsafe_annotation_expr:line{getattr(node,'lineno','?')}"])
            new_body.append(node)
            continue
        return _blocked(
            reasons + [f"unsupported_top_level_statement:{type(node).__name__}:line{getattr(node,'lineno','?')}"]
        )

    tree.body = new_body
    ast.fix_missing_locations(tree)
    try:
        candidate = ast.unparse(tree)
    except Exception as exc:
        return _blocked(reasons + [f"unparse_failed:{type(exc).__name__}"])
    try:
        compile(candidate, f"<usercustomize_{version}>", "exec")
    except SyntaxError as exc:
        return _blocked(reasons + [f"candidate_compile_failed:{type(exc).__name__}"])

    # Final static verification: nothing outside the positive allowlist
    # (plus __future__) may survive.
    post_tree = ast.parse(candidate)
    for node in ast.walk(post_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS:
                    return _blocked(reasons + ["post_transform_unexpected_import_survived"])
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top != "__future__" and top not in ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS:
                return _blocked(reasons + ["post_transform_unexpected_import_from_survived"])

    return _ok(candidate, reasons, {"version": version, "kept_statement_count": len(new_body)})


# ---------------------------------------------------------------------------
# 2.2: start_safe.py / run_all.py singleton candidates
# ---------------------------------------------------------------------------

def _leading_docstring_and_future_offset(body):
    offset = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        offset = 1
    while offset < len(body) and isinstance(body[offset], ast.ImportFrom) and body[offset].module == "__future__":
        offset += 1
    return offset


def _expr_references_any_name(expr, names):
    if expr is None:
        return False
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id in names:
            return True
    return False


def transform_launcher_singleton(source, lock_path):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    body = list(tree.body)
    offset = _leading_docstring_and_future_offset(body)
    prefix = body[:offset]
    rest = body[offset:]

    main_indices = [i for i, n in enumerate(rest) if isinstance(n, ast.If) and _is_main_guard(n.test)]
    if len(main_indices) != 1:
        return _blocked([f"main_anchor_count:{len(main_indices)}"])
    main_rel_idx = main_indices[0]

    pre_main = rest[:main_rel_idx]
    main_node = rest[main_rel_idx]
    post_main = rest[main_rel_idx + 1:]
    if post_main:
        return _blocked(["statements_after_main_guard_unsupported"])

    # Reject dynamic import calls anywhere in the module up front.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            qual = _call_qualname(node)
            if qual in ("__import__", "importlib.import_module", "import_module"):
                return _blocked(["dynamic_import_blocked"])

    kept_pre = []
    moved_imports = []
    moved_aliases = set()

    for node in pre_main:
        if isinstance(node, ast.Import):
            names_ok = all(a.name.split(".")[0] in ALLOWED_PRE_GUARD_STDLIB_IMPORTS for a in node.names)
            if names_ok:
                kept_pre.append(node)
            else:
                for a in node.names:
                    moved_aliases.add(a.asname or a.name.split(".")[0])
                moved_imports.append(node)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                return _blocked([f"relative_import_blocked:line{getattr(node,'lineno','?')}"])
            if any(a.name == "*" for a in node.names):
                return _blocked([f"star_import_blocked:line{getattr(node,'lineno','?')}"])
            top = (node.module or "").split(".")[0]
            if top in ALLOWED_PRE_GUARD_STDLIB_IMPORTS:
                kept_pre.append(node)
            else:
                for a in node.names:
                    moved_aliases.add(a.asname or a.name)
                moved_imports.append(node)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kept_pre.append(node)
            continue
        if isinstance(node, ast.Assign) and _is_pure_literal(node.value):
            kept_pre.append(node)
            continue
        return _blocked([f"import_time_side_effect:{type(node).__name__}:line{getattr(node,'lineno','?')}"])

    # Definition-time moved-alias reference check on everything kept above
    # the guard (decorators/bases/keywords/defaults/annotations execute at
    # module-definition time, before the moved imports run).
    for node in kept_pre:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _expr_references_any_name(dec, moved_aliases):
                    return _blocked(["definition_time_moved_alias_reference_blocked"])
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if _expr_references_any_name(base, moved_aliases):
                        return _blocked(["definition_time_moved_alias_reference_blocked"])
                for kw in node.keywords:
                    if _expr_references_any_name(kw.value, moved_aliases):
                        return _blocked(["definition_time_moved_alias_reference_blocked"])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                defaults = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
                for d in defaults:
                    if _expr_references_any_name(d, moved_aliases):
                        return _blocked(["definition_time_moved_alias_reference_blocked"])
                all_args = list(args.args) + list(args.kwonlyargs) + \
                    ([args.vararg] if args.vararg else []) + ([args.kwarg] if args.kwarg else [])
                for a in all_args:
                    if a is not None and a.annotation is not None and \
                            _expr_references_any_name(a.annotation, moved_aliases):
                        return _blocked(["definition_time_moved_alias_reference_blocked"])
                if node.returns is not None and _expr_references_any_name(node.returns, moved_aliases):
                    return _blocked(["definition_time_moved_alias_reference_blocked"])

    original_main_body = main_node.body

    guard_name = "_singleton_guard"
    setup = ast.parse(
        f"{guard_name} = SingletonGuard({lock_path!r})\n"
        f"if not {guard_name}.install():\n"
        "    import sys as _crm_speed_diag_sys\n"
        "    _crm_speed_diag_sys.stderr.write("
        "'CRM-SPEED-001: duplicate launcher start blocked by singleton guard\\n')\n"
        "    raise SystemExit(78)\n"
        "try:\n"
        "    pass\n"
        "finally:\n"
        f"    {guard_name}.cleanup()\n"
    ).body
    try_node = setup[-1]
    inner_body = moved_imports + list(original_main_body)
    if not inner_body:
        inner_body = [ast.parse("pass").body[0]]
    try_node.body = inner_body
    main_node.body = setup[:-1] + [try_node]

    import_node = ast.ImportFrom(module=RUNTIME_MODULE_NAME, names=[ast.alias(name="SingletonGuard", asname=None)], level=0)

    tree.body = prefix + [import_node] + kept_pre + [main_node]
    ast.fix_missing_locations(tree)

    try:
        candidate = ast.unparse(tree)
    except Exception as exc:
        return _blocked([f"unparse_failed:{type(exc).__name__}"])
    try:
        compile(candidate, "<launcher>", "exec")
    except SyntaxError as exc:
        return _blocked([f"candidate_compile_failed:{type(exc).__name__}"])

    return _ok(candidate, [], {
        "lock_path": lock_path,
        "duplicate_exit_code": 78,
        "moved_import_count": len(moved_imports),
    })


# ---------------------------------------------------------------------------
# 2.4: avtoperedacha.py rebuild-queue candidate (TASK 041 call-graph proof,
# TASK 048 Return-context + module-level-execution repair)
# ---------------------------------------------------------------------------

def _collect_spawn_aliases(tree):
    module_aliases = {}
    direct_names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in SPAWN_MODULE_CANDIDATES:
                    module_aliases[alias.asname or alias.name] = base
        elif isinstance(node, ast.ImportFrom):
            if node.module in SPAWN_MODULE_CANDIDATES:
                for alias in node.names:
                    if alias.name in SPAWN_DIRECT_IMPORT_NAMES:
                        direct_names.add(alias.asname or alias.name)
    return module_aliases, direct_names


def _is_spawn_call_resolved(node, module_aliases, direct_names):
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in direct_names
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id in module_aliases and func.attr in SPAWN_ATTR_NAMES
    return False


def _literal_strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for e in node.elts:
            out.extend(_literal_strings(e))
        return out
    return []


def _spawn_matches_generator(call_node, generator_name):
    strings = []
    for a in call_node.args:
        strings.extend(_literal_strings(a))
    for kw in call_node.keywords:
        strings.extend(_literal_strings(kw.value))
    if not strings:
        return False
    joined = " ".join(strings).lower()
    if "stranica.py" in joined:
        return True
    if generator_name.lower() in joined:
        return True
    return False


def _zero_arg_functions(tree):
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.decorator_list:
            args = node.args
            if not args.args and not args.vararg and not args.kwonlyargs and not args.kwarg \
                    and not getattr(args, "posonlyargs", []):
                names.append(node.name)
    return names


def _find_in_process_call_sites(tree, generator_name, generator_node):
    sites = []
    for node in tree.body:
        if node is generator_node:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == generator_name:
                sites.append(sub)
    return sites


def _module_level_call_to(tree, generator_name):
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == generator_name:
                return True
    return False


def _is_leading_docstring(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def transform_avtoperedacha_rebuild(source):
    lock_path = "/home/Carix/qa/crm_speed_task020/rebuild.lock"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    module_aliases, direct_names = _collect_spawn_aliases(tree)
    zero_arg = _zero_arg_functions(tree)
    if not zero_arg:
        return _blocked(["no_zero_argument_generator_candidate_found"])

    generator_nodes = {
        n.name: n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in zero_arg
    }

    all_spawn_calls = [n for n in ast.walk(tree) if _is_spawn_call_resolved(n, module_aliases, direct_names)]

    full_candidates = []
    for name in zero_arg:
        gnode = generator_nodes[name]
        in_process_sites = _find_in_process_call_sites(tree, name, gnode)
        if not in_process_sites:
            continue
        matched_spawns = [c for c in all_spawn_calls if _spawn_matches_generator(c, name)]
        if not matched_spawns:
            continue
        if _module_level_call_to(tree, name):
            continue
        full_candidates.append((name, in_process_sites, matched_spawns))

    if len(full_candidates) != 1:
        return _blocked([f"full_generator_candidate_count:{len(full_candidates)}"])

    generator_name, in_process_sites, matched_spawns = full_candidates[0]

    class _Replacer(ast.NodeTransformer):
        @staticmethod
        def _matches_trigger(value):
            if not isinstance(value, ast.Call):
                return False
            if isinstance(value.func, ast.Name) and value.func.id == generator_name:
                return True
            if _is_spawn_call_resolved(value, module_aliases, direct_names) and \
                    _spawn_matches_generator(value, generator_name):
                return True
            return False

        @staticmethod
        def _enqueue_call():
            return ast.Call(
                func=ast.Attribute(value=ast.Name(id="_queue", ctx=ast.Load()), attr="enqueue", ctx=ast.Load()),
                args=[], keywords=[],
            )

        def visit_Expr(self, node):
            if self._matches_trigger(node.value):
                new_expr = ast.Expr(value=self._enqueue_call())
                ast.copy_location(new_expr, node)
                ast.fix_missing_locations(new_expr)
                return new_expr
            return self.generic_visit(node)

        def visit_Return(self, node):
            if node.value is not None and self._matches_trigger(node.value):
                new_return = ast.Return(value=self._enqueue_call())
                ast.copy_location(new_return, node)
                ast.fix_missing_locations(new_return)
                return new_return
            return self.generic_visit(node)

    new_tree = copy.deepcopy(tree)
    new_body = [_Replacer().visit(n) for n in new_tree.body]
    new_tree.body = new_body

    remaining_spawn_use = any(
        _is_spawn_call_resolved(n, module_aliases, direct_names) for n in ast.walk(new_tree)
    )
    if not remaining_spawn_use:
        used_module_names = set(module_aliases.keys())
        remaining_module_name_refs = {
            n.id for n in ast.walk(new_tree) if isinstance(n, ast.Name) and n.id in used_module_names
        }
        new_tree.body = [
            n for n in new_tree.body
            if not (
                isinstance(n, ast.Import)
                and all((a.asname or a.name) in used_module_names for a in n.names)
                and not remaining_module_name_refs
            )
        ]

    insert_idx = None
    for i, n in enumerate(new_tree.body):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == generator_name:
            insert_idx = i + 1
            break
    if insert_idx is None:
        return _blocked(["generator_definition_lost_during_transform"])

    import_node = ast.ImportFrom(module=RUNTIME_MODULE_NAME, names=[ast.alias(name="RebuildQueue", asname=None)], level=0)
    queue_assign = ast.parse(f"_queue = RebuildQueue({generator_name}, {lock_path!r})\n").body[0]

    body = list(new_tree.body)
    doc_offset = 1 if body and _is_leading_docstring(body[0]) else 0
    final_body = body[:doc_offset] + [import_node] + body[doc_offset:insert_idx] + [queue_assign] + body[insert_idx:]
    new_tree.body = final_body
    ast.fix_missing_locations(new_tree)

    try:
        candidate = ast.unparse(new_tree)
    except Exception as exc:
        return _blocked([f"unparse_failed:{type(exc).__name__}"])
    try:
        compile(candidate, "<avtoperedacha>", "exec")
    except SyntaxError as exc:
        return _blocked([f"candidate_compile_failed:{type(exc).__name__}"])

    post_tree = ast.parse(candidate)
    post_module_aliases, post_direct_names = _collect_spawn_aliases(post_tree)
    remaining_spawn = any(
        _is_spawn_call_resolved(n, post_module_aliases, post_direct_names) for n in ast.walk(post_tree)
    )
    if remaining_spawn:
        return _blocked(["spawn_still_reachable_after_transform"])

    queue_line_found = False
    remaining_direct_calls = 0
    for n in ast.walk(post_tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and \
                isinstance(n.value.func, ast.Name) and n.value.func.id == "RebuildQueue":
            queue_line_found = True
            continue
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == generator_name:
            remaining_direct_calls += 1
    if not queue_line_found:
        return _blocked(["queue_binding_missing_after_transform"])
    if remaining_direct_calls != 0:
        return _blocked(["direct_generator_call_still_present_after_transform"])

    queue_assigns = [
        n for n in ast.walk(post_tree)
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "_queue"
    ]
    if len(queue_assigns) != 1:
        return _blocked(["queue_assignment_count_invalid"])

    # TASK 048: reject any surviving *module-level* enqueue execution --
    # the rewrite must never itself execute the queue at import time.
    for node in post_tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "enqueue" and \
                    isinstance(call.func.value, ast.Name) and call.func.value.id == "_queue":
                return _blocked(["module_level_enqueue_execution_blocked"])

    return _ok(candidate, [], {
        "generator": generator_name,
        "in_process_sites": len(in_process_sites),
        "spawn_sites": len(matched_spawns),
    })


# ---------------------------------------------------------------------------
# 2.5: short SQLite ownership candidate (avtoperedacha.py / samokontrol.py)
# ---------------------------------------------------------------------------

def transform_sqlite_short_ownership(source, function_names=None):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    if not function_names:
        discovered = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if sqlite_ownership.find_db_handle_names(node):
                    discovered.add(node.name)
        function_names = discovered

    if not function_names:
        return _blocked(["no_db_functions_found"])

    try:
        candidate = sqlite_ownership.transform_short_ownership(source, set(function_names))
    except sqlite_ownership.AnchorNotFoundError as exc:
        return _blocked([f"anchor_not_found:{exc}"])
    except Exception as exc:
        return _blocked([f"exception:{type(exc).__name__}"])

    try:
        compile(candidate, "<sqlite_ownership_candidate>", "exec")
    except SyntaxError as exc:
        return _blocked([f"candidate_compile_failed:{type(exc).__name__}"])

    return _ok(candidate, [], {"functions": sorted(function_names)})


def check_db_closed_before_slow_work_candidate(source):
    """Structural, path-conservative verification against a CANDIDATE
    source string (never the original) using the canonical
    sqlite_ownership handle-specific verifier."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{type(exc).__name__}"}
    found_any = False
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if sqlite_ownership.find_db_handle_names(node):
                found_any = True
                violations.extend(sqlite_ownership.verify_no_live_handle_across_slow_call(node))
    if not found_any:
        return {"status": "BLOCKED", "reason": "no_db_functions_found"}
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


<END_CANDIDATE_TRANSFORMS_PY>

<BEGIN_TEST_TASK_046_AST_SQLITE_PY>
"""
TASK 046 focused offline test suite for the rebuild AST transformer and the
SQLite ownership transform. Temporary-directory / in-memory only. No network,
no PythonAnywhere, no Production or CRM access.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""

import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import candidate_transforms as ct  # noqa: E402
import sqlite_ownership as so  # noqa: E402


class TestRebuildTransformPositive(unittest.TestCase):
    def test_expr_call_positive(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK")
        compile(result["code"], "<t>", "exec")
        self.assertIn("_queue = RebuildQueue(generate_stranica_page,", result["code"])
        tail = result["code"].split("def generate_stranica_page")[1].split("def trigger_one")[1]
        self.assertNotIn("generate_stranica_page()", tail)

    def test_return_call_positive(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                return generate_stranica_page()

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK")
        self.assertIn("return _queue.enqueue()", result["code"])

    def test_alias_spawn_positive(self):
        src = textwrap.dedent("""
            import subprocess

            SCRIPT = "stranica.py"

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                subprocess.run(["python3", SCRIPT])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK")
        self.assertIn("_queue.enqueue()", result["code"])


class TestRebuildTransformNegative(unittest.TestCase):
    def test_unsupported_assignment_context_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                x = generate_stranica_page()
                return x

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_unrelated_spawn_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                subprocess.run(["ffmpeg", "-i", "in.mp4", "out.mp4"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_dynamic_command_blocks(self):
        src = textwrap.dedent("""
            import subprocess
            import os

            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()

            def trigger_two(name):
                subprocess.run(["python3", os.path.join("scripts", name)])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_ambiguous_two_generator_targets_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def generate_other_page():
                return "ok2"

            def trigger_one():
                generate_stranica_page()

            def trigger_two():
                generate_other_page()

            def trigger_three():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_direct_call_blocks(self):
        src = textwrap.dedent("""
            import subprocess

            def generate_stranica_page():
                return "ok"

            def trigger_two():
                subprocess.run(["python3", "stranica.py"])
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_spawn_blocks(self):
        src = textwrap.dedent("""
            def generate_stranica_page():
                return "ok"

            def trigger_one():
                generate_stranica_page()
        """)
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")


class TestSqliteOwnershipStatic(unittest.TestCase):
    def test_cursor_via_execute_and_return_cur_blocks(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.execute("SELECT id FROM t")
                return cur
        """)
        result = so.transform_sqlite_ownership(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_conn_execute_cursor_discovery_positive(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        result = so.transform_sqlite_ownership(src)
        self.assertEqual(result["status"], "OK")
        self.assertIn("timeout=2", result["code"])
        self.assertIn("tuple(", result["code"])
        self.assertIn("finally", result["code"])

    def test_guarded_close_order_and_tuple_rows(self):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        result = so.transform_sqlite_ownership(src)
        self.assertEqual(result["status"], "OK")
        code = result["code"]
        cur_close_pos = code.index("cur.close()")
        conn_close_pos = code.index("conn.close()")
        self.assertLess(cur_close_pos, conn_close_pos)
        self.assertIn("is not None", code)


class TestSqliteOwnershipRuntime(unittest.TestCase):
    def _build_and_run(self, fake_connect):
        src = textwrap.dedent("""
            import sqlite3

            def fetch_rows(path):
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute("SELECT id FROM t")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
        """)
        result = so.transform_sqlite_ownership(src)
        self.assertEqual(result["status"], "OK")
        code_no_import = result["code"].replace("import sqlite3\n", "")
        namespace = {"sqlite3": type("FakeModule", (), {"connect": staticmethod(fake_connect)})}
        exec(compile(code_no_import, "<gen>", "exec"), namespace)
        return namespace["fetch_rows"]

    def test_success_path_closes_in_order_and_returns_tuple(self):
        events = []

        class FakeCursor:
            def execute(self, sql, *a):
                events.append("execute")
                return self

            def fetchall(self):
                events.append("fetchall")
                return [(1,), (2,)]

            def close(self):
                events.append("cur_close")

        class FakeConn:
            def cursor(self):
                events.append("cursor")
                return FakeCursor()

            def close(self):
                events.append("conn_close")

        def fake_connect(path, timeout=None):
            events.append(("connect", timeout))
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        rows = fn(":memory:")
        self.assertEqual(rows, ((1,), (2,)))
        self.assertIsInstance(rows, tuple)
        self.assertIsInstance(rows[0], tuple)
        self.assertEqual(events[-2:], ["cur_close", "conn_close"])
        self.assertEqual(events[0], ("connect", 2))

    def test_connect_failure_no_unbound_local_error(self):
        def fake_connect(path, timeout=None):
            raise RuntimeError("boom")

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(RuntimeError):
            fn(":memory:")

    def test_execute_failure_closes_conn_only(self):
        events = []

        class FakeCursor:
            def execute(self, sql, *a):
                raise RuntimeError("exec boom")

            def close(self):
                events.append("cur_close")

        class FakeConn:
            def cursor(self):
                events.append("cursor")
                return FakeCursor()

            def close(self):
                events.append("conn_close")

        def fake_connect(path, timeout=None):
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(RuntimeError):
            fn(":memory:")
        self.assertIn("cur_close", events)
        self.assertIn("conn_close", events)
        self.assertEqual(events.index("cur_close"), events.index("conn_close") - 1)

    def test_fetch_failure_closes_both_no_masking(self):
        class FakeCursor:
            def execute(self, sql, *a):
                return self

            def fetchall(self):
                raise ValueError("fetch boom")

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        def fake_connect(path, timeout=None):
            return FakeConn()

        fn = self._build_and_run(fake_connect)
        with self.assertRaises(ValueError):
            fn(":memory:")


class TestPublicApiPreserved(unittest.TestCase):
    def test_public_names_present(self):
        self.assertTrue(hasattr(ct, "transform_avtoperedacha_rebuild"))
        self.assertTrue(hasattr(so, "transform_sqlite_ownership"))
        self.assertTrue(hasattr(so, "OwnershipBlocked"))


if __name__ == "__main__":
    unittest.main()


<END_TEST_TASK_046_AST_SQLITE_PY>

<BEGIN_TEST_TASK_048_CANDIDATE_RESTORE_PY>
"""test_task_048_candidate_restore.py

Compact focused tests for the TASK 048 repair of candidate_transforms.py.
Does not duplicate the older TASK 031/038/041 suites. Assumes
sqlite_ownership.py already exists unchanged in this same package
directory (delivered by an earlier task); this file does not modify or
redeliver it.

No network, no PythonAnywhere, no Production/CRM access. All lock paths
used here are temporary directories created by the test itself.
"""
from __future__ import annotations

import os
import signal
import sys
import tempfile
import types
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import candidate_transforms as ct  # noqa: E402


class TestCompatibilityNames(unittest.TestCase):
    def test_required_names_exist(self):
        names = [
            "_ok", "_blocked", "CrossProcessLock", "SingletonGuard", "RebuildQueue",
            "generate_runtime_support_source", "transform_usercustomize",
            "transform_launcher_singleton", "transform_avtoperedacha_rebuild",
            "transform_sqlite_short_ownership", "check_db_closed_before_slow_work_candidate",
        ]
        for n in names:
            self.assertTrue(hasattr(ct, n), f"missing required name: {n}")

    def test_result_schema_compatible(self):
        ok = ct._ok("candidate-src", ["r1"], {"k": 1})
        for key in ("status", "candidate", "reasons", "metadata"):
            self.assertIn(key, ok)
        self.assertEqual(ok["status"], "OK")
        self.assertEqual(ok["candidate"], "candidate-src")

        blocked = ct._blocked(["why"], {"a": 1})
        for key in ("status", "candidate", "reasons", "metadata"):
            self.assertIn(key, blocked)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertIsNone(blocked["candidate"])


class TestRebuildTransformPositives(unittest.TestCase):
    def test_expr_trigger_positive(self):
        src = (
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "import subprocess\n\n"
            "def spawn_related():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<t>", "exec")
        self.assertIn("_queue = RebuildQueue(gen", result["candidate"])
        self.assertIn("_queue.enqueue()", result["candidate"])
        self.assertNotIn("gen()", result["candidate"].replace("_queue.enqueue()", ""))

    def test_return_trigger_positive(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def trigger():\n"
            "    return gen()\n\n"
            "def spawner():\n"
            "    return subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<t>", "exec")
        self.assertIn("return _queue.enqueue()", result["candidate"])

    def test_aliased_subprocess_positive(self):
        src = (
            "import subprocess as sp\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "def spawner():\n"
            "    sp.Popen(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])


class TestRebuildTransformNegatives(unittest.TestCase):
    def test_unrelated_spawn_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "def other():\n"
            "    subprocess.run(['ffmpeg', '-i', 'a.mp4'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_direct_call_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_nonzero_args_generator_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen(x):\n"
            "    return x\n\n"
            "def start():\n"
            "    gen(1)\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_module_level_direct_call_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "gen()\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_assignment_context_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    x = gen()\n"
            "    return x\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_ambiguous_two_full_candidates_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen_a():\n"
            "    return 1\n\n"
            "def gen_b():\n"
            "    return 2\n\n"
            "def start():\n"
            "    gen_a()\n"
            "    gen_b()\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py', 'gen_a'])\n"
            "    subprocess.run(['python3', 'stranica.py', 'gen_b'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")


class TestLauncherTransform(unittest.TestCase):
    LAUNCHER_SRC = (
        '"""Launcher module docstring."""\n'
        "from __future__ import annotations\n\n"
        "import fake_app_module\n\n\n"
        "def main():\n"
        "    fake_app_module.run()\n\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    def _build_fake_runtime_module(self, install_return, events):
        mod = types.ModuleType(ct.RUNTIME_MODULE_NAME)

        class FakeSingletonGuard:
            def __init__(self, path):
                self.path = path

            def install(self):
                events.append("install")
                return install_return

            def cleanup(self):
                events.append("cleanup")

        mod.SingletonGuard = FakeSingletonGuard
        return mod

    def test_future_import_preserved_and_compiles(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK", result["reasons"])
        self.assertIn("from __future__ import annotations", result["candidate"])
        compile(result["candidate"], "<launcher>", "exec")

    def test_import_as_module_no_lock_no_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(True, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.RAN = []
        fake_app.run = lambda: fake_app.RAN.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "not_main"}
            exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertEqual(events, [])
            self.assertEqual(fake_app.RAN, [])
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_main_path_acquires_guard_before_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(True, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.run = lambda: events.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "__main__"}
            exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertIn("install", events)
            self.assertIn("app_ran", events)
            self.assertLess(events.index("install"), events.index("app_ran"))
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_duplicate_start_exits_78_before_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(False, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.run = lambda: events.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "__main__"}
            with self.assertRaises(SystemExit) as cm:
                exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertEqual(cm.exception.code, 78)
            self.assertNotIn("app_ran", events)
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_definition_time_moved_alias_ambiguity_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "@fake_dep.register\n"
            "def helper():\n"
            "    pass\n\n\n"
            "if __name__ == '__main__':\n"
            "    helper()\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_relative_import_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "from . import sibling\n\n\n"
            "if __name__ == '__main__':\n"
            "    sibling.run()\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")


class TestRuntimeSignalCleanup(unittest.TestCase):
    def test_cleanup_restores_fake_handlers_idempotently(self):
        src = ct.generate_runtime_support_source()
        ns = {}
        exec(compile(src, "<runtime>", "exec"), ns)
        SingletonGuard = ns["SingletonGuard"]

        fake_prev_term = lambda signum, frame: None  # noqa: E731
        fake_prev_int = lambda signum, frame: None  # noqa: E731
        orig_getsignal = signal.getsignal
        orig_signal = signal.signal
        installed = {}

        def fake_getsignal(sig):
            if sig == signal.SIGTERM:
                return fake_prev_term
            if sig == signal.SIGINT:
                return fake_prev_int
            return orig_getsignal(sig)

        def fake_signal(sig, handler):
            installed[sig] = handler
            return None

        with tempfile.TemporaryDirectory() as d:
            lock_path = os.path.join(d, "test.lock")
            guard = SingletonGuard(lock_path)
            signal.getsignal = fake_getsignal
            signal.signal = fake_signal
            try:
                ok = guard.install()
                self.assertTrue(ok)
                self.assertIn(signal.SIGTERM, installed)
                self.assertIn(signal.SIGINT, installed)
                guard.cleanup()
                self.assertEqual(installed[signal.SIGTERM], fake_prev_term)
                self.assertEqual(installed[signal.SIGINT], fake_prev_int)
                # idempotent: second cleanup must not raise or re-restore
                guard.cleanup()
            finally:
                signal.getsignal = orig_getsignal
                signal.signal = orig_signal


if __name__ == "__main__":
    unittest.main()


<END_TEST_TASK_048_CANDIDATE_RESTORE_PY>
