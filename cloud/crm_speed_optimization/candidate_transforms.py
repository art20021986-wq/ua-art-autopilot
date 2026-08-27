"""candidate_transforms.py (TASK 038)

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

GENERATOR_NAME_HINTS = ("stranica", "generate_page", "render_page", "build_page")

SPAWN_QUALNAMES_SUFFIXES = ("Popen", "system", "check_call", "check_output")
SPAWN_QUALNAMES_EXACT = ("subprocess.call", "subprocess.run")


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
any I/O at import time.
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
                    _self.release()
                    if callable(_previous):
                        _previous(signum, frame)

                signal.signal(sig, _handler)
            except Exception:
                pass
        return True

    def cleanup(self):
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
                            self.errors.append(str(exc)[:500])
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
                kept.append(alias)
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
            new_body.append(node)
            continue
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

    # Final static verification: no forbidden import name may survive.
    post_tree = ast.parse(candidate)
    for node in ast.walk(post_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES:
                    return _blocked(reasons + ["post_transform_forbidden_import_survived"])
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES:
                return _blocked(reasons + ["post_transform_forbidden_import_from_survived"])

    return _ok(candidate, reasons, {"version": version, "kept_statement_count": len(new_body)})


# ---------------------------------------------------------------------------
# 2.2: start_safe.py / run_all.py singleton candidates
# ---------------------------------------------------------------------------

def transform_launcher_singleton(source, lock_path):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    main_indices = []
    for idx, node in enumerate(tree.body):
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            main_indices.append(idx)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assign) and _is_pure_literal(node.value):
            continue
        if idx == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue
        return _blocked([f"import_time_side_effect:{type(node).__name__}:line{getattr(node,'lineno','?')}"])

    if len(main_indices) != 1:
        return _blocked([f"main_anchor_count:{len(main_indices)}"])

    idx = main_indices[0]
    main_node = tree.body[idx]
    original_body = main_node.body

    guard_name = "_singleton_guard"
    setup = ast.parse(
        f"{guard_name} = SingletonGuard({lock_path!r})\n"
        f"if not {guard_name}.install():\n"
        "    raise SystemExit(3)\n"
        "try:\n"
        "    pass\n"
        "finally:\n"
        f"    {guard_name}.cleanup()\n"
    ).body
    try_node = setup[-1]
    try_node.body = original_body
    main_node.body = setup[:-1] + [try_node]

    import_node = ast.ImportFrom(module=RUNTIME_MODULE_NAME, names=[ast.alias(name="SingletonGuard", asname=None)], level=0)
    new_tree_body = [import_node] + tree.body
    tree.body = new_tree_body
    ast.fix_missing_locations(tree)

    try:
        candidate = ast.unparse(tree)
    except Exception as exc:
        return _blocked([f"unparse_failed:{type(exc).__name__}"])
    try:
        compile(candidate, "<launcher>", "exec")
    except SyntaxError as exc:
        return _blocked([f"candidate_compile_failed:{type(exc).__name__}"])

    return _ok(candidate, [], {"lock_path": lock_path})


# ---------------------------------------------------------------------------
# 2.4: avtoperedacha.py rebuild-queue candidate
# ---------------------------------------------------------------------------

def _is_spawn_call(node):
    if not isinstance(node, ast.Call):
        return False
    qual = _call_qualname(node)
    if any(qual.endswith(suf) for suf in SPAWN_QUALNAMES_SUFFIXES):
        return True
    if qual in SPAWN_QUALNAMES_EXACT:
        return True
    return False


def transform_avtoperedacha_rebuild(source):
    lock_path = "/home/Carix/qa/crm_speed_task020/rebuild.lock"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _blocked([f"syntax_error:{type(exc).__name__}"])

    func_names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    generator_candidates = [n for n in func_names if any(h in n.lower() for h in GENERATOR_NAME_HINTS)]
    if len(generator_candidates) != 1:
        return _blocked([f"generator_candidate_count:{len(generator_candidates)}"])
    generator_name = generator_candidates[0]

    spawn_sites = [n for n in ast.walk(tree) if _is_spawn_call(n)]
    if not spawn_sites:
        return _blocked(["no_reachable_process_spawn_found"])

    class _Replacer(ast.NodeTransformer):
        def visit_Expr(self, node):
            if _is_spawn_call(node.value):
                new_call = ast.Call(
                    func=ast.Attribute(value=ast.Name(id="_queue", ctx=ast.Load()), attr="enqueue", ctx=ast.Load()),
                    args=[], keywords=[],
                )
                new_expr = ast.Expr(value=new_call)
                ast.copy_location(new_expr, node)
                ast.fix_missing_locations(new_expr)
                return new_expr
            return self.generic_visit(node)

    new_tree = copy.deepcopy(tree)
    new_tree.body = [_Replacer().visit(n) for n in new_tree.body]

    remaining_subprocess_use = any(
        isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "subprocess"
        for node in ast.walk(new_tree)
    )
    if not remaining_subprocess_use:
        new_tree.body = [
            n for n in new_tree.body
            if not (isinstance(n, ast.Import) and any(a.name == "subprocess" for a in n.names))
        ]

    import_node = ast.ImportFrom(module=RUNTIME_MODULE_NAME, names=[ast.alias(name="RebuildQueue", asname=None)], level=0)
    queue_assign = ast.parse(f"_queue = RebuildQueue({generator_name}, {lock_path!r})\n").body[0]
    new_tree.body = [import_node] + new_tree.body + [queue_assign]
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
    remaining_spawn = any(_is_spawn_call(n) for n in ast.walk(post_tree))
    if remaining_spawn:
        return _blocked(["spawn_still_reachable_after_transform"])

    return _ok(candidate, [], {"generator": generator_name, "replaced_sites": len(spawn_sites)})


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
        return _blocked([f"anchor_not_found:{type(exc).__name__}"])
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
