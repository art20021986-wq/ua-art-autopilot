# TASK 044 — CRM-SPEED-001 final compatibility and structural closure

## Authority and immutable safety boundary

Continue the owner-approved CRM-SPEED-001 repair after independent controller execution of TASK 041. Work only under `cloud/crm_speed_optimization/` plus `cloud/latest_status.md` and `cloud/owner_reply.md`. Claude authors every implementation change.

Do not execute Gate A, access PythonAnywhere/network, install candidates, or modify Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Tests are offline and temporary-directory-only. Do not modify `tasks/`.

Required markers:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

Return complete files only.

## Independent controller result for commit 65e1b53e71492bebd3b7405a44d04af41e91847a

- compilation: PASS for all 23 Python files;
- full discovery: 243 tests;
- 230 PASS, 11 FAIL, 2 ERROR;
- no unhandled `Exception in thread`;
- safe-inbox sync: PASS, isolated to `/home/Carix/autopilot_inbox`;
- Production/CRM/Gate A/UA-0009 unchanged.

TASK 041 is not accepted. Its own report also discloses an unimplemented launcher-import relocation requirement, so no readiness claim is permitted.

### Root-cause evidence

1. The rebuild transformer replaces only `Expr(Call)`. Positive fixtures use `return generate_stranica_page()`, so that direct call survives and the transformer blocks itself with `direct_generator_call_still_present_after_transform`. This cascades into candidate/orchestration/manifest/publication failures.
2. `find_cursor_names` recognizes only `cur = conn.cursor()`, not the common SQLite shape `cur = conn.execute('SELECT ...')`. Therefore cursor escape is not blocked and no cursor close is generated.
3. When an extended transform blocks, the real orchestrator exits phase40 without a complete well-formed predicate set. Manifest verification then fails early on `missing_or_malformed_predicate:candidates_compile` rather than testing receipt/report tamper binding.
4. The canonical publication probe is skipped entirely after an early candidate block, breaking the canonical-delegation proof.
5. Launcher application/local imports are still permitted at top level before singleton acquisition; TASK 041 explicitly left this unfinished.

Fix the causes, not the assertions. Preserve every strong negative test.

## 1. Rebuild transformation: exact supported call contexts

In `candidate_transforms.transform_avtoperedacha_rebuild`:

- keep the TASK 041 requirements for exactly one zero-argument generator, at least one direct in-process call, at least one alias-resolved literal spawn for the same `stranica.py` generator, and BLOCK on unrelated/dynamic/ambiguous spawn;
- classify every direct generator/spawn call by its parent context before rewriting;
- support only:
  - standalone `Expr(Call)` trigger -> standalone `_queue.enqueue()`;
  - exact `Return(Call)` trigger -> `return _queue.enqueue()`;
- any generator/spawn result used in assignment, argument, boolean expression, arithmetic, comprehension, await, yield, condition, decorator/default or another unsupported context BLOCKS instead of guessing semantics;
- replace both supported in-process and related-spawn triggers;
- exclude the generator function definition itself from trigger replacement, but reject recursion/dynamic dispatch;
- insert exactly one queue binding after the generator definition; the callback argument is the function object, never a call;
- post-transform AST verification must count zero direct generator `ast.Call` nodes outside the generator definition and zero resolved spawn calls, exactly one queue assignment/callback identity, zero module-level enqueue/callback execution.

The existing TASK 038 positive fixture and TASK 041 aliased-subprocess fixture must return OK and compile. Unrelated ffmpeg, no direct call, no related spawn, dynamic command, two targets, nonzero args and unsupported call context remain BLOCKED.

Do not weaken the corrected AST assertion.

## 2. SQLite cursor ownership: cover conn.execute cursor and exception safety

Rewrite the Section 1 transform/verifier in `sqlite_ownership.py` while preserving the separate read-only UA-0009 evidence API and all public names.

- Recognize a cursor assigned by either `cur = conn.cursor()` or the common `cur = conn.execute(...)` / supported readonly execute form owned by that exact connection.
- Treat `return cur`, passing/storing/aliasing cur/conn, or any handle escape as BLOCKED.
- Require exactly one local connection and at most one exact cursor.
- Before the generated try, initialize owned handles safely (`conn = None`, and `cur = None` when applicable) so connect/execute/fetch exceptions cannot cause `UnboundLocalError` in finally.
- In finally, guard each close with `is not None`, close cursor first, then connection, on every success/exception path.
- Remove/reconcile original tracked-handle close statements so the candidate does not double-close or leave closes after slow work.
- Materialize `fetchall/fetchmany` results as immutable tuple-of-tuples before close; preserve SELECT text/parameters and later rows use/return.
- Keep timeout=2 exactly once.
- Reject write SQL, commit/rollback, mutable PRAGMA, nonliteral/uncertain SQL, multiple connections/cursors, caller-owned handles, unsupported control flow, fetch/handle escape and slow work inside ownership.
- The verifier tracks each exact connection/cursor independently and proves both closed before every slow call.

Add runtime fake connection/cursor tests for success, connect failure, execute failure and fetch failure. Prove cursor-before-connection close order, no exception masking, immutable rows, unchanged query/parameters and timeout. Existing cursor-close and cursor-return tests must pass.

## 3. Complete launcher import relocation

Remove the residual gap disclosed by TASK 041.

- Preserve module docstring and leading future imports.
- Keep only an explicit positive allowlist of inert stdlib imports above the main guard.
- Move statically resolvable application/local/third-party `import` and `from ... import ...` nodes into the one module-level main-guard body **after** successful singleton installation and before the original main actions. Module-level guard execution preserves global bindings.
- Relative imports, star imports, dynamic imports and imports whose relocation changes decorator/base/default/annotation evaluation semantics BLOCK.
- Scan functions/classes for definition-time expressions that reference a moved alias; ambiguous cases BLOCK.
- Singleton acquisition and duplicate diagnostic/exit 78 must execute before any moved import.
- No application import/startup occurs merely by importing the launcher candidate.
- Generated runtime support restores previous SIGINT/SIGTERM handlers during idempotent cleanup and retains canonical lock/atexit/error-sanitization behavior.

Tests must inspect AST order and safely execute/import candidates using fake modules to prove: importing candidate does not import application modules or acquire a lock; main execution acquires guard first, then imports application module; duplicate exit prevents application import; future imports compile; cleanup restores signal handlers.

## 4. Orchestrator: fail closed with complete evidence and exact eight candidates

Preserve historical `_compute_evidence()/run_gate_a()` behavior. On real `orchestrate_gate_a`:

- On successful transforms, clear any legacy temporary map and set `candidate_sources` to exactly these eight keys:
  `usercustomize_py310.py`, `usercustomize_py313.py`, `start_safe.py`, `run_all.py`, `cars_ui.py`, `avtoperedacha.py`, `samokontrol.py`, `crm_speed_runtime.py`.
- Compile/write/hash/diff exactly those eight; no ninth original `usercustomize.py`.
- On any transform block, record safe original-byte compile-only evidence with `candidate_origin=original_due_to_transform_block` and `accepted_candidate_set=False`, then block. It may not proceed to candidate predicates or PASS.
- Before emitting any receipt, ensure every fixed `REQUIRED_PREDICATES` key exists as a dict with status `OK` or `BLOCKED`. Missing/skipped evidence becomes a bounded `BLOCKED: skipped_due_to_prior_block`, never omitted.
- The canonical no-redirect UA-0009 publication probe must be invoked exactly once per orchestrator run, including early-block runs, with the injected opener. If phase80 did not run it, perform it during phase100 finalization; never fabricate a result.
- Preserve before/after fingerprints, site inventories and SQLite evidence around the full attempted workload.
- BLOCKED receipts must remain structurally verifiable so manifest/report/receipt tamper tests reach the hash-binding checks.
- Full deterministic ten-repeat records and exact eight candidate/diff/install hashes remain present on success.

This must restore all prior manifest/delegation tests without reintroducing a legacy PASS path.

## 5. Tests and acceptance

Correct implementation only; do not delete, skip, rename or weaken existing tests. Update TASK 038/TASK 041 fixtures only when needed to express the same already-required behavior.

Add `test_task_044_final_closure.py` covering:

- direct generator call in Expr and Return contexts;
- unsupported use contexts BLOCK;
- alias spawn positive and all negative spawn probes;
- conn.execute-derived cursor close/escape and runtime exception ordering;
- launcher moved-import order and import safety;
- generated runtime signal restoration;
- exact eight artifacts/hashes;
- early-block complete predicate skeleton and exactly-once publication delegation;
- manifest/report/receipt tamper reasons remain exact;
- six controller probes from TASK 038 now return expected statuses.

Controller command:

```bash
python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

Acceptance:

- all existing 243 tests plus new TASK 044 tests PASS;
- 0 FAIL, 0 ERROR, 0 skipped/expected-failure;
- zero `Exception in thread`;
- after first green, five complete repeat runs;
- manual probes:
  - unrelated ffmpeg -> BLOCKED;
  - no in-process generator call -> BLOCKED;
  - positive direct+literal-related spawn -> OK;
  - unknown usercustomize import -> BLOCKED;
  - future-import launcher -> OK;
  - cursor derived from conn.execute -> closed and materialized;
  - cursor return -> BLOCKED;
  - blocked orchestration -> complete well-formed receipt and never PASS.

## Deliverables

Return complete mutually consistent contents for exactly:

- `cloud/crm_speed_optimization/candidate_transforms.py`
- `cloud/crm_speed_optimization/sqlite_ownership.py`
- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/test_task_038_real_candidates.py`
- `cloud/crm_speed_optimization/test_task_041_architecture_audit.py`
- `cloud/crm_speed_optimization/test_task_044_final_closure.py`
- `cloud/crm_speed_optimization/TASK_044_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Status is `READY_FOR_CONTROLLER_REVIEW_TASK_044`, not READY_FOR_GATE_A, until independent tests and audit. No known residual item may be silently omitted; if incomplete, report BLOCKED.

## Exact current source snapshots

The complete current sources below are from exact commit `65e1b53e71492bebd3b7405a44d04af41e91847a`. Preserve unrelated concurrent repository work during safe rebase.


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/candidate_transforms.py

```python
"""candidate_transforms.py (TASK 041)

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
    try_node.body = original_body
    main_node.body = setup[:-1] + [try_node]

    import_node = ast.ImportFrom(module=RUNTIME_MODULE_NAME, names=[ast.alias(name="SingletonGuard", asname=None)], level=0)

    body = list(tree.body)
    insert_at = _leading_docstring_and_future_offset(body)
    tree.body = body[:insert_at] + [import_node] + body[insert_at:]
    ast.fix_missing_locations(tree)

    try:
        candidate = ast.unparse(tree)
    except Exception as exc:
        return _blocked([f"unparse_failed:{type(exc).__name__}"])
    try:
        compile(candidate, "<launcher>", "exec")
    except SyntaxError as exc:
        return _blocked([f"candidate_compile_failed:{type(exc).__name__}"])

    return _ok(candidate, [], {"lock_path": lock_path, "duplicate_exit_code": 78})


# ---------------------------------------------------------------------------
# 2.4: avtoperedacha.py rebuild-queue candidate (TASK 041 call-graph proof)
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
        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Call):
                if isinstance(value.func, ast.Name) and value.func.id == generator_name:
                    return self._make_enqueue(node)
                if _is_spawn_call_resolved(value, module_aliases, direct_names) and \
                        _spawn_matches_generator(value, generator_name):
                    return self._make_enqueue(node)
            return self.generic_visit(node)

        @staticmethod
        def _make_enqueue(node):
            new_call = ast.Call(
                func=ast.Attribute(value=ast.Name(id="_queue", ctx=ast.Load()), attr="enqueue", ctx=ast.Load()),
                args=[], keywords=[],
            )
            new_expr = ast.Expr(value=new_call)
            ast.copy_location(new_expr, node)
            ast.fix_missing_locations(new_expr)
            return new_expr

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


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/candidate_transforms.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

```python
"""
sqlite_ownership.py (TASK 041 correction of the TASK 034 structural
transform/verifier; the read-only UA-0009 evidence API in Section 2 is
preserved unchanged.)

Two independent capabilities live in this module:

1. The structural (AST-based) transformation and verifier enforcing
   short SQLite ownership: SELECT rows are materialized into ordinary
   immutable values (tuple()) and the cursor/connection are closed
   BEFORE any slow-call category (formatting/hash/sleep/network/
   filesystem/Telegram I/O). TASK 041 corrections:

   - transform_short_ownership now requires exactly one local
     sqlite3.connect assignment and at most one cursor derived only from
     that connection, rejects any branch/loop/try/with inside the
     ownership segment (straight-line only), rejects write SQL
     (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/REPLACE/VACUUM/REINDEX),
     commit()/rollback(), non-literal SQL text, and cursor escape via
     return; it also materializes fetchall()/fetchmany() results into
     tuple() immediately after the fetch call and closes the cursor
     (when present) before the connection.
   - verify_no_live_handle_across_slow_call now tracks each connection
     name and each derived cursor name independently (per-name open/
     closed state) instead of one global boolean, so an unrelated
     `.close()` call on an unrelated object can never mark this
     function's real handles as closed.

2. A canonical, read-only, fail-closed SQLite evidence API used to
   prove UA-0009 row identity/ownership without ever emitting raw field
   values, names, phones, messages, blobs, or database pages. Only
   structural table/column identifiers, bounded row counts/identity
   hashes, and SHA-256 digests are returned. Unchanged from TASK 034.

No network access. No production paths. No writes. No migrations, WAL
changes, VACUUM, REINDEX, or mutable PRAGMAs are ever issued.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import stat
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------
# Section 1: AST-based short-ownership transform and verifier.
# --------------------------------------------------------------------

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}

WRITE_SQL_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "vacuum", "reindex",
)


class AnchorNotFoundError(Exception):
    pass


def _iter_functions(tree: ast.AST, names: Set[str]):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            yield node


def _call_qualname(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = func.value.id + "."
        return base + func.attr
    return ""


def find_db_handle_names(func) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def find_cursor_names(func, handle_names: Set[str]) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("cursor") and isinstance(node.value.func, ast.Attribute):
                owner = getattr(node.value.func.value, "id", None)
                if owner in handle_names:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    return names


def _literal_sql_text(call_node: ast.Call) -> Optional[str]:
    if call_node.args and isinstance(call_node.args[0], ast.Constant) and isinstance(call_node.args[0].value, str):
        return call_node.args[0].value
    return None


def _is_write_sql(sql_text: str) -> bool:
    lowered = sql_text.strip().lower()
    return any(lowered.startswith(k) for k in WRITE_SQL_KEYWORDS)


def _contains_write_sql_or_commit(stmts) -> Optional[str]:
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                qual = _call_qualname(node)
                if qual.endswith("execute") or qual.endswith("executemany"):
                    sql = _literal_sql_text(node)
                    if sql is None:
                        return "non_literal_sql_rejected"
                    if _is_write_sql(sql):
                        return "write_sql_rejected"
                    lowered = sql.strip().lower()
                    if lowered.startswith("pragma") and "=" in lowered and "query_only" not in lowered:
                        return "mutable_pragma_rejected"
                if qual.endswith("commit") or qual.endswith("rollback"):
                    return "commit_or_rollback_rejected"
    return None


def _contains_unsupported_control_flow(stmts) -> bool:
    for stmt in stmts:
        if isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)):
            return True
    return False


def _returns_name(func, name: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == name:
            return True
    return False


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) tracking each connection name and each derived cursor
    name INDEPENDENTLY. A slow call is a violation only for the specific
    names that are still open at that point; an unrelated `.close()`
    call on an unrelated name can never mark this function's real
    handles as closed. Conservative: anything not provably closed before
    a slow call is reported.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    open_names: Set[str] = set()
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("connect"):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) and t.id in handle_names:
                            open_names.add(t.id)
                if qual.endswith("cursor") and isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    if owner in handle_names:
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
                                open_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and owner and (owner in handle_names or owner in cursor_names):
                        open_names.discard(owner)
                    elif any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                             for s in SLOW_CALL_NAMES):
                        if open_names:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before close of {sorted(open_names)}"
                            )
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(stmt, field, None)
                    if isinstance(block, list):
                        walk_stmts(block)
                handlers = getattr(stmt, "handlers", None)
                if handlers:
                    for h in handlers:
                        walk_stmts(h.body)

    walk_stmts(func.body)
    return violations


def _ensure_short_timeout(func, handle_names: Set[str]) -> None:
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                has_timeout = any(kw.arg == "timeout" for kw in node.value.keywords)
                if not has_timeout:
                    node.value.keywords.append(
                        ast.keyword(arg="timeout", value=ast.Constant(value=2))
                    )


def transform_short_ownership(source: str, function_names: Set[str]) -> str:
    """Rewrite the named functions so the sqlite3 connection/cursor is
    guaranteed materialized-and-closed (via try/finally) before any
    subsequent formatting/slow work. Supports only structurally proven
    local ownership: exactly one local sqlite3.connect assignment, zero
    or one cursor derived only from that connection, a straight-line
    ownership segment (no branch/loop/try/with), literal read-only SQL
    (no write keywords, commit, rollback, or mutable PRAGMA), and no
    cursor escape via return. Raises AnchorNotFoundError on any
    unsupported shape.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if len(handle_names) != 1:
            raise AnchorNotFoundError(
                f"expected exactly one local connection in {func.name}, found {len(handle_names)}"
            )
        cursor_names = find_cursor_names(func, handle_names)
        if len(cursor_names) > 1:
            raise AnchorNotFoundError(f"expected zero or one cursor in {func.name}")
        for cname in cursor_names:
            if _returns_name(func, cname):
                raise AnchorNotFoundError(f"cursor escapes function {func.name}")

        _ensure_short_timeout(func, handle_names)

        tracked_names = handle_names | cursor_names
        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            refs_handle = any(
                isinstance(n, ast.Name) and n.id in tracked_names
                for n in ast.walk(stmt)
            )
            if refs_handle:
                handle_stmt_indices.append(idx)
        if not handle_stmt_indices:
            raise AnchorNotFoundError(
                f"DB handle {handle_names} unused after connect in {func.name}"
            )
        last_db_idx = max(handle_stmt_indices)
        db_block = func.body[: last_db_idx + 1]
        rest_block = func.body[last_db_idx + 1:]

        if _contains_unsupported_control_flow(db_block):
            raise AnchorNotFoundError(
                f"unsupported control flow in ownership segment of {func.name}"
            )
        write_reason = _contains_write_sql_or_commit(db_block)
        if write_reason:
            raise AnchorNotFoundError(f"{write_reason} in {func.name}")

        # Materialize fetchall()/fetchmany() results into an immutable
        # tuple immediately after the fetch, before any close/slow work.
        materialized_block = []
        for stmt in db_block:
            materialized_block.append(stmt)
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("fetchall") or qual.endswith("fetchmany"):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            materialize = ast.Assign(
                                targets=[ast.Name(id=t.id, ctx=ast.Store())],
                                value=ast.Call(
                                    func=ast.Name(id="tuple", ctx=ast.Load()),
                                    args=[ast.Name(id=t.id, ctx=ast.Load())],
                                    keywords=[],
                                ),
                            )
                            ast.copy_location(materialize, stmt)
                            materialized_block.append(materialize)
        db_block = materialized_block

        close_stmts = []
        for name in sorted(cursor_names) + sorted(handle_names):
            close_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id=name, ctx=ast.Load()),
                                        attr="close", ctx=ast.Load()),
                    args=[], keywords=[],
                )
            )
            close_stmts.append(close_call)

        try_node = ast.Try(body=db_block, handlers=[], orelse=[], finalbody=close_stmts)
        func.body = [try_node] + rest_block
        ast.fix_missing_locations(func)

    return ast.unparse(tree)


# --------------------------------------------------------------------
# Section 2: canonical read-only, fail-closed SQLite evidence API
# (TASK 034, unchanged). Standard library only. Never raises for
# expected operational conditions.
# --------------------------------------------------------------------

MAX_TABLES = 50
MAX_COLUMNS = 50
MAX_ROWS = 1000
MAX_SERIALIZED_BYTES = 1_000_000


@dataclass
class OwnershipEvidence:
    status: str  # "OK" or "BLOCKED"
    reason: str
    quick_check: Optional[str] = None
    query_only: Optional[int] = None
    table: Optional[str] = None
    row_count: Optional[int] = None
    rows_sha256: Optional[str] = None
    evidence_sha256: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _sanitize(exc: BaseException) -> str:
    # Only the exception class name is ever surfaced -- never the
    # message, which could embed a path or a fragment of data.
    return type(exc).__name__


def _validate_db_path(path: str):
    """Validate the database path with lstat: must be a regular,
    non-symlink file with a stable identity (nlink == 1). Fails closed
    on any hard-link surprise."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"path_stat_failed:{_sanitize(exc)}"
    if stat.S_ISLNK(st.st_mode):
        return False, "path_is_symlink"
    if not stat.S_ISREG(st.st_mode):
        return False, "path_not_regular_file"
    if st.st_nlink != 1:
        return False, "path_hard_linked"
    return True, "ok"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def collect_ua0009_ownership_evidence(
    db_path: str,
    table: str,
    id_column: str,
    id_value: str = "UA-0009",
    timeout: float = 2.0,
    max_tables: int = MAX_TABLES,
    max_columns: int = MAX_COLUMNS,
    max_rows: int = MAX_ROWS,
    max_serialized_bytes: int = MAX_SERIALIZED_BYTES,
) -> OwnershipEvidence:
    """Read-only, fail-closed evidence collection selecting exactly one
    row identified by the configured exact identifier-column rule
    (table/id_column/id_value). The cursor and connection are always
    closed BEFORE any hashing/serialization occurs. Never raises for
    expected operational conditions."""
    valid, reason = _validate_db_path(db_path)
    if not valid:
        return OwnershipEvidence(status="BLOCKED", reason=reason)

    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    quick_check_val = None
    query_only_val = None

    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return OwnershipEvidence(status="BLOCKED", reason=f"open_failed:{_sanitize(exc)}")

    rows = None
    try:
        try:
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA query_only=ON")
                row = cur.execute("PRAGMA query_only").fetchone()
                query_only_val = row[0] if row else None

                row = cur.execute("PRAGMA quick_check").fetchone()
                quick_check_val = row[0] if row else None
                if quick_check_val != "ok":
                    return OwnershipEvidence(
                        status="BLOCKED", reason="quick_check_not_ok",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                tables = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT ?",
                    (max_tables + 1,),
                ).fetchall()
                if len(tables) > max_tables:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="table_overflow",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )
                table_names = {r[0] for r in tables}
                if table not in table_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_table",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                columns = cur.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
                if len(columns) > max_columns:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="column_overflow",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )
                column_names = {c[1] for c in columns}
                if id_column not in column_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_column",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )

                select_sql = (
                    f"SELECT rowid, * FROM {_quote_ident(table)} "
                    f"WHERE {_quote_ident(id_column)} = ? LIMIT ?"
                )
                rows = cur.execute(select_sql, (id_value, max_rows + 1)).fetchall()
            finally:
                cur.close()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return OwnershipEvidence(
            status="BLOCKED", reason=f"sqlite_error:{_sanitize(exc)}",
            quick_check=quick_check_val, query_only=query_only_val,
        )

    # Cursor and connection are now closed. Only materialized, immutable
    # values remain; hashing/serialization happens strictly below.
    if not rows:
        return OwnershipEvidence(
            status="BLOCKED", reason="missing_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    if len(rows) > 1:
        return OwnershipEvidence(
            status="BLOCKED", reason="ambiguous_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )

    serialized = repr(rows[0]).encode("utf-8")
    if len(serialized) > max_serialized_bytes:
        return OwnershipEvidence(
            status="BLOCKED", reason="serialized_overflow",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    row_hash = hashlib.sha256(serialized).hexdigest()
    combined = hashlib.sha256(
        f"{quick_check_val}|{query_only_val}|{table}|{id_column}|{row_hash}".encode("utf-8")
    ).hexdigest()

    return OwnershipEvidence(
        status="OK", reason="ok", quick_check=quick_check_val, query_only=query_only_val,
        table=table, row_count=1, rows_sha256=row_hash, evidence_sha256=combined,
    )


def compare_ownership_evidence(before: OwnershipEvidence, after: OwnershipEvidence):
    """Pure comparison helper for before/after UA-0009 evidence. OK only
    when both evidence objects are complete (status OK) and their
    evidence_sha256 hashes match exactly."""
    if before.status != "OK" or after.status != "OK":
        return False, "incomplete_evidence"
    if not before.evidence_sha256 or not after.evidence_sha256:
        return False, "incomplete_evidence"
    if before.evidence_sha256 != after.evidence_sha256:
        return False, "hash_mismatch"
    return True, "ok"


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
"""CRM-SPEED-001 Gate A orchestration (TASK 032/035 canonical
integration, TASK 038 real candidate-transform integration, TASK 041
fail-closed correction).

This module provides one canonical evidence-computation core plus two
callers:

- run_gate_a(fixture): historical compatibility adapter for in-memory
  source fixtures (unit tests). Unchanged by TASK 038/041.

- orchestrate_gate_a(config, opener=None, clock=None): the real public
  orchestration entry point. TASK 038 extended phase40/60/80 to
  generate, compile, and structurally verify real candidates for both
  usercustomize.py versions, start_safe.py, run_all.py, avtoperedacha.py,
  samokontrol.py, and a generated crm_speed_runtime.py support module.

  TASK 041 correction: the real path now REQUIRES that extended
  candidate generation succeed. If any of the seven source transforms
  is missing/ambiguous/BLOCKED, phase40 immediately raises and the
  overall status is BLOCKED -- there is no parallel legacy/original
  fallback path that can continue to phase80/PASS. On success,
  candidate_sources/extended candidate evidence contains exactly eight
  keys (the seven transformed originals plus crm_speed_runtime.py; the
  legacy original usercustomize.py key is never present), all eight are
  compiled without import/execute, and all eight are written as
  candidates+diffs through SafeWriter.

Gate A is never executed against production by this repository. Every
function here operates only on paths/strings explicitly supplied by the
caller (production launcher DEFAULT_CONFIG or a test fixture/config).
"""
import os
import ast
import stat
import json
import time
import shutil
import secrets
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
import cars_ui_transform
import candidate_transforms
import sqlite_ownership
import ua0009_publication_check

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILES_PER_ROOT = 32

ADMIN_ROUTE_NAMES = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]

MEDIA_METHOD_NAMES = {
    "reply_photo", "reply_video", "reply_media_group", "reply_document",
    "reply_audio", "reply_voice", "reply_animation",
    "send_photo", "send_video", "send_media_group", "send_document",
    "send_audio", "send_voice", "send_animation",
    "download", "download_to_drive", "get_file",
}

DYNAMIC_DISPATCH_FORBIDDEN = {"getattr", "setattr", "eval", "exec", "globals", "locals"}

SAFE_BUILTIN_NAMES = {
    "str", "int", "float", "bool", "len", "print", "list", "dict", "set",
    "tuple", "sorted", "enumerate", "range", "isinstance", "format", "repr",
    "min", "max", "sum", "any", "all", "zip", "map", "filter",
}

ALLOWED_SITE_NAMES = (
    ["index.html", "katalog.html"]
    + [f"UA-000{n}.html" for n in range(1, 10)]
    + [f"UA-000{n}-diag.html" for n in range(1, 10)]
    + [f"UA-000{n}-track.html" for n in range(1, 10)]
)

LAUNCHER_LOCK_PATH = "/home/Carix/qa/crm_speed_task020/launcher_singleton.lock"

DEFAULT_CONFIG = {
    "required_inputs": [
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
    ],
    "site_roots": {
        "/home/Carix/site": ALLOWED_SITE_NAMES,
        "/home/Carix/video": ALLOWED_SITE_NAMES,
        "/home/Carix/public_html": ALLOWED_SITE_NAMES,
    },
    "ua0009_url": "https://ua-art-detailing.ru/UA-0009.html",
    "run_root": "/home/Carix/qa/crm_speed_task020",
    "backup_archive": "/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz",
    "backup_archive_sha256": "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913",
    "protected_function_names": [],
    "db_function_source": None,
    "min_free_bytes": 10 * 1024 * 1024,
    "ua0009_table": None,
    "ua0009_id_column": None,
    "ua0009_id_value": "UA-0009",
}

REQUIRED_PREDICATES = [
    "inputs_present_and_regular",
    "backup_verified",
    "candidates_compile",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_quickcheck_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "site_inventory_unchanged",
    "admin_routes_text_only",
    "media_persistence_unchanged",
    "usercustomize_inert",
    "singleton_guard_present",
    "rebuild_queue_bound_no_process_spawn",
    "db_closed_before_slow_work",
    "deterministic_repeat_all_transforms",
    "no_production_write",
]


class _GateABlocked(Exception):
    """Raised internally to short-circuit an orchestration phase with a
    known reason. Always converted into a BLOCKED phase result."""


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_file(path):
    if not os.path.exists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return {"symlink": True}
    return {
        "mode": st.st_mode,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": _sha256_file(path),
    }


# ---------------------------------------------------------------------------
# Thin adapters around the canonical cars_ui_transform implementation
# ---------------------------------------------------------------------------

def _is_safe_builtin_unresolved(flag):
    if flag.startswith("unresolved_callable:"):
        parts = flag.split(":")
        name = parts[1] if len(parts) > 1 else ""
        return name in SAFE_BUILTIN_NAMES
    return False


def _translate_dynamic_flag(flag):
    if flag.startswith("getattr_dispatch"):
        return "dynamic_dispatch_forbidden:getattr"
    return flag


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    tree = ast.parse(source)
    module_function_names = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    violations = []
    for ep in entry_points:
        if ep not in module_function_names:
            violations.append(f"missing_entry_point:{ep}")

    scan = cars_ui_transform.scan_reachable_call_graph(tree, entry_points)

    for func_name in sorted(scan.reachable):
        for flag in scan.unresolved_dynamic.get(func_name, []):
            if _is_safe_builtin_unresolved(flag):
                continue
            violations.append(_translate_dynamic_flag(flag))
        for call_info in scan.direct_media_calls.get(func_name, []):
            violations.append(f"direct_media_call:{call_info.method}")

    clean = len(violations) == 0
    return clean, violations


def generate_unified_diff(original, candidate):
    original = original or ""
    candidate = candidate or ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="original", tofile="candidate",
    )
    return "".join(diff)


def transform_cars_ui(source, entry_points=None):
    entry_points = entry_points or ADMIN_ROUTE_NAMES
    try:
        clean_before, violations_before = scan_reachable_call_graph(source, entry_points)
    except SyntaxError as exc:
        return {"candidate": None, "status": "BLOCKED", "reasons": [f"syntax_error:{exc}"]}

    dynamic_flags = [v for v in violations_before if not v.startswith("direct_media_call")]
    if dynamic_flags:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before}

    if not violations_before:
        return {"candidate": source, "status": "OK", "reasons": []}

    canonical_result = cars_ui_transform.transform_cars_ui(source, entry_points)
    if canonical_result.get("status") != "OK" or canonical_result.get("candidate") is None:
        reason = canonical_result.get("reason", "canonical_transform_blocked")
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + [reason]}

    candidate = canonical_result["candidate"]
    clean_after, violations_after = scan_reachable_call_graph(candidate, entry_points)
    if not clean_after:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + violations_after}
    return {"candidate": candidate, "status": "OK", "reasons": violations_before}


def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    records = []
    for _ in range(repeats):
        result = transform_fn(source, *args)
        candidate = result.get("candidate")
        status = result.get("status")
        reasons = result.get("reasons", [])
        candidate_bytes = _stable_bytes(candidate)
        diff_text = generate_unified_diff(source, candidate)
        diff_bytes = diff_text.encode("utf-8")
        metadata_digest = hashlib.sha256(
            json.dumps({"status": status, "reasons": reasons}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        records.append({
            "candidate_sha256": _sha256_bytes(candidate_bytes),
            "diff_sha256": _sha256_bytes(diff_bytes),
            "status": status,
            "reasons": reasons,
            "metadata_digest": metadata_digest,
        })
    first = records[0]
    deterministic = all(r == first for r in records)
    return {"deterministic": deterministic, "repeats": repeats, "records": records}


def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    if not os.path.isdir(root):
        return {"status": "BLOCKED", "reason": "missing_root", "root": root}
    matched = []
    for name in allowed_names:
        candidate_path = os.path.join(root, name)
        if os.path.lexists(candidate_path):
            matched.append(candidate_path)
    if len(matched) > max_files_per_root:
        return {
            "status": "BLOCKED", "reason": "overflow",
            "matched_count": len(matched), "max_files_per_root": max_files_per_root,
        }
    entries = []
    for path in matched:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            return {"status": "BLOCKED", "reason": "symlink_rejected", "path": path}
        if not stat.S_ISREG(st.st_mode):
            return {"status": "BLOCKED", "reason": "not_regular_file", "path": path}
        if st.st_nlink != 1:
            return {"status": "BLOCKED", "reason": "hard_link_rejected", "path": path}
        entries.append({
            "path": os.path.realpath(path),
            "mode": st.st_mode,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _sha256_file(path),
        })
    entries.sort(key=lambda e: e["path"])
    return {"status": "OK", "entries": entries, "matched_count": len(matched), "max_files_per_root": max_files_per_root}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
    """Historical fixture-facing adapter, preserved unchanged for
    _compute_evidence()/run_gate_a() compatibility. orchestrate_gate_a()
    uses the canonical ua0009_publication_check.canonical_probe_ua0009
    directly instead (see phase80 below) rather than this adapter."""
    if not url or not url.startswith("https://"):
        return {"status": "BLOCKED", "reason": "missing_or_non_https_url"}
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        req = urllib.request.Request(url, method="GET")
        resp = opener.open(req, timeout=5)
        code = getattr(resp, "getcode", lambda: getattr(resp, "code", None))()
        return {"status": "BLOCKED", "reason": f"unexpected_status_{code}"}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return {"status": "OK", "reason": f"not_served_{exc.code}", "http_status": exc.code}
        return {"status": "BLOCKED", "reason": f"http_error_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"status": "BLOCKED", "reason": f"network_error:{exc.reason}"}
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"probe_exception:{type(exc).__name__}"}


def check_inputs_present_and_regular(paths):
    missing = []
    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
            continue
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            missing.append(p)
    if missing:
        return {"status": "BLOCKED", "missing_or_symlink": missing}
    return {"status": "OK", "checked": paths}


def check_backup_verified(archive_path, expected_sha256):
    if not os.path.exists(archive_path):
        return {"status": "BLOCKED", "reason": "backup_missing"}
    actual = _sha256_file(archive_path)
    if actual != expected_sha256:
        return {"status": "BLOCKED", "reason": "backup_hash_mismatch"}
    return {"status": "OK", "sha256": actual}


def check_candidates_compile(candidate_sources):
    errors = {}
    for name, src in candidate_sources.items():
        try:
            compile(src, name, "exec")
        except SyntaxError as exc:
            errors[name] = str(exc)
    if errors:
        return {"status": "BLOCKED", "errors": errors}
    return {"status": "OK", "compiled": list(candidate_sources.keys())}


def check_protected_fingerprints_unchanged(before, after):
    if not before or not after:
        return {"status": "BLOCKED", "reason": "missing_fingerprints"}
    if before != after:
        diff_keys = [k for k in before if before.get(k) != after.get(k)]
        return {"status": "BLOCKED", "reason": "changed", "diff_keys": diff_keys}
    return {"status": "OK"}


def check_sqlite_readonly_quickcheck_ok(db_path):
    if not os.path.exists(db_path):
        return {"status": "BLOCKED", "reason": "db_missing"}
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON;")
            cur = conn.execute("PRAGMA quick_check;")
            result = cur.fetchone()
        finally:
            conn.close()
        if result and result[0] == "ok":
            return {"status": "OK", "quick_check": result[0]}
        return {"status": "BLOCKED", "reason": "quick_check_failed", "value": result}
    except sqlite3.OperationalError as exc:
        return {"status": "BLOCKED", "reason": f"sqlite_locked_or_error:{exc}"}


def check_admin_routes_text_only(cars_ui_source):
    result = transform_cars_ui(cars_ui_source)
    if result["status"] != "OK" or result["candidate"] is None:
        return {"status": "BLOCKED", "reasons": result["reasons"]}
    clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
    if not clean:
        return {"status": "BLOCKED", "reasons": violations}
    return {"status": "OK", "candidate_sha256": _sha256_bytes(result["candidate"].encode("utf-8"))}


def _extract_function_ast_dumps(source, names):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = ast.dump(node)
    return found


def check_media_persistence_unchanged(original_source, candidate_source, protected_function_names):
    before = _extract_function_ast_dumps(original_source, protected_function_names)
    after = _extract_function_ast_dumps(candidate_source or "", protected_function_names)
    missing = [n for n in protected_function_names if n not in after]
    if missing:
        return {"status": "BLOCKED", "reason": "missing_protected_functions", "missing": missing}
    changed = [n for n in protected_function_names if before.get(n) != after.get(n)]
    if changed:
        return {"status": "BLOCKED", "reason": "protected_functions_changed", "changed": changed}
    return {"status": "OK"}


FORBIDDEN_USERCUSTOMIZE_MODULES = {
    "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
    "threading", "multiprocessing", "subprocess",
}


def check_usercustomize_inert(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                    violations.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                violations.append(f"forbidden_import_from:{node.module}")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            violations.append("top_level_call_statement")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


def check_singleton_guard_present(tmp_dir):
    lock_path = os.path.join(tmp_dir, "singleton.lock")
    guard1 = SingletonGuard(lock_path)
    ok1 = guard1.acquire()
    guard2 = SingletonGuard(lock_path)
    ok2 = guard2.acquire()
    guard1.release()
    guard3 = SingletonGuard(lock_path)
    ok3 = guard3.acquire()
    guard3.release()
    if ok1 and not ok2 and ok3:
        return {"status": "OK"}
    return {"status": "BLOCKED", "reason": "singleton_semantics_violated", "ok1": ok1, "ok2": ok2, "ok3": ok3}


def check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source):
    try:
        tree = ast.parse(avtoperedacha_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    violations.append(f"forbidden_import:{alias.name}")
        if isinstance(node, ast.Attribute) and node.attr in ("system", "Popen", "call", "run", "check_call", "check_output"):
            violations.append(f"forbidden_call_site:{node.attr}")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


SLOW_CALL_NAMES = {"sleep", "send_message", "send_photo", "render", "generate", "post", "request"}


def check_db_closed_before_slow_work(function_source):
    try:
        tree = ast.parse(function_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node
            break
    if func is None:
        return {"status": "BLOCKED", "reason": "no_function_found"}
    close_index = None
    slow_index = None
    for i, stmt in enumerate(func.body):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "close" and close_index is None:
                    close_index = i
                if node.func.attr in SLOW_CALL_NAMES and slow_index is None:
                    slow_index = i
    if close_index is None:
        return {"status": "BLOCKED", "reason": "no_close_found"}
    if slow_index is not None and slow_index < close_index:
        return {"status": "BLOCKED", "reason": "slow_work_before_close"}
    return {"status": "OK", "close_index": close_index, "slow_index": slow_index}


def check_deterministic_repeat_all_transforms(transform_map):
    failures = []
    records = {}
    for name, (fn, source, args) in transform_map.items():
        measurement = measure_deterministic_repeat(fn, source, args=args, repeats=10)
        records[name] = measurement
        if not measurement["deterministic"]:
            failures.append(name)
    if failures:
        return {"status": "BLOCKED", "failures": failures, "records": records}
    return {"status": "OK", "checked": list(transform_map.keys()), "records": records}


def check_site_inventory_unchanged(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    before = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    after = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    if before.get("status") != "OK" or after.get("status") != "OK":
        return {"status": "BLOCKED", "before": before, "after": after}
    if before["entries"] != after["entries"]:
        return {"status": "BLOCKED", "reason": "inventory_changed"}
    return {"status": "OK", "matched_count": before["matched_count"]}


def check_no_production_write(protected_before, protected_after, site_before, site_after):
    if protected_before != protected_after:
        return {"status": "BLOCKED", "reason": "protected_changed"}
    if site_before != site_after:
        return {"status": "BLOCKED", "reason": "site_inventory_changed"}
    return {"status": "OK"}


def _collect_ua0009_sqlite_evidence(config, db_path):
    """Delegates entirely to sqlite_ownership.collect_ua0009_ownership_evidence
    (the exact canonical implementation) -- no duplicated logic. Missing
    table/column/db configuration fails closed (BLOCKED), never
    fabricated."""
    table = config.get("ua0009_table")
    id_column = config.get("ua0009_id_column")
    id_value = config.get("ua0009_id_value", "UA-0009")
    if not db_path or not table or not id_column:
        return sqlite_ownership.OwnershipEvidence(
            status="BLOCKED", reason="ua0009_table_or_column_not_configured"
        )
    return sqlite_ownership.collect_ua0009_ownership_evidence(db_path, table, id_column, id_value)


def evaluate_gate_a(evidence):
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


# ---------------------------------------------------------------------------
# Canonical evidence computation shared by run_gate_a() and
# orchestrate_gate_a()
# ---------------------------------------------------------------------------

def _compute_evidence(fixture):
    evidence = {}
    evidence["inputs_present_and_regular"] = check_inputs_present_and_regular(fixture["required_inputs"])
    evidence["backup_verified"] = check_backup_verified(fixture["backup_archive"], fixture["backup_archive_sha256"])

    cars_ui_candidate = transform_cars_ui(fixture["cars_ui_source"])
    usercustomize_source = fixture["usercustomize_source"]
    avtoperedacha_source = fixture["avtoperedacha_source"]

    candidate_sources = {
        "cars_ui.py": cars_ui_candidate.get("candidate") or fixture["cars_ui_source"],
        "usercustomize.py": usercustomize_source,
        "avtoperedacha.py": avtoperedacha_source,
    }
    evidence["candidates_compile"] = check_candidates_compile(candidate_sources)

    evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"])
    evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(fixture["db_path"])
    evidence["ua0009_fingerprint_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["ua0009_fingerprint_before"], fixture["ua0009_fingerprint_after"])
    evidence["ua0009_not_public"] = check_ua0009_not_public(fixture["ua0009_url"], fixture.get("ua0009_opener"))
    evidence["site_inventory_unchanged"] = check_site_inventory_unchanged(
        fixture["site_root"], fixture["allowed_site_names"], fixture.get("max_files_per_root", DEFAULT_MAX_FILES_PER_ROOT))
    evidence["admin_routes_text_only"] = check_admin_routes_text_only(fixture["cars_ui_source"])
    evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(
        fixture["cars_ui_source"], cars_ui_candidate.get("candidate"), fixture["protected_function_names"])
    evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
    evidence["singleton_guard_present"] = check_singleton_guard_present(fixture["tmp_dir"])
    evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)
    evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(fixture["db_function_source"])
    evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
        "cars_ui": (transform_cars_ui, fixture["cars_ui_source"], ()),
    })
    evidence["no_production_write"] = check_no_production_write(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"],
        fixture.get("site_before"), fixture.get("site_after"))
    return evidence


def _ensure_run_dir(run_dir):
    """Safely create a requested non-existing run_dir after validating
    its parent. Never weakens SafeWriter: SafeWriter still refuses any
    directory that does not already exist by the time it is
    constructed."""
    parent = os.path.dirname(os.path.abspath(run_dir))
    if parent == "":
        parent = "."
    if not os.path.isdir(parent):
        raise ValueError(f"run_dir parent does not exist: {parent}")
    if os.path.islink(parent):
        raise ValueError("run_dir parent must not be a symlink")
    if os.path.islink(run_dir):
        raise ValueError("run_dir must not be a symlink")
    if not os.path.exists(run_dir):
        os.mkdir(run_dir, 0o700)
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir must be a directory")


def run_gate_a(fixture):
    """Historical compatibility adapter for in-memory source fixtures.
    Delegates all predicate evaluation to _compute_evidence() and
    evaluate_gate_a(), the exact same functions used by
    orchestrate_gate_a(). The only adapter-specific behavior is safely
    creating a requested non-existing run_dir after validating its
    parent, so SafeWriter always receives an already-existing directory.
    """
    evidence = _compute_evidence(fixture)
    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "pii_emitted": "NO",
        "generated_at": time.time(),
    }
    run_dir = fixture.get("run_dir")
    if run_dir:
        _ensure_run_dir(run_dir)
        writer = SafeWriter(run_dir)
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt


# ---------------------------------------------------------------------------
# Canonical real orchestration entry point
# ---------------------------------------------------------------------------

def _validate_no_symlink_dir(path):
    if not os.path.isdir(path):
        raise _GateABlocked(f"qa_root_missing_or_not_dir:{path}")
    if os.path.islink(path):
        raise _GateABlocked("qa_root_is_symlink")
    abs_path = os.path.abspath(path)
    cur = ""
    for part in abs_path.split(os.sep):
        if not part:
            if not cur:
                cur = os.sep
            continue
        cur = os.path.join(cur, part) if cur else part
        if os.path.islink(cur):
            raise _GateABlocked(f"symlink_component:{cur}")
    return os.path.realpath(path)


def _create_unique_run_dir(qa_root_real):
    for _ in range(5):
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(6)
        candidate = os.path.join(qa_root_real, run_id)
        try:
            os.mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        if os.path.islink(candidate):
            raise _GateABlocked("run_dir_became_symlink")
        parent_real = os.path.realpath(os.path.dirname(candidate))
        if parent_real != qa_root_real:
            raise _GateABlocked("run_dir_parent_identity_mismatch")
        if os.path.realpath(candidate) != candidate:
            raise _GateABlocked("run_dir_identity_mismatch")
        return candidate
    raise _GateABlocked("could_not_create_unique_run_dir")


def secure_read_file(path):
    try:
        lst = os.lstat(path)
    except FileNotFoundError:
        raise _GateABlocked(f"missing_input:{path}")
    if stat.S_ISLNK(lst.st_mode):
        raise _GateABlocked(f"symlink_input:{path}")
    if not stat.S_ISREG(lst.st_mode):
        raise _GateABlocked(f"non_regular_input:{path}")
    if lst.st_nlink != 1:
        raise _GateABlocked(f"hard_linked_input:{path}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, os.O_RDONLY | nofollow)
    except OSError as exc:
        raise _GateABlocked(f"open_failed:{path}:{type(exc).__name__}")
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_nlink != 1:
            raise _GateABlocked(f"identity_changed_after_open:{path}")
        if fst.st_ino != lst.st_ino or fst.st_dev != lst.st_dev:
            raise _GateABlocked(f"identity_mismatch:{path}")
        with os.fdopen(fd, "rb", closefd=True) as fh:
            data = fh.read()
    except _GateABlocked:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    lst2 = os.lstat(path)
    if stat.S_ISLNK(lst2.st_mode) or not stat.S_ISREG(lst2.st_mode) or lst2.st_nlink != 1:
        raise _GateABlocked(f"identity_changed_after_read:{path}")
    return {
        "path": os.path.realpath(path),
        "size": len(data),
        "mode": lst.st_mode,
        "mtime_ns": lst.st_mtime_ns,
        "sha256": _sha256_bytes(data),
        "data": data,
    }


def _find_input_path(config, filename):
    for p in config.get("required_inputs", []):
        if os.path.basename(p) == filename:
            return p
    return None


def _resolve_unique_input(config, filename):
    matches = [p for p in config.get("required_inputs", []) if os.path.basename(p) == filename]
    if len(matches) != 1:
        return None
    return matches[0]


def _resolve_two_usercustomize_paths(config):
    """TASK 038: resolve exactly two usercustomize.py inputs by their
    Python 3.10 and 3.13 parent path components. Missing/duplicate/
    ambiguous mapping returns (None, None, reason) -- never chooses only
    the first basename match."""
    all_uc = [p for p in config.get("required_inputs", []) if os.path.basename(p) == "usercustomize.py"]
    matches_310 = [p for p in all_uc if "python3.10" in p]
    matches_313 = [p for p in all_uc if "python3.13" in p]
    if len(matches_310) != 1 or len(matches_313) != 1:
        return None, None, "usercustomize_path_resolution_ambiguous_or_missing"
    if matches_310[0] == matches_313[0]:
        return None, None, "usercustomize_path_resolution_ambiguous_or_missing"
    return matches_310[0], matches_313[0], None


def _verify_launcher_candidate_structural(candidate_source, lock_path):
    """AST-based structural verification (TASK 041) replacing substring
    presence checks: proves the runtime SingletonGuard import exists and
    a SingletonGuard(lock_path) call is bound to a name, using the
    exact configured lock path literal."""
    try:
        tree = ast.parse(candidate_source)
    except SyntaxError:
        return False
    has_import = any(
        isinstance(n, ast.ImportFrom) and n.module == candidate_transforms.RUNTIME_MODULE_NAME
        and any(a.name == "SingletonGuard" for a in n.names)
        for n in tree.body
    )
    has_guard_assign = False
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) \
                and n.value.func.id == "SingletonGuard":
            if n.value.args and isinstance(n.value.args[0], ast.Constant) and n.value.args[0].value == lock_path:
                has_guard_assign = True
    return has_import and has_guard_assign


def _render_report(receipt):
    lines = []
    lines.append("# Gate A Report - " + str(receipt.get("task_id")))
    lines.append("Status: " + str(receipt.get("status")))
    lines.append("Run ID: " + str(receipt.get("run_id")))
    lines.append("Generated at: " + str(receipt.get("generated_at")))
    lines.append("")
    lines.append("## Phases")
    for p in receipt.get("phases", []):
        lines.append(
            "- phase " + str(p.get("phase")) + " (" + str(p.get("label")) + "): "
            + str(p.get("status")) + " duration=" + str(p.get("duration")) + "s"
        )
    lines.append("")
    lines.append("## Unmet predicates")
    for u in receipt.get("unmet_predicates", []) or []:
        lines.append("- " + str(u))
    lines.append("")
    lines.append("## Extended (TASK 038/041) candidates")
    ext = receipt.get("extended_candidates", {})
    lines.append("available: " + str(ext.get("available")))
    for r in ext.get("blocked_reasons", []) or []:
        lines.append("- blocked_reason: " + str(r))
    lines.append("")
    lines.append("## Blockers")
    for b in receipt.get("blockers", []) or []:
        lines.append("- " + str(b))
    lines.append("")
    lines.append("PRODUCTION_WRITE: " + str(receipt.get("production_write")))
    lines.append("Next safe action: " + str(receipt.get("next_safe_action")))
    return os.linesep.join(lines) + os.linesep


def orchestrate_gate_a(config, opener=None, clock=None):
    """The single, real, public orchestration entry point."""
    clock = clock or time.monotonic
    phases = []
    evidence = {}
    site_before = {}
    site_after = {}
    candidate_sources = {}
    input_records = {}
    state = {"blocked": False}
    sqlite_state = {"before": None, "after": None}
    run_dir = None
    lock = None
    candidate_writer = None

    def run_phase(num, label, fn):
        start = clock()
        try:
            fn()
            outcome = "OK"
        except _GateABlocked as exc:
            evidence.setdefault("_blockers", []).append(str(exc))
            outcome = "BLOCKED"
        except Exception as exc:
            evidence.setdefault("_blockers", []).append(f"exception:{type(exc).__name__}:{exc}")
            outcome = "BLOCKED"
        end = clock()
        status_field = "finished" if num == 100 else outcome
        phases.append({
            "phase": num, "label": label, "start": start, "end": end,
            "duration": end - start, "status": status_field,
        })
        return outcome

    def phase20():
        nonlocal run_dir, lock
        qa_root_real = _validate_no_symlink_dir(config["run_root"])
        lock = CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        if not lock.acquire():
            raise _GateABlocked("gate_a_lock_held")
        run_dir = _create_unique_run_dir(qa_root_real)
        for p in config["required_inputs"]:
            input_records[p] = secure_read_file(p)
        evidence["inputs_present_and_regular"] = {"status": "OK", "checked": list(input_records.keys())}
        du = shutil.disk_usage(qa_root_real)
        if du.free < config.get("min_free_bytes", 10 * 1024 * 1024):
            raise _GateABlocked("insufficient_free_space")
        backup_result = check_backup_verified(config["backup_archive"], config["backup_archive_sha256"])
        evidence["backup_verified"] = backup_result
        if backup_result["status"] != "OK":
            raise _GateABlocked("backup_verification_failed")
        evidence["_fingerprints_before"] = {p: fingerprint_file(p) for p in config["required_inputs"]}

        db_path = _find_input_path(config, "crm.db")
        sqlite_state["before"] = _collect_ua0009_sqlite_evidence(config, db_path)

        for root, names in config["site_roots"].items():
            site_before[root] = scan_bounded_inventory(root, names)

    def phase40():
        nonlocal candidate_writer
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_path = _resolve_unique_input(config, "cars_ui.py")
        avtoperedacha_path = _resolve_unique_input(config, "avtoperedacha.py")
        if not (cars_ui_path and avtoperedacha_path):
            raise _GateABlocked("missing_source_paths_for_transform")

        cars_ui_source = input_records[cars_ui_path]["data"].decode("utf-8")
        avtoperedacha_source = input_records[avtoperedacha_path]["data"].decode("utf-8")
        evidence["_cars_ui_source"] = cars_ui_source
        evidence["_avtoperedacha_source"] = avtoperedacha_source

        legacy_usercustomize_path = _find_input_path(config, "usercustomize.py")
        legacy_usercustomize_source = None
        if legacy_usercustomize_path:
            legacy_usercustomize_source = input_records[legacy_usercustomize_path]["data"].decode("utf-8")
            evidence["_usercustomize_source"] = legacy_usercustomize_source

        result = transform_cars_ui(cars_ui_source)
        evidence["_transform_result"] = result
        if result["status"] != "OK" or result.get("candidate") is None:
            compile_map = {"cars_ui.py": cars_ui_source}
            if legacy_usercustomize_source is not None:
                compile_map["usercustomize.py"] = legacy_usercustomize_source
            compile_map["avtoperedacha.py"] = avtoperedacha_source
            try:
                compile_result = check_candidates_compile(compile_map)
            except Exception as exc:
                compile_result = {"status": "BLOCKED", "reason": f"exception:{type(exc).__name__}"}
            if compile_result.get("status") == "OK":
                evidence["candidates_compile"] = {
                    "status": "OK",
                    "candidate_origin": "original_due_to_transform_block",
                    "compiled": compile_result.get("compiled", []),
                }
            else:
                evidence["candidates_compile"] = dict(
                    compile_result, candidate_origin="original_due_to_transform_block"
                )
            raise _GateABlocked("cars_ui_transform_blocked")

        candidate_sources["cars_ui.py"] = result["candidate"]
        if legacy_usercustomize_source is not None:
            candidate_sources["usercustomize.py"] = legacy_usercustomize_source
        candidate_sources["avtoperedacha.py"] = avtoperedacha_source
        diff_text = generate_unified_diff(cars_ui_source, candidate_sources["cars_ui.py"])
        evidence["_diff_sha256"] = _sha256_bytes(diff_text.encode("utf-8"))

        # -- TASK 038/041: extended real candidate generation (required) --
        extended = {"available": False, "blocked_reasons": []}
        uc310_path, uc313_path, uc_err = _resolve_two_usercustomize_paths(config)
        if uc_err:
            extended["blocked_reasons"].append(uc_err)
        start_safe_path = _resolve_unique_input(config, "start_safe.py")
        run_all_path = _resolve_unique_input(config, "run_all.py")
        samokontrol_path = _resolve_unique_input(config, "samokontrol.py")
        if not (start_safe_path and run_all_path and samokontrol_path):
            extended["blocked_reasons"].append("missing_launcher_or_samokontrol_paths")

        if not extended["blocked_reasons"]:
            try:
                uc310_source = input_records[uc310_path]["data"].decode("utf-8")
                uc313_source = input_records[uc313_path]["data"].decode("utf-8")
                start_safe_source = input_records[start_safe_path]["data"].decode("utf-8")
                run_all_source = input_records[run_all_path]["data"].decode("utf-8")
                samokontrol_source = input_records[samokontrol_path]["data"].decode("utf-8")

                evidence["_launcher_lock_path"] = LAUNCHER_LOCK_PATH
                support_source = candidate_transforms.generate_runtime_support_source()

                per_result = {
                    "usercustomize_py310.py": candidate_transforms.transform_usercustomize(uc310_source, "py310"),
                    "usercustomize_py313.py": candidate_transforms.transform_usercustomize(uc313_source, "py313"),
                    "start_safe.py": candidate_transforms.transform_launcher_singleton(start_safe_source, LAUNCHER_LOCK_PATH),
                    "run_all.py": candidate_transforms.transform_launcher_singleton(run_all_source, LAUNCHER_LOCK_PATH),
                    "avtoperedacha.py": candidate_transforms.transform_avtoperedacha_rebuild(avtoperedacha_source),
                    "samokontrol.py": candidate_transforms.transform_sqlite_short_ownership(samokontrol_source),
                }
                originals = {
                    "usercustomize_py310.py": uc310_source,
                    "usercustomize_py313.py": uc313_source,
                    "start_safe.py": start_safe_source,
                    "run_all.py": run_all_source,
                    "avtoperedacha.py": avtoperedacha_source,
                    "samokontrol.py": samokontrol_source,
                }

                evidence["_extended_per_result"] = {
                    name: {"status": r["status"], "reasons": r.get("reasons", []), "metadata": r.get("metadata", {})}
                    for name, r in per_result.items()
                }

                blocked_names = [n for n, r in per_result.items() if r["status"] != "OK" or r.get("candidate") is None]
                if blocked_names:
                    extended["blocked_reasons"].append("transform_blocked:" + ",".join(sorted(blocked_names)))
                else:
                    extended_candidate_sources = {name: r["candidate"] for name, r in per_result.items()}
                    extended_candidate_sources["crm_speed_runtime.py"] = support_source
                    extended_candidate_sources["cars_ui.py"] = candidate_sources["cars_ui.py"]
                    originals["crm_speed_runtime.py"] = ""
                    originals["cars_ui.py"] = cars_ui_source
                    evidence["_extended_candidate_sources"] = extended_candidate_sources
                    evidence["_extended_originals"] = originals

                    if len(extended_candidate_sources) != 8:
                        extended["blocked_reasons"].append("extended_candidate_count_invalid")
                    else:
                        candidate_writer = SafeWriter(run_dir)
                        for name, src in extended_candidate_sources.items():
                            candidate_writer.write_text(os.path.join("candidates", name), src)
                            diff_txt = generate_unified_diff(originals.get(name, ""), src)
                            candidate_writer.write_text(os.path.join("diffs", name + ".diff"), diff_txt)

                        extended["available"] = True
                        extended["support_module_sha256"] = _sha256_bytes(support_source.encode("utf-8"))
            except Exception as exc:
                extended["blocked_reasons"].append(f"exception:{type(exc).__name__}")

        evidence["_extended"] = extended

        # TASK 041: no legacy/original fallback continues to phase80/PASS.
        # If extended generation is not fully available, phase40 blocks
        # immediately.
        if not extended.get("available"):
            raise _GateABlocked(
                "extended_candidate_generation_unavailable:" + ";".join(extended.get("blocked_reasons", []))
            )

    def phase60():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        extended = evidence.get("_extended", {})
        if extended.get("available"):
            full_sources = dict(evidence.get("_extended_candidate_sources", {}))
        else:
            if not candidate_sources:
                raise _GateABlocked("no_candidates_to_compile")
            full_sources = dict(candidate_sources)
        result = check_candidates_compile(full_sources)
        if result.get("status") == "OK":
            result = dict(result)
            result["hashes"] = {k: _sha256_bytes(v.encode("utf-8")) for k, v in full_sources.items()}
        evidence["candidates_compile"] = result
        evidence["_candidate_hashes"] = result.get("hashes", {})
        if result["status"] != "OK":
            raise _GateABlocked("compile_failed")

    def phase80():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_source = evidence.get("_cars_ui_source")
        candidate = candidate_sources.get("cars_ui.py")
        avtoperedacha_source = evidence.get("_avtoperedacha_source")
        extended = evidence.get("_extended", {})

        evidence["admin_routes_text_only"] = check_admin_routes_text_only(cars_ui_source)

        protected_names = config.get("protected_function_names") or []
        if not protected_names:
            evidence["media_persistence_unchanged"] = {"status": "BLOCKED", "reason": "protected_function_names_not_configured"}
        else:
            evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(cars_ui_source, candidate, protected_names)

        db_path = _find_input_path(config, "crm.db")
        if db_path:
            evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(db_path)
        else:
            evidence["sqlite_readonly_quickcheck_ok"] = {"status": "BLOCKED", "reason": "db_path_not_configured"}

        if extended.get("available"):
            ext_sources = evidence.get("_extended_candidate_sources", {})
            ext_originals = evidence.get("_extended_originals", {})

            uc310 = ext_sources.get("usercustomize_py310.py", "")
            uc313 = ext_sources.get("usercustomize_py313.py", "")
            inert310 = check_usercustomize_inert(uc310)
            inert313 = check_usercustomize_inert(uc313)
            if inert310["status"] == "OK" and inert313["status"] == "OK":
                evidence["usercustomize_inert"] = {"status": "OK", "py310": inert310, "py313": inert313}
            else:
                evidence["usercustomize_inert"] = {"status": "BLOCKED", "py310": inert310, "py313": inert313}

            start_safe_candidate = ext_sources.get("start_safe.py", "")
            run_all_candidate = ext_sources.get("run_all.py", "")
            launcher_lock = evidence.get("_launcher_lock_path", "")
            static_ok = (
                _verify_launcher_candidate_structural(start_safe_candidate, launcher_lock)
                and _verify_launcher_candidate_structural(run_all_candidate, launcher_lock)
            )
            behavioral = check_singleton_guard_present(run_dir)
            if static_ok and behavioral["status"] == "OK":
                evidence["singleton_guard_present"] = {"status": "OK"}
            else:
                evidence["singleton_guard_present"] = {"status": "BLOCKED", "static_ok": static_ok, "behavioral": behavioral}

            avto_candidate = ext_sources.get("avtoperedacha.py", "")
            evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avto_candidate)

            samokontrol_candidate = ext_sources.get("samokontrol.py", "")
            db_check_avto = candidate_transforms.check_db_closed_before_slow_work_candidate(avto_candidate)
            db_check_samo = candidate_transforms.check_db_closed_before_slow_work_candidate(samokontrol_candidate)
            if db_check_avto["status"] == "OK" and db_check_samo["status"] == "OK":
                evidence["db_closed_before_slow_work"] = {"status": "OK"}
            else:
                evidence["db_closed_before_slow_work"] = {
                    "status": "BLOCKED", "avtoperedacha": db_check_avto, "samokontrol": db_check_samo,
                }

            det_map = {
                "cars_ui": (transform_cars_ui, cars_ui_source, ()),
                "usercustomize_py310": (candidate_transforms.transform_usercustomize, ext_originals.get("usercustomize_py310.py", ""), ("py310",)),
                "usercustomize_py313": (candidate_transforms.transform_usercustomize, ext_originals.get("usercustomize_py313.py", ""), ("py313",)),
                "start_safe": (candidate_transforms.transform_launcher_singleton, ext_originals.get("start_safe.py", ""), (launcher_lock,)),
                "run_all": (candidate_transforms.transform_launcher_singleton, ext_originals.get("run_all.py", ""), (launcher_lock,)),
                "avtoperedacha": (candidate_transforms.transform_avtoperedacha_rebuild, ext_originals.get("avtoperedacha.py", ""), ()),
                "samokontrol": (candidate_transforms.transform_sqlite_short_ownership, ext_originals.get("samokontrol.py", ""), ()),
            }
            det_result = check_deterministic_repeat_all_transforms(det_map)
            support_hash = _sha256_bytes(candidate_transforms.generate_runtime_support_source().encode("utf-8"))
            support_deterministic = all(
                _sha256_bytes(candidate_transforms.generate_runtime_support_source().encode("utf-8")) == support_hash
                for _ in range(10)
            )
            if det_result["status"] == "OK" and support_deterministic:
                evidence["deterministic_repeat_all_transforms"] = {
                    "status": "OK", "checked": list(det_map.keys()) + ["support_module"],
                    "support_module_sha256": support_hash, "records": det_result.get("records", {}),
                }
            else:
                evidence["deterministic_repeat_all_transforms"] = {
                    "status": "BLOCKED", "det_result": det_result, "support_deterministic": support_deterministic,
                }
        else:
            evidence["usercustomize_inert"] = check_usercustomize_inert(evidence.get("_usercustomize_source", "") or "")
            evidence["singleton_guard_present"] = check_singleton_guard_present(run_dir)
            evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)
            db_function_source = config.get("db_function_source")
            if db_function_source:
                evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(db_function_source)
            else:
                evidence["db_closed_before_slow_work"] = {"status": "BLOCKED", "reason": "db_function_source_not_configured"}
            evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
                "cars_ui": (transform_cars_ui, cars_ui_source, ()),
            })

        publication_result = ua0009_publication_check.canonical_probe_ua0009(config["ua0009_url"], opener=opener)
        evidence["ua0009_not_public"] = {
            "status": "OK" if publication_result.status == "PASS" else "BLOCKED",
            "reason": publication_result.reason,
            "http_status": publication_result.status_code,
        }

        required_here = [
            "admin_routes_text_only", "media_persistence_unchanged", "usercustomize_inert",
            "singleton_guard_present", "rebuild_queue_bound_no_process_spawn",
            "sqlite_readonly_quickcheck_ok", "db_closed_before_slow_work",
            "deterministic_repeat_all_transforms", "ua0009_not_public",
        ]
        failed = [k for k in required_here if evidence.get(k, {}).get("status") != "OK"]
        if failed:
            raise _GateABlocked("predicate_failed:" + ",".join(failed))

    def phase100():
        fingerprints_after = {p: fingerprint_file(p) for p in config["required_inputs"]}
        evidence["_fingerprints_after"] = fingerprints_after
        fingerprints_before = evidence.get("_fingerprints_before")
        if fingerprints_before:
            evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(fingerprints_before, fingerprints_after)
        else:
            evidence["protected_fingerprints_unchanged"] = {"status": "BLOCKED", "reason": "missing_before_fingerprints"}
        for root, names in config["site_roots"].items():
            try:
                site_after[root] = scan_bounded_inventory(root, names)
            except Exception as exc:
                site_after[root] = {"status": "BLOCKED", "reason": f"exception:{type(exc).__name__}"}
        site_ok = True
        changed_roots = []
        for root in config["site_roots"]:
            b = site_before.get(root)
            a = site_after.get(root)
            if not b or b.get("status") != "OK" or not a or a.get("status") != "OK" or b.get("entries") != a.get("entries"):
                site_ok = False
                changed_roots.append(root)
        evidence["site_inventory_unchanged"] = {"status": "OK"} if site_ok else {"status": "BLOCKED", "changed_roots": changed_roots}

        db_path = _find_input_path(config, "crm.db")
        before_ev = sqlite_state["before"] or sqlite_ownership.OwnershipEvidence(
            status="BLOCKED", reason="not_collected_before_block"
        )
        after_ev = _collect_ua0009_sqlite_evidence(config, db_path)
        sqlite_state["before"] = before_ev
        sqlite_state["after"] = after_ev
        cmp_ok, cmp_reason = sqlite_ownership.compare_ownership_evidence(before_ev, after_ev)
        evidence["ua0009_fingerprint_unchanged"] = {"status": "OK" if cmp_ok else "BLOCKED", "reason": cmp_reason}
        evidence["_sqlite_ownership_before"] = before_ev.to_dict()
        evidence["_sqlite_ownership_after"] = after_ev.to_dict()

        evidence["no_production_write"] = check_no_production_write(
            evidence.get("_fingerprints_before") or {}, fingerprints_after, site_before, site_after)

    try:
        outcome = run_phase(20, "lock_preflight_backup_fingerprints_sqlite_before", phase20)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(40, "secure_source_reads_and_candidate_diff", phase40)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(60, "compile_candidates", phase60)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(80, "structural_concurrency_sqlite_media_publication", phase80)
        if outcome != "OK":
            state["blocked"] = True
        run_phase(100, "finalization_fingerprints_inventories_sqlite_after_receipt", phase100)

        public_evidence = {k: v for k, v in evidence.items() if not k.startswith("_")}
        status, unmet = evaluate_gate_a(public_evidence)

        extended_info = evidence.get("_extended", {})
        receipt = {
            "task_id": "CRM-SPEED-001",
            "run_id": os.path.basename(run_dir) if run_dir else None,
            "generated_at": time.time(),
            "phases": phases,
            "status": status,
            "unmet_predicates": unmet,
            "evidence": public_evidence,
            "package_hashes": evidence.get("_candidate_hashes", {}),
            "diff_sha256": evidence.get("_diff_sha256"),
            "site_inventories": {"before": site_before, "after": site_after},
            "sqlite_ownership": {
                "before": evidence.get("_sqlite_ownership_before"),
                "after": evidence.get("_sqlite_ownership_after"),
            },
            "publication_result": public_evidence.get("ua0009_not_public"),
            "extended_candidates": {
                "available": extended_info.get("available", False),
                "blocked_reasons": extended_info.get("blocked_reasons", []),
                "per_candidate": evidence.get("_extended_per_result", {}),
                "support_module_sha256": extended_info.get("support_module_sha256"),
                "candidate_hashes": {
                    k: _sha256_bytes(v.encode("utf-8"))
                    for k, v in evidence.get("_extended_candidate_sources", {}).items()
                },
                "support_module_install_target": "crm_speed_runtime.py",
            },
            "synthetic_latency": {"non_production": True, "value_ms": 0},
            "blockers": evidence.get("_blockers", []),
            "allowed_write_ledger": [],
            "next_safe_action": (
                "await_task_041_controller_review_then_owner_gate_b_review"
                if status == "BLOCKED" else
                "await_owner_gate_b_approval"
            ),
            "production_write": "NO",
            "pii_emitted": "NO",
        }

        if run_dir is not None:
            try:
                final_writer = SafeWriter(run_dir)
                final_writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
                final_writer.write_text("report.md", _render_report(receipt))
                combined_ledger = list(candidate_writer.ledger) if candidate_writer is not None else []
                combined_ledger.extend(final_writer.ledger)
                receipt["allowed_write_ledger"] = combined_ledger
                final_writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
            except Exception as exc:
                receipt.setdefault("blockers", []).append(f"receipt_write_failed:{type(exc).__name__}")
        return receipt
    finally:
        if lock is not None:
            lock.release()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_038_real_candidates.py

```python
"""Offline, deterministic executable tests for TASK 038: RebuildQueue
no-escaped-exception correction and real candidate-transform pipeline
(candidate_transforms.py) plus its integration into
crm_speed_gate_a.orchestrate_gate_a.

TASK 041 correction applied to this file only as explicitly authorized:
(1) the invalid string-substring assertion in
    test_single_generator_binds_to_one_queue_no_spawn was replaced with
    an AST call-site assertion (a FunctionDef string can never satisfy
    an ast.Call check), and (2) AVTOPEREDACHA_SOURCE was updated to
    contain both a real in-process call site and a literal stranica.py
    process-spawn site for the same generator, since TASK 041 hardened
    transform_avtoperedacha_rebuild to require actual call-graph proof
    instead of function-name hints.

No network access. No PythonAnywhere paths. No /home/Carix access. Only
temporary directories, local threads/processes and a fake 404 HTTPS
opener are used. No other existing tests are modified, skipped, or
weakened.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""
import ast
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import candidate_transforms
import crm_speed_gate_a as gate_a
import sqlite_ownership

from test_crm_speed_gate_a import CLEAN_CARS_UI, _FakeOpener


def _fake_opener_404():
    return _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))


# ---------------------------------------------------------------------------
# 1. RebuildQueue no-escaped-exception correction (Defect A)
# ---------------------------------------------------------------------------

class RebuildQueueNoEscapeTests(unittest.TestCase):
    def test_deleted_lock_parent_no_escaped_exception(self):
        tmp = tempfile.mkdtemp(prefix="task038_rq_")
        sub = os.path.join(tmp, "sub")
        os.makedirs(sub)
        lock_path = os.path.join(sub, "rebuild.lock")

        excepthook_calls = []
        original_hook = threading.excepthook

        def spy_hook(args):
            excepthook_calls.append(args)

        threading.excepthook = spy_hook
        try:
            callback_calls = []
            q = canonical_modules.RebuildQueue(lambda: callback_calls.append(1), lock_path)
            shutil.rmtree(tmp)  # delete the lock parent before the worker runs
            status = q.enqueue()
            self.assertEqual(status, "accepted")

            deadline = time.time() + 3
            while not q.is_idle() and time.time() < deadline:
                time.sleep(0.01)
            q.shutdown(timeout=3)

            self.assertEqual(excepthook_calls, [])
            self.assertEqual(callback_calls, [])
            self.assertEqual(len(q.errors), 1)
            self.assertTrue(q.is_idle())
            self.assertFalse(os.path.exists(tmp))
        finally:
            threading.excepthook = original_hook
            shutil.rmtree(tmp, ignore_errors=True)

    def test_burst_still_coalesces_after_correction(self):
        tmp = tempfile.mkdtemp(prefix="task038_rq2_")
        try:
            gate = threading.Event()
            calls = []

            def cb():
                gate.wait(timeout=3)
                calls.append(1)

            q = canonical_modules.RebuildQueue(cb, os.path.join(tmp, "rebuild.lock"))
            self.assertEqual(q.enqueue(), "accepted")
            for _ in range(5):
                q.enqueue()
            gate.set()
            q.shutdown(timeout=5)
            self.assertEqual(len(calls), 2)
            self.assertEqual(q.runs, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3/4. usercustomize candidate transforms and two-path resolution
# ---------------------------------------------------------------------------

USERCUSTOMIZE_310_SOURCE = (
    '"""py310 sitecustomize"""\n'
    "import sys\n"
    "import team_bot\n"
    "X = 1\n"
    "def helper():\n"
    "    return 42\n"
)

USERCUSTOMIZE_313_SOURCE = (
    '"""py313 sitecustomize"""\n'
    "import sys\n"
    "import avtoperedacha\n"
    "Y = [1, 2, 3]\n"
)

USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT = (
    "import sys\n"
    "print('hello')\n"
)


class UsercustomizeTransformTests(unittest.TestCase):
    def test_forbidden_import_removed_harmless_preserved(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_310_SOURCE, "py310")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("team_bot", result["candidate"])
        self.assertIn("def helper", result["candidate"])
        self.assertIn("X = 1", result["candidate"])
        compile(result["candidate"], "<c>", "exec")

    def test_second_version_removes_different_forbidden_import(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_313_SOURCE, "py313")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("avtoperedacha", result["candidate"])
        self.assertIn("Y = ", result["candidate"])

    def test_unknown_top_level_side_effect_blocks(self):
        result = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT, "py310")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])


class TwoPathResolutionTests(unittest.TestCase):
    def test_two_distinct_paths_resolve(self):
        cfg = {"required_inputs": [
            "/x/python3.10/site-packages/usercustomize.py",
            "/x/python3.13/site-packages/usercustomize.py",
        ]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(err)
        self.assertNotEqual(p310, p313)

    def test_single_flat_usercustomize_blocks(self):
        cfg = {"required_inputs": ["/x/usercustomize.py"]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(p310)
        self.assertIsNone(p313)
        self.assertIsNotNone(err)

    def test_duplicate_python310_paths_block(self):
        cfg = {"required_inputs": [
            "/x/python3.10/a/usercustomize.py",
            "/x/python3.10/b/usercustomize.py",
            "/x/python3.13/site-packages/usercustomize.py",
        ]}
        p310, p313, err = gate_a._resolve_two_usercustomize_paths(cfg)
        self.assertIsNone(p310)
        self.assertIsNotNone(err)


# ---------------------------------------------------------------------------
# 5. start_safe.py / run_all.py singleton candidates
# ---------------------------------------------------------------------------

START_SAFE_SOURCE = (
    "import sys\n\n"
    "def main():\n"
    "    print('running')\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

RUN_ALL_SOURCE = (
    "import sys\n\n"
    "def entry():\n"
    "    return 1\n\n"
    "if __name__ == '__main__':\n"
    "    entry()\n"
)

START_SAFE_BAD_IMPORT_TIME_EFFECT = (
    "import sys\n"
    "sys.stdout.write('start')\n"
    "if __name__ == '__main__':\n"
    "    pass\n"
)

START_SAFE_BAD_TWO_MAIN = (
    "if __name__ == '__main__':\n"
    "    pass\n"
    "if __name__ == '__main__':\n"
    "    pass\n"
)


class LauncherSingletonTests(unittest.TestCase):
    LOCK_PATH = "/home/Carix/qa/crm_speed_task020/launcher_singleton.lock"

    def test_start_safe_and_run_all_get_same_singleton_lock(self):
        r1 = candidate_transforms.transform_launcher_singleton(START_SAFE_SOURCE, self.LOCK_PATH)
        r2 = candidate_transforms.transform_launcher_singleton(RUN_ALL_SOURCE, self.LOCK_PATH)
        self.assertEqual(r1["status"], "OK")
        self.assertEqual(r2["status"], "OK")
        self.assertIn("SingletonGuard", r1["candidate"])
        self.assertIn("SingletonGuard", r2["candidate"])
        self.assertIn(self.LOCK_PATH, r1["candidate"])
        self.assertIn(self.LOCK_PATH, r2["candidate"])
        self.assertIn(candidate_transforms.RUNTIME_MODULE_NAME, r1["candidate"])
        compile(r1["candidate"], "<c>", "exec")
        compile(r2["candidate"], "<c>", "exec")

    def test_import_time_side_effect_blocks(self):
        result = candidate_transforms.transform_launcher_singleton(START_SAFE_BAD_IMPORT_TIME_EFFECT, self.LOCK_PATH)
        self.assertEqual(result["status"], "BLOCKED")

    def test_multiple_main_anchors_block(self):
        result = candidate_transforms.transform_launcher_singleton(START_SAFE_BAD_TWO_MAIN, self.LOCK_PATH)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 6. avtoperedacha rebuild-queue binding
# ---------------------------------------------------------------------------

AVTOPEREDACHA_SOURCE = (
    "import subprocess\n\n"
    "def generate_stranica_page():\n"
    "    return 'page'\n\n"
    "def call_generator_directly():\n"
    "    return generate_stranica_page()\n\n"
    "def handle_update():\n"
    "    subprocess.Popen(['python3', 'stranica.py'])\n"
)

AVTOPEREDACHA_TWO_GENERATORS = (
    "import subprocess\n\n"
    "def generate_stranica_a():\n"
    "    return 1\n\n"
    "def generate_stranica_b():\n"
    "    return 2\n\n"
    "def handle():\n"
    "    subprocess.Popen(['x'])\n"
)


class AvtoperedachaRebuildTests(unittest.TestCase):
    def test_single_generator_binds_to_one_queue_no_spawn(self):
        result = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_SOURCE)
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("subprocess", result["candidate"])
        self.assertIn("_queue.enqueue()", result["candidate"])
        self.assertIn("RebuildQueue", result["candidate"])
        compile(result["candidate"], "<c>", "exec")
        # TASK 041: AST call-site assertion -- a FunctionDef string can
        # never satisfy an ast.Call check, unlike the prior invalid
        # substring assertion. Proves zero remaining direct calls to the
        # generator outside the queue binding.
        candidate_tree = ast.parse(result["candidate"])
        direct_calls = [
            n for n in ast.walk(candidate_tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "generate_stranica_page"
        ]
        self.assertEqual(direct_calls, [])

    def test_two_generator_candidates_block(self):
        result = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_TWO_GENERATORS)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_spawn_present_blocks(self):
        source = "def generate_stranica_page():\n    return 1\n"
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 7. sqlite short ownership candidate for avtoperedacha/samokontrol
# ---------------------------------------------------------------------------

SAMOKONTROL_SOURCE = (
    "import sqlite3\n"
    "import time\n\n"
    "def check_db():\n"
    "    conn = sqlite3.connect('x.db')\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

SAMOKONTROL_NO_DB_FUNCTIONS = (
    "def helper():\n"
    "    return 1\n"
)


class SqliteOwnershipCandidateTests(unittest.TestCase):
    def test_samokontrol_candidate_materializes_and_closes_before_slow_work(self):
        result = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_SOURCE)
        self.assertEqual(result["status"], "OK")
        check = candidate_transforms.check_db_closed_before_slow_work_candidate(result["candidate"])
        self.assertEqual(check["status"], "OK", check)
        tree = ast.parse(result["candidate"])
        found_try = any(isinstance(n, ast.Try) and n.finalbody for n in ast.walk(tree))
        self.assertTrue(found_try)

    def test_avtoperedacha_style_db_function_also_transforms(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def kolonki_cars(conn=None):\n"
            "    conn = sqlite3.connect('y.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    time.sleep(0)\n"
            "    return rows\n"
        )
        result = candidate_transforms.transform_sqlite_short_ownership(source)
        self.assertEqual(result["status"], "OK")

    def test_no_db_functions_blocks(self):
        result = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_NO_DB_FUNCTIONS)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 8/9/13. compile all eight candidates + deterministic repeat + support module
# ---------------------------------------------------------------------------

class EightCandidateCompileAndDeterminismTests(unittest.TestCase):
    def test_compile_all_eight_without_import(self):
        support = candidate_transforms.generate_runtime_support_source()
        r_uc310 = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_310_SOURCE, "py310")
        r_uc313 = candidate_transforms.transform_usercustomize(USERCUSTOMIZE_313_SOURCE, "py313")
        r_start = candidate_transforms.transform_launcher_singleton(START_SAFE_SOURCE, LauncherSingletonTests.LOCK_PATH)
        r_run = candidate_transforms.transform_launcher_singleton(RUN_ALL_SOURCE, LauncherSingletonTests.LOCK_PATH)
        r_avto = candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_SOURCE)
        r_samo = candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_SOURCE)
        cars_ui_result = gate_a.transform_cars_ui(CLEAN_CARS_UI)

        sources = {
            "crm_speed_runtime.py": support,
            "usercustomize_py310.py": r_uc310["candidate"],
            "usercustomize_py313.py": r_uc313["candidate"],
            "start_safe.py": r_start["candidate"],
            "run_all.py": r_run["candidate"],
            "avtoperedacha.py": r_avto["candidate"],
            "samokontrol.py": r_samo["candidate"],
            "cars_ui.py": cars_ui_result["candidate"],
        }
        self.assertEqual(len(sources), 8)
        for name, src in sources.items():
            self.assertIsNotNone(src, name)
            compile(src, name, "exec")
        self.assertNotIn("usercustomize_py310", sys.modules)
        self.assertNotIn("crm_speed_runtime", sys.modules)

    def test_all_seven_transforms_plus_support_are_deterministic(self):
        cases = [
            (candidate_transforms.transform_usercustomize, USERCUSTOMIZE_310_SOURCE, ("py310",)),
            (candidate_transforms.transform_usercustomize, USERCUSTOMIZE_313_SOURCE, ("py313",)),
            (candidate_transforms.transform_launcher_singleton, START_SAFE_SOURCE, (LauncherSingletonTests.LOCK_PATH,)),
            (candidate_transforms.transform_launcher_singleton, RUN_ALL_SOURCE, (LauncherSingletonTests.LOCK_PATH,)),
            (candidate_transforms.transform_avtoperedacha_rebuild, AVTOPEREDACHA_SOURCE, ()),
            (candidate_transforms.transform_sqlite_short_ownership, SAMOKONTROL_SOURCE, ()),
            (gate_a.transform_cars_ui, CLEAN_CARS_UI, ()),
        ]
        for fn, source, args in cases:
            measurement = gate_a.measure_deterministic_repeat(fn, source, args=args, repeats=10)
            self.assertTrue(measurement["deterministic"], fn.__name__)

        support_hashes = set()
        for _ in range(10):
            support_hashes.add(gate_a._sha256_bytes(candidate_transforms.generate_runtime_support_source().encode("utf-8")))
        self.assertEqual(len(support_hashes), 1)

    def test_blocked_transform_never_yields_a_candidate(self):
        blocked_results = [
            candidate_transforms.transform_usercustomize(USERCUSTOMIZE_UNKNOWN_SIDE_EFFECT, "py310"),
            candidate_transforms.transform_launcher_singleton(START_SAFE_BAD_TWO_MAIN, LauncherSingletonTests.LOCK_PATH),
            candidate_transforms.transform_avtoperedacha_rebuild(AVTOPEREDACHA_TWO_GENERATORS),
            candidate_transforms.transform_sqlite_short_ownership(SAMOKONTROL_NO_DB_FUNCTIONS),
        ]
        for r in blocked_results:
            self.assertEqual(r["status"], "BLOCKED")
            self.assertIsNone(r["candidate"])


# ---------------------------------------------------------------------------
# 10/12/14. Full synthetic orchestrate_gate_a integration
# ---------------------------------------------------------------------------

def _make_full_extended_config():
    tmp = tempfile.mkdtemp(prefix="task038_full_")
    py310_dir = os.path.join(tmp, "python3.10", "site-packages")
    py313_dir = os.path.join(tmp, "python3.13", "site-packages")
    os.makedirs(py310_dir)
    os.makedirs(py313_dir)

    required = []

    def _write(path, content):
        with open(path, "w") as fh:
            fh.write(content)
        required.append(path)

    _write(os.path.join(py310_dir, "usercustomize.py"), USERCUSTOMIZE_310_SOURCE)
    _write(os.path.join(py313_dir, "usercustomize.py"), USERCUSTOMIZE_313_SOURCE)
    _write(os.path.join(tmp, "start_safe.py"), START_SAFE_SOURCE)
    _write(os.path.join(tmp, "run_all.py"), RUN_ALL_SOURCE)
    _write(os.path.join(tmp, "cars_ui.py"), CLEAN_CARS_UI)
    _write(os.path.join(tmp, "avtoperedacha.py"), AVTOPEREDACHA_SOURCE)
    _write(os.path.join(tmp, "samokontrol.py"), SAMOKONTROL_SOURCE)
    _write(os.path.join(tmp, "db.py"), "# fixture\n")
    _write(os.path.join(tmp, "team_bot.py"), "# fixture\n")
    _write(os.path.join(tmp, "stranica.py"), "# fixture\n")

    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_path = os.path.join(tmp, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha = gate_a._sha256_file(backup_path)

    site_root = os.path.join(tmp, "site")
    os.makedirs(site_root)
    with open(os.path.join(site_root, "index.html"), "w") as fh:
        fh.write("<html></html>")
    with open(os.path.join(site_root, "katalog.html"), "w") as fh:
        fh.write("<html></html>")

    run_root = os.path.join(tmp, "qa_root")
    os.makedirs(run_root, mode=0o700)

    config = {
        "required_inputs": required,
        "site_roots": {site_root: ["index.html", "katalog.html"]},
        "ua0009_url": "https://example.com/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": [],
        "db_function_source": None,
        "min_free_bytes": 1024,
    }
    return config, tmp


class FullExtendedOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_full_extended_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot(self):
        snap = {}
        for p in self.cfg["required_inputs"]:
            with open(p, "rb") as fh:
                snap[p] = fh.read()
        return snap

    def test_extended_available_and_eight_artifacts_written_originals_unchanged(self):
        before = self._snapshot()
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        after = self._snapshot()
        self.assertEqual(before, after)

        self.assertTrue(receipt["extended_candidates"]["available"], receipt["extended_candidates"])
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        candidates_dir = os.path.join(run_dir, "candidates")
        diffs_dir = os.path.join(run_dir, "diffs")
        expected_names = {
            "usercustomize_py310.py", "usercustomize_py313.py", "start_safe.py",
            "run_all.py", "avtoperedacha.py", "samokontrol.py", "crm_speed_runtime.py",
        }
        actual_names = set(os.listdir(candidates_dir))
        self.assertTrue(expected_names.issubset(actual_names))
        diff_names = set(os.listdir(diffs_dir))
        for name in expected_names:
            self.assertIn(name + ".diff", diff_names)

        self.assertEqual(
            set(receipt["extended_candidates"]["candidate_hashes"].keys()) - {"cars_ui.py"},
            expected_names - set(),
        )
        self.assertIn("crm_speed_runtime.py", receipt["extended_candidates"]["candidate_hashes"])
        self.assertIsNotNone(receipt["extended_candidates"]["support_module_sha256"])

    def test_phase80_uses_candidate_strings_not_original(self):
        seen_sources = []
        original_check = gate_a.check_usercustomize_inert

        def spy(source):
            seen_sources.append(source)
            return original_check(source)

        import unittest.mock as mock
        with mock.patch.object(gate_a, "check_usercustomize_inert", spy):
            gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertTrue(seen_sources)
        for s in seen_sources:
            self.assertNotIn("team_bot", s)
            self.assertNotIn("avtoperedacha", s)

    def test_no_candidate_module_ever_imported(self):
        gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        for name in ("usercustomize_py310", "usercustomize_py313", "start_safe", "run_all",
                     "avtoperedacha", "samokontrol", "crm_speed_runtime"):
            self.assertNotIn(name, sys.modules)


# ---------------------------------------------------------------------------
# Compile sanity for files touched by this task
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in (
            "canonical_modules.py", "candidate_transforms.py", "sqlite_ownership.py",
            "crm_speed_gate_a.py", "test_task_038_real_candidates.py",
        ):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_038_real_candidates.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_041_architecture_audit.py

```python
"""Offline, deterministic executable tests for TASK 041: closing the
remaining fail-open candidate-transform defects identified by
independent audit of TASK 038 (commit
be8113a3c2bc0e1b6b5173c5fd13736332b13da2).

No network access. No PythonAnywhere paths. No /home/Carix access. Only
temporary directories and in-memory fixtures are used. Existing tests
are never modified except as explicitly authorized in
test_task_038_real_candidates.py (invalid assertion correction +
positive-fixture update).

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import candidate_transforms
import crm_speed_gate_a as gate_a
import sqlite_ownership

from test_task_038_real_candidates import (
    _make_full_extended_config, _fake_opener_404,
)


# ---------------------------------------------------------------------------
# 1. usercustomize positive allowlist (Defect: `import requests` -> OK)
# ---------------------------------------------------------------------------

class UsercustomizeAllowlistTests(unittest.TestCase):
    def test_import_requests_blocks(self):
        result = candidate_transforms.transform_usercustomize("import requests\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])

    def test_mixed_sys_team_bot_single_statement_preserves_sys_removes_team_bot(self):
        source = "import sys, team_bot\n"
        result = candidate_transforms.transform_usercustomize(source, "py310")
        self.assertEqual(result["status"], "OK")
        self.assertIn("import sys", result["candidate"])
        self.assertNotIn("team_bot", result["candidate"])

    def test_alias_and_from_import_variants(self):
        source = (
            "import team_bot as tb\n"
            "from team_bot import helper as h\n"
            "import sys as system_module\n"
        )
        result = candidate_transforms.transform_usercustomize(source, "py313")
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("team_bot", result["candidate"])
        self.assertIn("sys", result["candidate"])

    def test_dynamic_import_blocks(self):
        result = candidate_transforms.transform_usercustomize("import importlib\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_unknown_local_import_blocks(self):
        result = candidate_transforms.transform_usercustomize("import cars_ui\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_from_requests_import_get_blocks(self):
        result = candidate_transforms.transform_usercustomize("from requests import get\n", "py310")
        self.assertEqual(result["status"], "BLOCKED")

    def test_py310_and_py313_remain_distinct_and_deterministic(self):
        source = "import sys\nimport team_bot\n"
        r1 = candidate_transforms.transform_usercustomize(source, "py310")
        r2 = candidate_transforms.transform_usercustomize(source, "py313")
        self.assertEqual(r1["metadata"]["version"], "py310")
        self.assertEqual(r2["metadata"]["version"], "py313")
        for _ in range(5):
            self.assertEqual(candidate_transforms.transform_usercustomize(source, "py310"), r1)


# ---------------------------------------------------------------------------
# 2. avtoperedacha call-graph proof negatives
# ---------------------------------------------------------------------------

class RebuildCallGraphNegativeTests(unittest.TestCase):
    def test_unrelated_ffmpeg_spawn_blocks(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_video():\n"
            "    subprocess.Popen(['ffmpeg', '-i', 'in.mp4', 'out.mp4'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])

    def test_generator_with_no_in_process_call_blocks(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def handle_update():\n"
            "    subprocess.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")

    def test_nonzero_argument_generator_excluded(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page(extra):\n"
            "    return extra\n\n"
            "def call_it():\n"
            "    return generate_stranica_page(1)\n\n"
            "def handle_update():\n"
            "    subprocess.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")

    def test_aliased_subprocess_import_still_resolves(self):
        source = (
            "import subprocess as sp\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_update():\n"
            "    sp.Popen(['python3', 'stranica.py'])\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("sp.Popen", result["candidate"])

    def test_dynamic_command_construction_does_not_count_as_anchor(self):
        source = (
            "import subprocess\n\n"
            "def generate_stranica_page():\n"
            "    return 'page'\n\n"
            "def call_it():\n"
            "    return generate_stranica_page()\n\n"
            "def handle_update(cmd):\n"
            "    subprocess.Popen(cmd)\n"
        )
        result = candidate_transforms.transform_avtoperedacha_rebuild(source)
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# 3. sqlite ownership: per-handle tracking, write-SQL, branch, escape
# ---------------------------------------------------------------------------

def _get_func(source, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError("function not found")


class SqliteOwnershipHardeningTests(unittest.TestCase):
    def test_unrelated_close_never_marks_real_handle_closed(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def f(other):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    other.close()\n"
            "    time.sleep(0)\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return 1\n"
        )
        func = _get_func(source, "f")
        violations = sqlite_ownership.verify_no_live_handle_across_slow_call(func)
        self.assertTrue(violations, "unrelated close must never suppress a real violation")

    def test_real_close_before_slow_call_has_no_violation(self):
        source = (
            "import sqlite3\n"
            "import time\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    time.sleep(0)\n"
            "    return rows\n"
        )
        func = _get_func(source, "f")
        violations = sqlite_ownership.verify_no_live_handle_across_slow_call(func)
        self.assertEqual(violations, [])

    def test_multiple_connections_block_transform(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn1 = sqlite3.connect('a.db')\n"
            "    conn2 = sqlite3.connect('b.db')\n"
            "    conn1.close()\n"
            "    conn2.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_caller_owned_handle_not_touched(self):
        source = (
            "def f(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    return cur.fetchall()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_branch_in_ownership_segment_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f(flag):\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    if flag:\n"
            "        cur = conn.execute('SELECT 1')\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_cursor_escape_via_return_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    return cur\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_write_sql_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    conn.execute('INSERT INTO t VALUES (1)')\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_commit_blocks(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    conn.commit()\n"
            "    conn.close()\n"
        )
        with self.assertRaises(sqlite_ownership.AnchorNotFoundError):
            sqlite_ownership.transform_short_ownership(source, {"f"})

    def test_fetchall_materialized_into_tuple(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        candidate = sqlite_ownership.transform_short_ownership(source, {"f"})
        compile(candidate, "<c>", "exec")
        self.assertIn("tuple(rows)", candidate)

    def test_cursor_closed_before_connection_in_generated_order(self):
        source = (
            "import sqlite3\n\n"
            "def f():\n"
            "    conn = sqlite3.connect('x.db')\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    rows = cur.fetchall()\n"
            "    return rows\n"
        )
        candidate = sqlite_ownership.transform_short_ownership(source, {"f"})
        cur_idx = candidate.index("cur.close()")
        conn_idx = candidate.index("conn.close()")
        self.assertLess(cur_idx, conn_idx)


# ---------------------------------------------------------------------------
# 4. RebuildQueue callback error sanitization
# ---------------------------------------------------------------------------

class RebuildQueueSanitizationTests(unittest.TestCase):
    def test_callback_exception_message_never_stored(self):
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp(prefix="task041_sanitize_")
        try:
            def bad_callback():
                raise ValueError("secret-token-abc123-should-never-leak")

            q = canonical_modules.RebuildQueue(bad_callback, os.path.join(tmp, "r.lock"))
            q.enqueue()
            q.shutdown(timeout=3)
            self.assertTrue(any(e.startswith("CallbackError:ValueError") for e in q.errors))
            for e in q.errors:
                self.assertNotIn("secret-token", e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generated_runtime_support_also_sanitizes(self):
        source = candidate_transforms.generate_runtime_support_source()
        self.assertIn('"CallbackError:"', source)
        self.assertNotIn("str(exc)[:500]", source)


# ---------------------------------------------------------------------------
# 5. launcher transform structural correctness
# ---------------------------------------------------------------------------

class LauncherStructuralTests(unittest.TestCase):
    LOCK_PATH = "/home/Carix/qa/crm_speed_task020/launcher_singleton.lock"

    def test_future_import_preserved_before_runtime_import(self):
        source = (
            '"""doc"""\n'
            "from __future__ import annotations\n"
            "import sys\n\n"
            "def main():\n"
            "    pass\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = candidate_transforms.transform_launcher_singleton(source, self.LOCK_PATH)
        self.assertEqual(result["status"], "OK")
        tree = ast.parse(result["candidate"])
        future_idx = next(i for i, n in enumerate(tree.body)
                           if isinstance(n, ast.ImportFrom) and n.module == "__future__")
        runtime_idx = next(i for i, n in enumerate(tree.body)
                            if isinstance(n, ast.ImportFrom) and n.module == candidate_transforms.RUNTIME_MODULE_NAME)
        self.assertLess(future_idx, runtime_idx)

    def test_duplicate_start_uses_exit_code_78_and_diagnostic(self):
        source = (
            "def main():\n"
            "    pass\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = candidate_transforms.transform_launcher_singleton(source, self.LOCK_PATH)
        self.assertEqual(result["status"], "OK")
        self.assertIn("SystemExit(78)", result["candidate"])
        self.assertIn("stderr.write", result["candidate"])


# ---------------------------------------------------------------------------
# 6. orchestrator: exactly eight candidates, no legacy fallback to PASS
# ---------------------------------------------------------------------------

class OrchestratorEightCandidateTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_full_extended_config()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exactly_eight_extended_candidates_no_legacy_usercustomize(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        candidates_dir = os.path.join(run_dir, "candidates")
        names = set(os.listdir(candidates_dir))
        self.assertEqual(len(names), 8, names)
        self.assertIn("cars_ui.py", names)
        self.assertNotIn("usercustomize.py", names)

    def test_blocked_launcher_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        # Corrupt start_safe.py so its transform is structurally BLOCKED
        # (two main anchors), proving no legacy fallback can reach PASS.
        start_safe_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "start_safe.py"][0]
        with open(start_safe_path, "w") as fh:
            fh.write(
                "if __name__ == '__main__':\n    pass\n"
                "if __name__ == '__main__':\n    pass\n"
            )
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])

    def test_blocked_avtoperedacha_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        avto_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "avtoperedacha.py"][0]
        with open(avto_path, "w") as fh:
            fh.write("def helper():\n    return 1\n")
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])

    def test_blocked_sqlite_transform_never_reaches_pass(self):
        cfg = dict(self.cfg)
        samo_path = [p for p in cfg["required_inputs"] if os.path.basename(p) == "samokontrol.py"][0]
        with open(samo_path, "w") as fh:
            fh.write("def helper():\n    return 1\n")
        receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["extended_candidates"]["available"])


# ---------------------------------------------------------------------------
# Compile sanity
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in (
            "canonical_modules.py", "candidate_transforms.py", "sqlite_ownership.py",
            "crm_speed_gate_a.py", "test_task_038_real_candidates.py",
            "test_task_041_architecture_audit.py",
        ):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_041_architecture_audit.py
