"""CRM-SPEED-001 Gate A core module — round 2 (task_025 corrective iteration).

Every predicate required for the final PASS decision is derived from a
measured Evidence object stored in the receipt. No predicate is ever
assigned True as a placeholder. Any missing/ambiguous measurement makes
the corresponding predicate BLOCKED, which forces the overall run to
BLOCKED.

This module performs NO production writes. All writes go through
SafeWriter and are constrained beneath the resolved per-run QA directory.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO (this file only defines the machinery; execution is a
separate controller-run act, never performed by Claude/Cloud).
"""

from __future__ import annotations

import ast
import atexit
import errno
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

# --------------------------------------------------------------------------
# Constants / bounded configuration
# --------------------------------------------------------------------------

SITE_ROOTS = [
    "/home/Carix/site",
    "/home/Carix/video",
    "/home/Carix/public_html",
]

_UA_NUMBERS = [f"{i:04d}" for i in range(1, 10)]
ALLOWED_SITE_NAMES = frozenset(
    ["index.html", "katalog.html"]
    + [f"UA-{n}.html" for n in _UA_NUMBERS]
    + [f"UA-{n}-diag.html" for n in _UA_NUMBERS]
    + [f"UA-{n}-track.html" for n in _UA_NUMBERS]
)

MAX_FILES_PER_ROOT = 32

UA0009_CANONICAL_URL = os.environ.get("UA0009_CANONICAL_URL", "").strip()

BACKUP_ARCHIVE_PATH = "/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz"
BACKUP_ARCHIVE_SHA256 = (
    "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913"
)

REQUIRED_INPUTS = [
    "/home/Carix/.local/lib/python3.10/site-packages/usercustomize.py",
    "/home/Carix/.local/lib/python3.13/site-packages/usercustomize.py",
    "/home/Carix/start_safe.py",
    "/home/Carix/run_all.py",
    "/home/Carix/cars_ui.py",
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/samokontrol.py",
    "/home/Carix/db.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/stranica.py",
    "/home/Carix/crm.db",
]

SLOW_CALL_KEYWORDS = (
    "sleep", "requests.", "urlopen", "send_message", "send_photo",
    "send_video", "bot.", "telegram", "generate", "stranica", "write(",
    "open(",
)

MEDIA_SEND_NAMES = frozenset(
    [
        "reply_photo", "reply_video", "send_photo", "send_video",
        "send_media_group", "reply_media_group", "send_animation",
        "reply_animation", "send_document", "reply_document",
    ]
)


# --------------------------------------------------------------------------
# Evidence framework — no field may become True without measurement
# --------------------------------------------------------------------------

class Evidence:
    def __init__(self, name: str):
        self.name = name
        self.measurements: dict = {}
        self.reasons: list = []
        self.passed = None

    def record(self, key, value):
        self.measurements[key] = value

    def fail(self, reason: str):
        self.reasons.append(reason)
        self.passed = False

    def finalize(self, condition: bool) -> bool:
        if self.passed is False:
            return False
        self.passed = bool(condition)
        if not self.passed and not self.reasons:
            self.reasons.append("condition_false_no_explicit_reason")
        return self.passed

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "measurements": self.measurements,
            "reasons": self.reasons,
        }


# --------------------------------------------------------------------------
# Hashing utilities
# --------------------------------------------------------------------------

def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Cross-process lock — PID + process-start-time + ownership token evidence
# --------------------------------------------------------------------------

class CrossProcessLock:
    """Atomic, non-blocking-capable cross-process lock.

    * acquire() uses O_CREAT|O_EXCL for the initial fast path.
    * Stale-owner takeover is serialized through a second O_CREAT|O_EXCL
      guard file so that only one contending process can win a takeover
      race, even when many processes observe the same stale lock at the
      same instant.
    * release() and the atexit handler are exception-safe and idempotent;
      they never recreate a deleted directory and never raise.
    """

    def __init__(self, path: str):
        self.path = path
        self._token = None
        self._acquired = False
        self._atexit_registered = False

    # -- process identity -------------------------------------------------
    @staticmethod
    def _proc_start_time_ns(pid: int):
        try:
            with open(f"/proc/{pid}/stat", "r") as f:
                data = f.read()
        except OSError:
            return None
        idx = data.rfind(")")
        if idx == -1:
            return None
        rest = data[idx + 2:].split()
        try:
            starttime_ticks = int(rest[19])  # field 22, 0-indexed after field3
        except (IndexError, ValueError):
            return None
        return starttime_ticks

    def _is_owner_alive(self, data) -> bool:
        if not data:
            return False
        pid = data.get("pid")
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        recorded_start = data.get("start_time_ns")
        current_start = self._proc_start_time_ns(pid)
        if recorded_start is not None and current_start is not None:
            return recorded_start == current_start
        # Ambiguous evidence (no /proc): fail closed toward "alive" so we
        # never double-acquire on ambiguity.
        return True

    def _read(self):
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    # -- acquire ------------------------------------------------------------
    def acquire(self, timeout: float = 0.0) -> bool:
        deadline = time.monotonic() + timeout
        token = uuid.uuid4().hex
        pid = os.getpid()
        start = self._proc_start_time_ns(pid)
        payload = {
            "pid": pid,
            "start_time_ns": start,
            "token": token,
            "acquired_at": time.time(),
        }
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(payload, f)
                    f.flush()
                    os.fsync(f.fileno())
                self._token = token
                self._acquired = True
                self._register_atexit()
                return True
            except FileExistsError:
                observed = self._read()
                if not self._is_owner_alive(observed):
                    if self._attempt_stale_takeover(observed, payload):
                        self._token = token
                        self._acquired = True
                        self._register_atexit()
                        return True
                if timeout <= 0 or time.monotonic() >= deadline:
                    return False
                time.sleep(0.005)
            except OSError:
                if timeout <= 0 or time.monotonic() >= deadline:
                    return False
                time.sleep(0.005)

    def _attempt_stale_takeover(self, observed, payload) -> bool:
        guard = self.path + ".guard"
        try:
            gfd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(gfd)
        except FileExistsError:
            return False
        except OSError:
            return False
        try:
            current = self._read()
            if current != observed and self._is_owner_alive(current):
                return False
            tmp = f"{self.path}.tmp.{payload['token']}"
            try:
                fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(payload, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
                return True
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                return False
        finally:
            try:
                os.unlink(guard)
            except OSError:
                pass

    # -- release --------------------------------------------------------------
    def release(self):
        if not self._acquired:
            self._unregister_atexit()
            return
        try:
            data = self._read()
            if data and data.get("token") == self._token:
                try:
                    os.unlink(self.path)
                except OSError:
                    pass
        except Exception:
            pass
        finally:
            self._acquired = False
            self._unregister_atexit()

    def _register_atexit(self):
        if not self._atexit_registered:
            atexit.register(self._atexit_release)
            self._atexit_registered = True

    def _unregister_atexit(self):
        if self._atexit_registered:
            try:
                atexit.unregister(self._atexit_release)
            except Exception:
                pass
            self._atexit_registered = False

    def _atexit_release(self):
        # Must never raise, must never recreate a deleted directory, must
        # silently return when the run/test directory is already gone.
        try:
            self.release()
        except Exception:
            pass

    def __enter__(self):
        self.acquire(timeout=0)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


class SingletonGuard:
    """Fail-fast singleton wrapper used by start_safe.py / run_all.py candidates."""

    def __init__(self, lock_path: str):
        self._lock = CrossProcessLock(lock_path)

    def run(self, main_callable, exit_code_on_duplicate: int = 3):
        if not self._lock.acquire(timeout=0):
            sys.stderr.write("SINGLETON_ALREADY_RUNNING\n")
            return exit_code_on_duplicate
        try:
            return main_callable()
        finally:
            self._lock.release()


# --------------------------------------------------------------------------
# RebuildQueue — cross-process safe, coalescing, non-blocking enqueue
# --------------------------------------------------------------------------

class RebuildQueue:
    def __init__(self, lock_path: str, pending_path: str, callback, logger=None):
        self.lock_path = lock_path
        self.pending_path = pending_path
        self.callback = callback
        self.logger = logger
        self._worker_guard = threading.Lock()
        self._worker_thread = None

    def enqueue(self) -> bool:
        self._touch_pending()
        with self._worker_guard:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(
                    target=self._worker_loop, daemon=True
                )
                self._worker_thread.start()
        return True

    def _touch_pending(self):
        try:
            fd = os.open(self.pending_path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError:
            pass

    def _consume_pending(self) -> bool:
        try:
            os.unlink(self.pending_path)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def _worker_loop(self):
        lock = CrossProcessLock(self.lock_path)
        if not lock.acquire(timeout=0):
            return
        try:
            while self._consume_pending():
                try:
                    self.callback()
                except Exception as exc:  # bounded, never spins forever
                    if self.logger:
                        try:
                            self.logger("rebuild_failed", exc.__class__.__name__)
                        except Exception:
                            pass
        finally:
            lock.release()


# --------------------------------------------------------------------------
# SafeWriter — hardened, run-directory-confined writer
# --------------------------------------------------------------------------

class SafeWriteError(Exception):
    pass


class SafeWriter:
    def __init__(self, run_dir: str, min_free_bytes: int = 10 * 1024 * 1024):
        self.run_dir = os.path.realpath(run_dir)
        self.min_free_bytes = min_free_bytes
        self.written_paths: list = []

    def _resolve_and_check(self, rel_or_abs: str) -> str:
        candidate = os.path.join(self.run_dir, rel_or_abs) if not os.path.isabs(
            rel_or_abs
        ) else rel_or_abs
        norm = os.path.normpath(candidate)
        if not (norm == self.run_dir or norm.startswith(self.run_dir + os.sep)):
            raise SafeWriteError(f"path_escape:{rel_or_abs}")
        parent = os.path.dirname(norm)
        os.makedirs(parent, exist_ok=True)
        cur = self.run_dir
        for part in os.path.relpath(parent, self.run_dir).split(os.sep):
            if part in ("", "."):
                continue
            cur = os.path.join(cur, part)
            if os.path.islink(cur):
                raise SafeWriteError(f"symlink_parent:{cur}")
        if os.path.exists(norm):
            st = os.lstat(norm)
            if stat.S_ISLNK(st.st_mode):
                raise SafeWriteError(f"symlink_target:{norm}")
            if not stat.S_ISREG(st.st_mode):
                raise SafeWriteError(f"non_regular_target:{norm}")
            if st.st_nlink != 1:
                raise SafeWriteError(f"hardlink_target:{norm}")
        return norm

    def write_text(self, rel_or_abs: str, content: str, mode: int = 0o600) -> str:
        target = self._resolve_and_check(rel_or_abs)
        usage = shutil.disk_usage(self.run_dir)
        if usage.free < self.min_free_bytes:
            raise SafeWriteError("insufficient_free_space")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".sw_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            dir_fd = os.open(os.path.dirname(target), os.O_RDONLY)
            try:
                os.replace(tmp, target)
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.written_paths.append(target)
        return target

    def read_source_no_follow(self, path: str) -> bytes:
        if os.path.islink(path):
            raise SafeWriteError(f"symlink_source:{path}")
        st_before = os.lstat(path)
        if not stat.S_ISREG(st_before.st_mode):
            raise SafeWriteError(f"non_regular_source:{path}")
        if st_before.st_nlink != 1:
            raise SafeWriteError(f"hardlink_source:{path}")
        with open(path, "rb") as f:
            data = f.read()
        st_after = os.fstat(f.fileno()) if False else os.lstat(path)
        if (st_before.st_ino, st_before.st_dev) != (st_after.st_ino, st_after.st_dev):
            raise SafeWriteError(f"identity_changed_during_read:{path}")
        return data

    def audit_all_under_run_dir(self) -> bool:
        return all(
            os.path.normpath(p) == self.run_dir
            or os.path.normpath(p).startswith(self.run_dir + os.sep)
            for p in self.written_paths
        )


# --------------------------------------------------------------------------
# Bounded site/public inventory
# --------------------------------------------------------------------------

def scan_bounded_inventory(roots=None):
    roots = roots or SITE_ROOTS
    inventory = {}
    blocked = []
    for root in roots:
        if not os.path.isdir(root):
            blocked.append(f"missing_root:{root}")
            continue
        try:
            with os.scandir(root) as it:
                entries = list(it)
        except OSError as exc:
            blocked.append(f"scan_error:{root}:{exc}")
            continue
        matched = [e for e in entries if e.name in ALLOWED_SITE_NAMES]
        if len(matched) > MAX_FILES_PER_ROOT:
            blocked.append(f"overflow:{root}:{len(matched)}")
            continue
        for entry in matched:
            path = os.path.join(root, entry.name)
            try:
                st = os.lstat(path)
            except OSError as exc:
                blocked.append(f"lstat_error:{path}:{exc}")
                continue
            if stat.S_ISLNK(st.st_mode):
                blocked.append(f"symlink:{path}")
                continue
            if not stat.S_ISREG(st.st_mode):
                blocked.append(f"not_regular:{path}")
                continue
            if st.st_nlink != 1:
                blocked.append(f"hardlink:{path}:{st.st_nlink}")
                continue
            canonical = os.path.realpath(path)
            try:
                sha = sha256_file(path)
            except OSError as exc:
                blocked.append(f"read_error:{path}:{exc}")
                continue
            inventory[canonical] = {
                "mode": st.st_mode,
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "sha256": sha,
            }
    return inventory, blocked


def inventories_equal(before: dict, after: dict) -> bool:
    return sorted(before.items()) == sorted(after.items())


# --------------------------------------------------------------------------
# Protected input fingerprinting
# --------------------------------------------------------------------------

def fingerprint_path(path: str):
    if not os.path.exists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return {"symlink": True}
    return {
        "mode": st.st_mode,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": sha256_file(path) if stat.S_ISREG(st.st_mode) else None,
    }


def fingerprint_all(paths):
    return {p: fingerprint_path(p) for p in paths}


# --------------------------------------------------------------------------
# Publication probe — fail closed on any ambiguity
# --------------------------------------------------------------------------

def probe_ua0009_not_public(url: str) -> Evidence:
    ev = Evidence("ua0009_not_public")
    ev.record("url", url)
    if not url:
        ev.fail("missing_url")
        return ev if ev.finalize(False) is not None else ev
    if not url.startswith("https://"):
        ev.fail("non_https_url")
        ev.finalize(False)
        return ev

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")
    try:
        resp = opener.open(req, timeout=5)
        status = resp.getcode()
        ev.record("status", status)
        ev.fail(f"unexpected_status_{status}")
        ev.finalize(False)
        return ev
    except urllib.error.HTTPError as exc:
        ev.record("status", exc.code)
        if exc.code in (404, 410):
            ev.finalize(True)
            return ev
        ev.fail(f"http_error_{exc.code}")
        ev.finalize(False)
        return ev
    except urllib.error.URLError as exc:
        ev.fail(f"url_error:{exc.reason}")
        ev.finalize(False)
        return ev
    except socket.timeout:
        ev.fail("timeout")
        ev.finalize(False)
        return ev
    except ValueError as exc:
        ev.fail(f"malformed_url:{exc}")
        ev.finalize(False)
        return ev
    except Exception as exc:
        ev.fail(f"unexpected_exception:{exc.__class__.__name__}")
        ev.finalize(False)
        return ev


# --------------------------------------------------------------------------
# SQLite quick_check (read-only, fail closed)
# --------------------------------------------------------------------------

def sqlite_quick_check(db_path: str) -> Evidence:
    ev = Evidence("sqlite_quick_check")
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON")
            cur = conn.execute("PRAGMA quick_check")
            row = cur.fetchone()
            result = row[0] if row else None
            ev.record("result", result)
            cur.close()
            return ev if ev.finalize(result == "ok") is not None else ev
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        ev.fail(f"operational_error:{exc}")
        ev.finalize(False)
        return ev
    except Exception as exc:
        ev.fail(f"unexpected_exception:{exc.__class__.__name__}")
        ev.finalize(False)
        return ev


# --------------------------------------------------------------------------
# AST-based structural transforms (real, generic — operate on real bytes
# at Gate A execution time; conservative and BLOCK on any ambiguity).
# --------------------------------------------------------------------------

SAFE_TOPLEVEL_IMPORT_MODULES = frozenset(
    ["sys", "os", "warnings", "locale", "encodings", "site", "logging"]
)

FORBIDDEN_TOPLEVEL_MODULES = frozenset(
    [
        "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
        "threading", "multiprocessing", "subprocess", "socket", "requests",
    ]
)


def transform_usercustomize(source: str):
    """Produce an inert usercustomize.py candidate.

    Returns (candidate_source_or_None, blocked_reasons_list).
    """
    reasons = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, [f"syntax_error:{exc}"]

    new_body = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
            if any(n in FORBIDDEN_TOPLEVEL_MODULES for n in names):
                continue  # dropped
            if all(n in SAFE_TOPLEVEL_IMPORT_MODULES for n in names):
                new_body.append(node)
                continue
            reasons.append(f"unclassified_import:{names}")
            continue
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_TOPLEVEL_MODULES:
                continue
            if mod in SAFE_TOPLEVEL_IMPORT_MODULES:
                new_body.append(node)
                continue
            reasons.append(f"unclassified_import_from:{mod}")
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            new_body.append(node)
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            new_body.append(node)  # docstrings / literal no-ops
            continue
        if isinstance(node, ast.Assign):
            if _is_pure_constant_expr(node.value):
                new_body.append(node)
                continue
            reasons.append("unclassified_toplevel_assign_with_call")
            continue
        if isinstance(node, ast.If):
            reasons.append("unclassified_toplevel_if_guard")
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            reasons.append("unclassified_toplevel_call")
            continue
        reasons.append(f"unclassified_node:{type(node).__name__}")

    if reasons:
        return None, reasons
    candidate = ast.unparse(ast.fix_missing_locations(ast.Module(body=new_body, type_ignores=[])))
    return candidate, []


def _is_pure_constant_expr(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure_constant_expr(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_pure_constant_expr(k) for k in node.keys if k is not None) and all(
            _is_pure_constant_expr(v) for v in node.values
        )
    return False


def transform_singleton_wrap(source: str, lock_path_literal: str):
    """Inject SingletonGuard around the exact `if __name__ == "__main__": <call>()`
    anchor. BLOCK if the anchor is missing or ambiguous (not exactly one
    single Expr(Call) statement in the guarded body).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, [f"syntax_error:{exc}"]

    anchors = []
    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            anchors.append(node)
    if len(anchors) != 1:
        return None, [f"main_guard_count:{len(anchors)}"]
    guard = anchors[0]
    if len(guard.body) != 1 or not (
        isinstance(guard.body[0], ast.Expr) and isinstance(guard.body[0].value, ast.Call)
    ):
        return None, ["ambiguous_main_guard_body"]

    call_node = guard.body[0].value
    import_singleton = ast.ImportFrom(
        module="crm_speed_gate_a", names=[ast.alias(name="SingletonGuard", asname=None)], level=0
    )
    new_stmt = ast.parse(
        f"__gate_a_singleton = SingletonGuard({lock_path_literal!r})\n"
        f"__gate_a_singleton.run(lambda: __gate_a_main_call())\n"
    ).body
    wrapper_func = ast.parse(
        "def __gate_a_main_call():\n    pass\n"
    ).body[0]
    wrapper_func.body = [ast.Expr(value=call_node)]
    guard.body = [wrapper_func] + new_stmt
    tree.body.insert(0, import_singleton)
    candidate = ast.unparse(ast.fix_missing_locations(tree))
    return candidate, []


def _is_main_guard(test_node) -> bool:
    if not isinstance(test_node, ast.Compare):
        return False
    left = test_node.left
    if not (isinstance(left, ast.Name) and left.id == "__name__"):
        return False
    if len(test_node.ops) != 1 or not isinstance(test_node.ops[0], ast.Eq):
        return False
    comparators = test_node.comparators
    if len(comparators) != 1:
        return False
    comp = comparators[0]
    return isinstance(comp, ast.Constant) and comp.value == "__main__"


def transform_avtoperedacha_rebuild(source: str):
    """Replace the single subprocess/os.system/multiprocessing rebuild call
    site with an in-process RebuildQueue.enqueue() call. BLOCK if zero or
    more than one such call site exists, or if any remain reachable after
    transform."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, [f"syntax_error:{exc}"]

    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_process_spawn_call(node):
            targets.append(node)
    if len(targets) != 1:
        return None, [f"process_spawn_call_count:{len(targets)}"]

    class _Replacer(ast.NodeTransformer):
        def visit_Call(self, node):
            if node is targets[0]:
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="REBUILD_QUEUE", ctx=ast.Load()),
                        attr="enqueue",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[],
                )
            self.generic_visit(node)
            return node

    new_tree = _Replacer().visit(tree)
    ast.fix_missing_locations(new_tree)
    candidate = ast.unparse(new_tree)

    try:
        verify_tree = ast.parse(candidate)
    except SyntaxError as exc:
        return None, [f"post_transform_syntax_error:{exc}"]
    remaining = [n for n in ast.walk(verify_tree) if isinstance(n, ast.Call) and _is_process_spawn_call(n)]
    if remaining:
        return None, ["process_spawn_call_remains_after_transform"]
    return candidate, []


def _is_process_spawn_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        chain = _attr_chain(func)
        joined = ".".join(chain)
        return joined.startswith("subprocess.") or joined.startswith(
            "multiprocessing."
        ) or joined == "os.system"
    return False


def _attr_chain(node) -> list:
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return list(reversed(parts))


def transform_cars_ui_admin_routes(source: str, route_names):
    """Replace reachable media-send call sites inside the given admin route
    functions with text-only replies. BLOCK per-route on ambiguity or
    unresolved dynamic dispatch; the whole candidate is rejected if any
    targeted route cannot be proven clean after transform."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, [f"syntax_error:{exc}"]

    functions_by_name = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    reasons = []
    for route in route_names:
        fn = functions_by_name.get(route)
        if fn is None:
            reasons.append(f"missing_route:{route}")
            continue
        if not _rewrite_media_calls_in_function(fn):
            reasons.append(f"ambiguous_media_call_site:{route}")

    if reasons:
        return None, reasons

    candidate = ast.unparse(ast.fix_missing_locations(tree))
    try:
        verify_tree = ast.parse(candidate)
    except SyntaxError as exc:
        return None, [f"post_transform_syntax_error:{exc}"]
    verify_functions = {
        n.name: n
        for n in ast.walk(verify_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for route in route_names:
        fn = verify_functions.get(route)
        if fn is None:
            return None, [f"missing_route_after_transform:{route}"]
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and n.attr in MEDIA_SEND_NAMES:
                return None, [f"media_call_remains:{route}:{n.attr}"]
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in MEDIA_SEND_NAMES:
                return None, [f"media_call_remains:{route}:{n.func.id}"]
    return candidate, []


def _rewrite_media_calls_in_function(fn) -> bool:
    """Return False (ambiguous / cannot safely rewrite) if any dynamic
    dispatch is detected; otherwise rewrites top-level Expr/Await statement
    call sites in-place and returns True."""
    ok = True

    def is_media_call(node):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in MEDIA_SEND_NAMES:
                return True
            if isinstance(f, ast.Name) and f.id in MEDIA_SEND_NAMES:
                return True
        return False

    def contains_dynamic_dispatch(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr":
                return True
        return False

    new_body = []
    for stmt in fn.body:
        target_call = None
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            target_call = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await) and isinstance(
            stmt.value.value, ast.Call
        ):
            target_call = stmt.value.value

        if target_call is not None and is_media_call(target_call):
            if contains_dynamic_dispatch(target_call):
                ok = False
                new_body.append(stmt)
                continue
            text_call = ast.parse(
                "reply_text('media: text-only summary (Gate A candidate)')"
            ).body[0]
            new_body.append(text_call)
            continue

        if any(is_media_call(n) for n in ast.walk(stmt)):
            # media call buried inside a non-trivial expression/branch we
            # do not attempt to rewrite structurally -> ambiguous.
            ok = False
        new_body.append(stmt)

    if ok:
        fn.body = new_body
    return ok


def transform_db_short_ownership(source: str, function_names):
    """Ensure DB cursor/connection objects in the named functions are closed
    before any slow-call statement. Conservative: only rewrites simple,
    straight-line functions; BLOCKs otherwise."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, [f"syntax_error:{exc}"]

    functions_by_name = {
        n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
    reasons = []
    for name in function_names:
        fn = functions_by_name.get(name)
        if fn is None:
            reasons.append(f"missing_function:{name}")
            continue
        if any(isinstance(s, (ast.For, ast.While, ast.Try)) for s in ast.walk(fn)):
            reasons.append(f"non_straightline_control_flow:{name}")
            continue
        db_var = None
        db_stmt_idx = None
        for idx, stmt in enumerate(fn.body):
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                chain = ".".join(_attr_chain(stmt.value.func)) if isinstance(
                    stmt.value.func, ast.Attribute
                ) else ""
                if "connect" in chain and len(stmt.targets) == 1 and isinstance(
                    stmt.targets[0], ast.Name
                ):
                    db_var = stmt.targets[0].id
                    db_stmt_idx = idx
                    break
        if db_var is None:
            reasons.append(f"no_db_connect_anchor:{name}")
            continue
        slow_idx = None
        for idx in range(db_stmt_idx + 1, len(fn.body)):
            stmt_src = ast.unparse(fn.body[idx])
            if any(k in stmt_src for k in SLOW_CALL_KEYWORDS):
                slow_idx = idx
                break
        if slow_idx is None:
            # nothing slow after DB open: acceptable as-is, no change needed
            continue
        already_closed = any(
            db_var in ast.unparse(fn.body[i]) and "close" in ast.unparse(fn.body[i])
            for i in range(db_stmt_idx + 1, slow_idx)
        )
        used_after_slow = any(
            db_var in ast.unparse(fn.body[i]) for i in range(slow_idx, len(fn.body))
        )
        if used_after_slow:
            reasons.append(f"db_var_used_after_slow_call:{name}")
            continue
        if already_closed:
            continue
        close_stmt = ast.parse(f"{db_var}.close()").body[0]
        fn.body.insert(slow_idx, close_stmt)

    if reasons:
        return None, reasons
    candidate = ast.unparse(ast.fix_missing_locations(tree))
    return candidate, []


# --------------------------------------------------------------------------
# Deterministic repeat measurement
# --------------------------------------------------------------------------

def measure_deterministic_repeat(transform_fn, source: str, args=(), repeats: int = 10):
    ev = Evidence("repeat_runs_byte_identical")
    hashes = []
    for _ in range(repeats):
        result = transform_fn(source, *args)
        candidate, reasons = result
        if candidate is None:
            hashes.append(("BLOCKED", tuple(reasons)))
        else:
            hashes.append(("OK", sha256_bytes(candidate.encode("utf-8"))))
    ev.record("hashes", [list(h) for h in hashes])
    all_identical = len(set(hashes)) == 1
    ev.finalize(all_identical)
    if not all_identical:
        ev.fail("nondeterministic_transform_output")
    return ev


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def build_receipt(run_dir: str, config: dict) -> dict:
    """Compute the full evidence-derived receipt. Never assigns a required
    boolean True without a stored Evidence measurement."""
    evidences = {}

    # -- required inputs
    ev_inputs = Evidence("required_inputs_present")
    missing = []
    for p in REQUIRED_INPUTS:
        if not os.path.exists(p):
            missing.append(p)
        elif os.path.islink(p):
            missing.append(f"symlink:{p}")
    ev_inputs.record("missing_or_symlink", missing)
    ev_inputs.finalize(len(missing) == 0)
    evidences["required_inputs_present"] = ev_inputs

    # -- backup archive
    ev_backup = Evidence("backup_archive_verified")
    if os.path.exists(BACKUP_ARCHIVE_PATH):
        actual = sha256_file(BACKUP_ARCHIVE_PATH)
        ev_backup.record("actual_sha256", actual)
        ev_backup.finalize(actual == BACKUP_ARCHIVE_SHA256)
        if actual != BACKUP_ARCHIVE_SHA256:
            ev_backup.fail("sha_mismatch")
    else:
        ev_backup.fail("missing_backup_archive")
        ev_backup.finalize(False)
    evidences["backup_archive_verified"] = ev_backup

    # -- protected fingerprints before
    protected_before = fingerprint_all(REQUIRED_INPUTS)

    # -- site inventory before
    inv_before, inv_before_blocked = scan_bounded_inventory()
    ev_inv = Evidence("site_inventory_unchanged")
    ev_inv.record("before_blocked", inv_before_blocked)

    # -- publication probe
    ev_pub = probe_ua0009_not_public(UA0009_CANONICAL_URL)
    evidences["ua0009_not_public"] = ev_pub

    # -- sqlite quick_check
    ev_sql = sqlite_quick_check(config.get("db_path", "/home/Carix/crm.db"))
    evidences["sqlite_quick_check"] = ev_sql

    # (Candidate transform + repeat + write-audit evidence is produced by
    #  the caller (RUN_GATE_A_CRM_SPEED.py) which has the actual run
    #  directory and SafeWriter instance; this function focuses on the
    #  input-side and environment-side evidence that does not require
    #  writing anything.)

    inv_after, inv_after_blocked = scan_bounded_inventory()
    ev_inv.record("after_blocked", inv_after_blocked)
    inv_ok = (
        not inv_before_blocked
        and not inv_after_blocked
        and inventories_equal(inv_before, inv_after)
    )
    ev_inv.finalize(inv_ok)
    if not inv_ok:
        ev_inv.fail("inventory_blocked_or_changed")
    evidences["site_inventory_unchanged"] = ev_inv

    protected_after = fingerprint_all(REQUIRED_INPUTS)
    ev_protected = Evidence("protected_inputs_unchanged")
    diff_keys = [
        k for k in protected_before if protected_before[k] != protected_after.get(k)
    ]
    ev_protected.record("diff_keys", diff_keys)
    ev_protected.finalize(len(diff_keys) == 0)
    evidences["protected_inputs_unchanged"] = ev_protected

    all_pass = all(e.passed is True for e in evidences.values())
    status = (
        "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL" if all_pass else "BLOCKED"
    )
    receipt = {
        "status": status,
        "generated_at": time.time(),
        "evidence": {k: v.to_dict() for k, v in evidences.items()},
        "PRODUCTION_WRITE": "NO",
    }
    return receipt


def main():
    run_dir = tempfile.mkdtemp(prefix="crm_speed_gate_a_offline_")
    config = {"db_path": "/home/Carix/crm.db"}
    receipt = build_receipt(run_dir, config)
    print(json.dumps(receipt, indent=2, default=str))
    return 0 if receipt["status"] != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
