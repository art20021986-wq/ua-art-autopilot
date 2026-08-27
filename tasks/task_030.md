# TASK 030 — CRM-SPEED-001 complete the real fail-closed Gate A architecture

## Owner authorization and immutable safety boundary

Continue the owner-approved CRM-SPEED-001 repair. Work only under cloud/. Claude must author all implementation changes. Do NOT execute Gate A, do NOT install candidates, and do NOT modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. No PythonAnywhere production action is authorized. The result is reviewable code only.

Required safety markers in every status/report:
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Independent controller verdict on commit 3c570c746dbd31984d765f3b9f7105958bed4a1c

Compilation passed. Full discovery passed 73/73, then passed 9 more complete runs: 730/730 total. Safe-inbox synchronization also passed. Nevertheless the package is NOT READY_FOR_GATE_A because the tests do not enforce the original architecture and several executable negative probes fail.

Executed controller probes:
- RUN_GATE_A_CRM_SPEED.py exits 0 after only printing DEFAULT_CONFIG. It does not acquire the Gate A lock, create a secured unique run, securely read bounded inputs, generate candidates/diffs, compile/verify them, re-fingerprint protected state, write manifest/receipt/report, or execute the specified 20/40/60/80/100 workflow.
- A currently live CrossProcessLock can be stolen solely because its age exceeds stale_after_seconds: first acquire=True and second simultaneous acquire=True after 0.03s with stale_after_seconds=0.01.
- RebuildQueue.enqueue() blocks for the entire callback: a 0.20s callback produced enqueue elapsed 0.201s. The admin path must return immediately.
- SafeWriter accepted an existing hard-link target instead of blocking.
- check_inputs_present_and_regular accepted a directory as a required input.
- ua0009_publication_check.check_ua0009_not_public returned ok=True for simulated network status -1 with quick_check='ok'. Network ambiguity must BLOCK.

Additional manual audit findings:
- run_gate_a currently consumes a caller-preassembled synthetic fixture and compares supplied before/after values; the real no-argument runner never constructs fresh evidence around the actual candidate workload.
- No real orchestration applies the usercustomize, start_safe, run_all, avtoperedacha, samokontrol SQLite, and cars_ui candidate transforms to securely read source copies.
- check_singleton_guard_present only tests the helper class; it does not prove start_safe.py and run_all.py candidates use it.
- check_rebuild_queue_bound_no_process_spawn only searches for imports/call names; it does not bind the existing in-process generator callback or prove one bounded queue.
- check_db_closed_before_slow_work is path-insensitive and can pass after seeing any close, even when another handle or branch remains live.
- site inventories are sampled twice adjacent to each other rather than before and after the full workload.
- the receipt lacks the complete required schema/UA-0009 evidence, candidate/diff hashes, manifest binding, synthetic latency, full deterministic records, phase progress, unexpected-write accounting, and human report.
- build_manifest and verify_gate_a do not verify the complete receipt-to-code/input/output binding.
- ua0009_publication_check.py and media_call_graph.py retain divergent duplicate logic instead of delegating to canonical implementations.
- OPERATOR_INSTRUCTIONS.md describes behavior that the launcher does not currently implement.

## Mandatory architecture correction

### 1. Real no-argument Gate A entry point

RUN_GATE_A_CRM_SPEED.py must call one public, injectable orchestration entry point that performs the complete fail-closed Gate A when later run by an explicitly authorized owner on PythonAnywhere. The no-argument production configuration uses only the exact bounded paths in the canonical specification. Tests must inject a temporary synthetic configuration and mocked HTTPS opener; tests must never access /home/Carix or the network.

The runner must:
- acquire one nonblocking exclusive Gate A lock before the workload and hold it through final evidence emission;
- create exactly one unique resolved run directory below /home/Carix/qa/crm_speed_task020 after validating the QA root;
- emit measured 20/40/60/80/100 phase records; 100 means finished, not passed;
- securely read only the fixed required inputs, reject missing/non-regular/symlink/hard-link/path-swap inputs, and never recursively scan the account;
- verify free space and the exact backup archive SHA-256 before candidate creation;
- fingerprint every protected input and all three fixed bounded site inventories before the workload, repeat them after all work, and derive zero unexpected changes from fresh measurements;
- write only inside the run directory, except the lock/guard files which must also remain under the fixed QA root;
- return GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL only when every required evidence predicate is present and OK; otherwise write a complete BLOCKED receipt/report and return nonzero;
- never import or execute production application modules, never invoke a production generator, and never install a candidate.

### 2. Real candidate generation in isolated copies

At Gate A runtime, securely read the exact original bytes and run deterministic AST/token-aware transforms. Missing or ambiguous anchors must BLOCK and leave that candidate unmodified. Write candidate files and unified diffs only in the run directory. Compile every candidate together without importing or executing it.

Required candidates/proofs:
- both usercustomize.py files: inert at import, with application/background startup effects removed and every unclassified top-level effect BLOCKED;
- start_safe.py and run_all.py: exact main anchor wrapped with the canonical singleton lifecycle, fail-fast duplicate diagnostic, release on normal return/exception/atexit/supported signals, and no import-time startup;
- avtoperedacha.py: identify exactly one distinct existing in-process stranica generation callable/call path, bind it as RebuildQueue callback without executing it in Gate A, replace process-spawn rebuild paths with immediate enqueue, and prove no subprocess/os.system/multiprocessing call remains reachable in that rebuild graph;
- cars_ui.py: use cars_ui_transform.py as the only canonical admin-media transformer for gallery, video_gallery, diag_photo_show, and diag_video_show; text-only output must preserve useful type/count/label/action information; ambiguous dispatch BLOCKS; upload/save/delete/reference and customer/public media functions remain semantically unchanged;
- avtoperedacha.py and samokontrol.py DB paths: structurally materialize selected rows into immutable ordinary values, close cursor/connection/transaction before formatting, hashing, sleep, Telegram/network calls, page generation, or filesystem work; unsupported control flow BLOCKS;
- unchanged protected inputs remain byte-identical. If a runtime support module is needed by candidates, generate a deterministic candidate support module and include it explicitly in candidate compilation, manifest, report, and any future Gate B install list. Candidates must not depend on an import path that would exist only in the cloud package.

Every transform must run at least 10 times from identical original bytes. Compare candidate bytes, unified-diff bytes, status/reason data, and metadata hashes; store all records.

### 3. Correct canonical concurrency primitives

CrossProcessLock / SingletonGuard:
- do not steal a lock from a live PID with matching process-start identity merely because it is old;
- serialize stale inspection/takeover and release with a Linux-safe atomic mechanism such as fcntl.flock on a validated guard file, then re-read owner evidence while serialized; no blind unlink TOCTOU;
- owner record includes PID, process-start identity, random token and acquisition time; only matching token may release;
- nonblocking duplicate returns immediately and never alters owner evidence;
- release and atexit are idempotent, do not recreate deleted parents, and never raise;
- deterministic multiprocess barrier test: at least 100 high-contention stale-takeover rounds, exactly one winner held until all contenders attempted; live-owner, PID-reuse/start mismatch, foreign-token, exception/cleanup cases.

RebuildQueue:
- enqueue returns promptly while slow callback runs elsewhere; use a bounded worker, never an unbounded thread/process storm;
- at most one active rebuild and at most one pending follow-up for a burst;
- use the canonical cross-process lock for the rebuild critical section;
- callback is mandatory and explicitly bound; failures are bounded and sanitized; no infinite retry/spin;
- behavioral tests measure prompt enqueue return with a slow callback and verify one active plus at most one coalesced follow-up.

### 4. Harden all I/O and evidence binding

SafeWriter must reject traversal, path escape, symlink in every parent, target symlink, non-regular target, and hard-link target; use exclusive secure temp files, no-follow semantics where available, fstat identity checks, restrictive mode, fsync file and directory, and atomic replace. It must record exact allowed writes. Tests cover symlink parent, hard-link target, target swap/replacement race, traversal, deleted parent, and insufficient free space.

Secure source reads must use no-follow/fstat checks and verify identity before/after the read. build_manifest must deterministically bind exact package-code hashes, source fingerprints, candidates, diffs, reports and receipt-relevant outputs without following symlinks. verify_gate_a must fail closed if any bound hash/predicate/status/write target is missing or altered.

### 5. SQLite, UA-0009 and publication proof

- open crm.db read-only by URI with query_only enabled and short timeout; require PRAGMA quick_check exactly 'ok'; lock/error is BLOCKED;
- perform bounded schema introspection and find/canonically serialize all UA-0009 rows without emitting PII; store only bounded structural identifiers and hashes needed for before/after equality; missing/ambiguous/overflow evidence BLOCKS;
- compare the UA-0009 evidence hash before and after the full workload;
- one canonical no-redirect HTTPS publication probe shared by every module/API; only actual HTTP 404 or 410 passes. Missing/malformed/non-HTTPS URL, 2xx, 3xx, 5xx, DNS/TLS/timeout/refused/proxy/network error all BLOCK;
- all three bounded site inventories are compared before and after the full workload.

### 6. Complete measured receipt

Receipt/report must include task ID, timestamps, phases, package hash manifest, secure source fingerprints, candidate/diff hashes, compilation results, every deterministic repetition, concurrency/structural proofs, read-only SQLite quick_check and UA-0009 hash evidence without PII, no-redirect probe, before/after site inventories, synthetic admin latency p95 with explicit NON-PRODUCTION label and target <=2.0s, unexpected changes/writes, blockers, next safe action, PRODUCTION_WRITE: NO, and final status.

No predicate may pass from a hard-coded boolean, caller-supplied after snapshot, adjacent before/after scan, self-referential static-presence assertion, or missing evidence. Final evaluation must enumerate a fixed required predicate set and treat every absent/non-OK item as BLOCKED.

### 7. Tests, compatibility and truthful docs

- Preserve the public APIs used by the existing 73 tests unless a stricter fail-closed result is required; do not delete, skip, rename, weaken, or rewrite existing passing test semantics merely to obtain green.
- Add a new architecture/end-to-end test module. A clean fully synthetic temporary fixture must exercise the same public orchestration entry point used by the no-argument launcher and reach GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL while leaving the complete original fixture tree byte-identical.
- Independently mutate/fail every mandatory evidence input and prove BLOCKED/nonzero.
- Add executable regressions for every controller probe listed above, including proving the launcher invokes orchestration rather than only printing configuration.
- All tests are offline, bounded, deterministic, and must not read/write /home/Carix or perform network calls.
- Target controller command: python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'.
- Update OPERATOR_INSTRUCTIONS.md, TEST_MATRIX.md, ROLLBACK.md, cloud_report_020.md, cloud/latest_status.md and cloud/owner_reply.md so claims exactly match executable behavior.
- Claude final status is READY_FOR_CONTROLLER_REVIEW only if the code is complete for controller execution; otherwise BLOCKED with exact unresolved items. Do not claim Gate A passed, Production accelerated, or CRM changed.

## Output rules

Implement the corrections, not only reports/tests/status. All implementation files must be mutually consistent and Claude-authored. Work only under cloud/. Do not execute Gate A. Do not access PythonAnywhere. Do not alter tasks/. Return a precise report of files and remaining blockers.

## Full canonical CRM-SPEED-001 specification

# TASK 020 CRM SPEED — Claude-authored optimization, Gate A only

## Owner goal

The owner approved starting CRM optimization. The administrative Telegram CRM must become fast and text-first. Car photos and videos must stop appearing automatically inside the administrator CRM, while media storage, upload/removal, the public site, and customer-facing media must remain available.

Claude must author every implementation file listed in Deliverables. ChatGPT will independently review the result before anything can be installed.

## Authority boundary

This task authorizes creation of reviewable code under cloud/ and a fail-closed Gate A runner only.

It does not authorize:

- modifying any live Python file under /home/Carix;
- modifying /home/Carix/crm.db or any other database;
- restarting the bot, web app, scheduled task, worker, or PythonAnywhere process;
- writing into /home/Carix/site, /home/Carix/video, public_html, or any production/media tree;
- publishing UA-0009;
- installing the candidate into production.

The Gate A runner may read bounded live inputs and may write only beneath /home/Carix/qa/crm_speed_task020. It must make patched candidate copies there. Any production installation is a separate Gate B decision after independent review and explicit owner approval.

## Confirmed incident evidence

Use these facts as requirements, not as permission to alter production:

1. Fresh CRM logs showed BlockingIOError(11, 'Resource temporarily unavailable') from avtoperedacha and SQLite database is locked with waits of about 30 seconds.
2. A DB connection stack included avtoperedacha.py:46 kolonki_cars -> :79 otpechatok -> :188 shag and held work for about 21.7 seconds.
3. Another long read included samokontrol.py:123 kolonki -> :140 proverit_bazu.
4. avtoperedacha.py has both in-process stranica generation around lines 145/149 and subprocess-based generation around line 169.
5. usercustomize.py in Python 3.10 and 3.13 site-packages automatically imports CRM/background modules into every Python process. This can duplicate workers when any Python subprocess starts.
6. cars_ui.py contains administrator media display routes/functions gallery, video_gallery, diag_photo_show, and diag_video_show using reply_photo/reply_video or equivalent media sending.
7. A safety backup already exists:
   - /home/Carix/backups/crm_speed_20260827_1038_crm.db
   - /home/Carix/backups/crm_speed_20260827_1038_before.tar.gz
   - archive SHA-256 b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913
8. Current production site is working and must remain unchanged during Gate A.
9. UA-0009 must remain unchanged and unpublished.

## Bounded live input candidates

The Gate A runner must resolve these exact candidates without recursive account scanning. Missing required inputs must produce BLOCKED, not guessed code:

- /home/Carix/.local/lib/python3.10/site-packages/usercustomize.py
- /home/Carix/.local/lib/python3.13/site-packages/usercustomize.py
- /home/Carix/start_safe.py
- /home/Carix/run_all.py
- /home/Carix/cars_ui.py
- /home/Carix/avtoperedacha.py
- /home/Carix/samokontrol.py
- /home/Carix/db.py
- /home/Carix/team_bot.py
- /home/Carix/stranica.py
- /home/Carix/crm.db

Optional bounded supporting inputs may include /home/Carix/yadro.py and /home/Carix/master_card.py if present. Do not recursively scan /home/Carix. Reject symlinks for every required input. Record canonical paths, size, mode, mtime_ns, and SHA-256 before any transformation.

## Candidate behavior to implement in isolated copies

### A. Stop duplicate background runtimes

For each usercustomize.py candidate:

- remove unconditional application/background imports and thread/process startup;
- retain only harmless interpreter customization, if any;
- make default behavior inert;
- never import team_bot, run_all, start_safe, avtoperedacha, stranica, or other CRM worker/generator modules merely because a Python interpreter started.

For start_safe.py and run_all.py candidates:

- establish one explicit process entry point;
- use an atomic non-blocking singleton lock with PID/start-time evidence and safe stale-lock handling;
- never kill unrelated processes;
- avoid import-time side effects;
- provide clean shutdown and lock release;
- duplicate starts must exit quickly with a clear diagnostic.

### B. Debounce and serialize rebuilds without subprocess storms

For avtoperedacha.py candidate:

- remove all subprocess, os.system, multiprocessing, and shell-based stranica rebuild execution;
- make generation an explicit in-process call, never triggered by import;
- implement one bounded coalescing/debounce queue so a burst collapses into at most one pending follow-up rebuild;
- use an atomic cross-process lock so two bot processes cannot rebuild concurrently;
- return to the Telegram handler immediately after enqueueing;
- log bounded success/failure/duration without secrets;
- do not retry forever or spin;
- never hold a SQLite connection, cursor, transaction, or DB lock during HTML generation, hashing, sleeping, Telegram I/O, or other slow work.

Preserve current public generator behavior and paths. Gate A must not invoke the generator against production or write public HTML.

### C. Short SQLite ownership

For avtoperedacha.py and samokontrol.py candidates:

- execute bounded SELECT work and materialize rows into ordinary immutable Python values;
- close cursor/connection immediately via context management/finally;
- format, compare, call Telegram, generate pages, wait, and perform filesystem work only after DB close;
- use a short explicit busy timeout appropriate for interactive reads;
- never begin an unnecessary write transaction;
- preserve query semantics;
- fast-fail with an actionable admin message rather than block for 30 seconds.

Do not make schema migrations, WAL changes, VACUUM, REINDEX, or mutable PRAGMA changes.

### D. Administrator CRM is text-only

In cars_ui.py candidate, change only administrator display behavior for gallery, video_gallery, diag_photo_show, and diag_video_show plus directly related admin navigation helpers:

- no reply_photo, reply_video, send_photo, send_video, media group, binary download, thumbnail fetch, or automatic media preview;
- reply with concise text: media type, count, optional filenames/labels, and text buttons/actions;
- preserve upload, attach, save, delete, metadata, DB references, website/public-card rendering, and customer-facing media;
- do not delete media or database values;
- do not globally disable Telegram media APIs;
- do not change unrelated commands.

Static analysis must prove those four admin routes have no reachable automatic media-send call. Tests must prove media persistence/removal methods remain present and are not stubbed.

### E. Import safety

Candidates must avoid network, DB, process, thread, or filesystem mutation on import; use bounded logging; avoid secrets/customer data in logs; compile on live Python; and preserve compatible callable names where possible.

## Fail-closed Gate A workflow

The no-argument launcher must be safe to repeat and implement:

1. 20% preflight: exclusive Gate A lock, bounded inputs, symlink rejection, free space, source/protected fingerprints.
2. 40% snapshot and candidate transform only in a unique directory below /home/Carix/qa/crm_speed_task020.
3. 60% compile every candidate and run static/unit tests without importing/executing live modules.
4. 80% prove text-only admin routes, singleton rejection, debounce coalescing, DB close before simulated slow work, no process spawning, and deterministic repeat.
5. 100% re-fingerprint production inputs, DB evidence, public-card evidence, and bounded production inventories; emit receipt.

Centralize all writes through a safe writer that only permits regular files inside the resolved per-run QA directory, rejects traversal/symlinks/hard-link surprises/path escapes, uses atomic writes, never imports application modules, and never executes copied generators.

Use AST/token-aware transformations with explicit structural anchors and expected match counts. Do not broadly regex-rewrite Python. Missing or ambiguous anchors are BLOCKED and must leave that candidate unmodified. Include unified diffs.

## Required validation

Gate A passes only if every item passes:

- required inputs are regular non-symlink files;
- backup archive exists and has the known SHA-256;
- every candidate compiles;
- no production source, DB, site, or media file is written;
- every protected source and crm.db fingerprint before/after is identical;
- SQLite inspection is read-only with query_only enabled;
- quick_check is ok, or a transient lock is BLOCKED without mutation;
- bounded schema introspection finds all UA-0009 rows, canonically serializes non-PII evidence, and fingerprints before/after;
- UA-0009 fingerprint is identical;
- explicit publication evidence proves unpublished and a no-redirect HTTP check proves the public card is not served; ambiguity is BLOCKED;
- bounded production page/site inventories are unchanged;
- four admin media routes have no reachable automatic media send;
- media upload/save/delete/reference behavior remains;
- usercustomize has no default application startup;
- start_safe/run_all have singleton guard and no import startup;
- avtoperedacha has no process spawn and has one bounded rebuild queue;
- DB handles close before simulated slow work;
- at least 10 deterministic repetitions pass;
- repeated transform is byte-identical;
- test duration and synthetic admin latency are recorded, with synthetic p95 target <= 2.0s and clearly not claimed as production measurement;
- unexpected protected changes is zero.

A 100% marker means finished, not passed. Runtime final status must be GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL or BLOCKED. Never claim deployed or production fixed.

## Evidence

Write machine-readable JSON receipt and human-readable Markdown report in the isolated run directory with task/timestamps, exact hashes, diff hashes, tests/repetitions/durations, synthetic latency, UA-0009 fingerprint/unpublished evidence without PII, before/after protected evidence, unexpected changes, blockers, next safe action, and PRODUCTION_WRITE: NO. Return nonzero on BLOCKED. Use standard library where practical and support one no-argument PythonAnywhere Bash command.

## Deliverables

Claude must create every file with complete content:

- `cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py`
- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/build_manifest.py`
- `cloud/crm_speed_optimization/verify_gate_a.py`
- `cloud/crm_speed_optimization/test_crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/TEST_MATRIX.md`
- `cloud/crm_speed_optimization/OPERATOR_INSTRUCTIONS.md`
- `cloud/crm_speed_optimization/ROLLBACK.md`
- `cloud/crm_speed_optimization/cloud_report_020.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Python files must be mutually consistent, compile, and contain no placeholders, TODO-only implementations, credentials, private DB data, or production-write capability.

cloud/latest_status.md must state READY_FOR_GATE_A only if Claude's static checks pass; otherwise BLOCKED. cloud/owner_reply.md must explain in Russian that Claude authored the candidate, production is untouched, what Gate A will do, and that installation requires review and separate owner approval.


## Exact current source snapshots from commit 3c570c746dbd31984d765f3b9f7105958bed4a1c

These are the complete current sources available to the worker. Rewrite them as needed while preserving non-weakened tests and canonical identity.

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py

```python
#!/usr/bin/env python3
"""No-argument Gate A launcher artifact.

IMPORTANT: This script is delivered for independent controller/owner
execution on PythonAnywhere ONLY, after review and explicit approval. It is
NEVER executed automatically by Claude/Cloud or by this repository's own
automation. Running this file is a separate, owner-approved action outside
the scope of any cloud/ task.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import DEFAULT_CONFIG  # noqa: E402


def main():
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(DEFAULT_CONFIG["run_root"], run_id)
    print("This launcher is a delivered artifact for controller/owner-run execution only.")
    print("Claude/Cloud automation does not execute Gate A against production.")
    print(json.dumps({"planned_run_dir": run_dir, "config": DEFAULT_CONFIG}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

```python
"""Canonical implementations shared by the launcher, orchestrator, and
tests for CRM-SPEED-001. This module is the SINGLE source of truth for
CrossProcessLock, SingletonGuard, RebuildQueue, and SafeWriter.

crm_speed_gate_a.py MUST import these classes directly. It must never
redefine or shadow them. cross_process_lock.py, rebuild_queue.py, and
safe_writer.py are thin re-export modules kept only for backward-compatible
imports; they contain no logic of their own.
"""
import os
import time
import uuid
import atexit
import tempfile
import threading


def _process_start_time(pid):
    """Best-effort process start-time fingerprint using /proc (Linux).
    Returns None when unavailable; callers must treat None as unknown and
    must not use it to positively confirm liveness."""
    try:
        with open(f"/proc/{pid}/stat", "r") as fh:
            data = fh.read()
        end = data.rfind(')')
        rest = data[end + 2:].split()
        return rest[19]
    except Exception:
        return None


class LockEvidence:
    def __init__(self, pid, start_time, token, acquired_at):
        self.pid = pid
        self.start_time = start_time
        self.token = token
        self.acquired_at = acquired_at

    def to_line(self):
        return f"{self.pid}|{self.start_time}|{self.token}|{self.acquired_at}\n"

    @staticmethod
    def parse(line):
        parts = line.strip().split("|")
        if len(parts) != 4:
            return None
        pid, start_time, token, acquired_at = parts
        try:
            return LockEvidence(int(pid), start_time, token, float(acquired_at))
        except ValueError:
            return None


class CrossProcessLock:
    """Atomic, non-blocking, cross-process lock with PID + process-start
    evidence, an ownership token, safe stale takeover, and idempotent,
    exception-safe release. Never kills another process."""

    def __init__(self, path, stale_after_seconds=300):
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.token = uuid.uuid4().hex
        self._owned = False
        self._atexit_registered = False

    def _read(self):
        try:
            with open(self.path, "r") as fh:
                return LockEvidence.parse(fh.readline())
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _is_live(self, evidence):
        if evidence is None:
            return False
        try:
            os.kill(evidence.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False
        current_start = _process_start_time(evidence.pid)
        if current_start is not None and evidence.start_time not in (None, "", current_start):
            return False
        if time.time() - evidence.acquired_at > self.stale_after_seconds:
            return False
        return True

    def acquire(self):
        """Return True only if this instance now owns the lock."""
        existing = self._read()
        if existing is not None and self._is_live(existing):
            return False
        fd = None
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = self._read()
            if existing is not None and self._is_live(existing):
                return False
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return False
        evidence = LockEvidence(os.getpid(), _process_start_time(os.getpid()) or "", self.token, time.time())
        with os.fdopen(fd, "w") as fh:
            fh.write(evidence.to_line())
            fh.flush()
            os.fsync(fh.fileno())
        recheck = self._read()
        if recheck is None or recheck.token != self.token:
            return False
        self._owned = True
        if not self._atexit_registered:
            atexit.register(self.release)
            self._atexit_registered = True
        return True

    def release(self):
        if not self._owned:
            return
        try:
            current = self._read()
            if current is not None and current.token == self.token:
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
        except Exception:
            pass
        finally:
            self._owned = False


class SingletonGuard(CrossProcessLock):
    """Process singleton built directly on CrossProcessLock semantics."""
    pass


class RebuildQueue:
    """Bounded coalescing rebuild queue. At most one pending follow-up is
    kept while a rebuild is running. enqueue() returns immediately."""

    def __init__(self, callback, lock_path):
        if callback is None or not callable(callback):
            raise ValueError("RebuildQueue requires an explicit bound callable callback")
        self._callback = callback
        self._lock = CrossProcessLock(lock_path)
        self._pending = False
        self._running = False
        self._guard = threading.Lock()
        self.runs = 0
        self.coalesced = 0

    def enqueue(self):
        with self._guard:
            if self._running:
                self._pending = True
                self.coalesced += 1
                return "coalesced"
            self._pending = True
        self._drain()
        return "accepted"

    def _drain(self):
        while True:
            with self._guard:
                if not self._pending or self._running:
                    return
                self._pending = False
                self._running = True
            acquired = self._lock.acquire()
            try:
                if acquired:
                    self._callback()
                    self.runs += 1
            finally:
                with self._guard:
                    self._running = False
                if acquired:
                    self._lock.release()


class SafeWriter:
    """Writes only regular files inside a resolved run directory. Rejects
    traversal/symlink surprises and writes atomically with fsync."""

    def __init__(self, run_dir):
        self.run_dir = os.path.realpath(run_dir)
        os.makedirs(self.run_dir, exist_ok=True)

    def _resolve(self, relative_path):
        target = os.path.realpath(os.path.join(self.run_dir, relative_path))
        if not (target == self.run_dir or target.startswith(self.run_dir + os.sep)):
            raise ValueError("path escapes run directory")
        return target

    def write_text(self, relative_path, content):
        target = self._resolve(relative_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target))
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
        dir_fd = os.open(os.path.dirname(target), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            os.close(dir_fd)
        return target

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
"""CRM-SPEED-001 Gate A orchestration logic (TASK 029 canonical integration).

This module imports canonical mechanisms from canonical_modules.py rather
than redefining them, and now also imports the canonical admin-media
transform/scanner from cars_ui_transform.py instead of redefining a
duplicate legacy transformer/scanner. scan_reachable_call_graph and
transform_cars_ui below are thin adapters around cars_ui_transform:

- scan_reachable_call_graph(source, entry_points, max_depth=25) parses
  `source`, delegates to cars_ui_transform.scan_reachable_call_graph for
  the actual reachable call-graph analysis, translates a small number of
  flag names into the historical vocabulary this module's callers and
  test suite expect (for example "dynamic_dispatch_forbidden:getattr"),
  filters out unresolved-callable flags for the small SAFE_BUILTIN_NAMES
  allowlist (len/str/int/... - matching the historical permissive
  treatment of ordinary builtins), and returns (clean, violations).
- transform_cars_ui(source, entry_points=None) first uses the adapter
  scan to decide whether any dynamic/ambiguous construct is present
  (fail closed, BLOCKED) or whether there is nothing to rewrite (OK,
  candidate=source unchanged), and only delegates the actual atomic
  media-call rewriting to cars_ui_transform.transform_cars_ui when there
  is at least one direct media call and no dynamic violation. The
  canonical result is then translated into this module's historical
  {'candidate', 'status', 'reasons'} shape.

Gate A is never executed against production by this repository. Every
function here operates only on strings/bytes/paths explicitly supplied by
the caller (production launcher or test fixture).
"""
import os
import ast
import stat
import json
import time
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
import cars_ui_transform

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
    """Historically this module allowlisted plain builtin calls (len,
    str, sorted, ...) as not being dynamic-dispatch violations. The
    canonical cars_ui_transform scanner is stricter (it flags every call
    that does not resolve to a module-level function or getattr as an
    unresolved_callable, including ordinary builtins), so this adapter
    filters that specific, narrow, pre-approved allowlist back out when
    translating canonical flags into this module's violation list."""
    if flag.startswith("unresolved_callable:"):
        parts = flag.split(":")
        name = parts[1] if len(parts) > 1 else ""
        return name in SAFE_BUILTIN_NAMES
    return False


def _translate_dynamic_flag(flag):
    """Translate a small number of canonical flag names into the
    historical vocabulary this module's callers/tests expect."""
    if flag.startswith("getattr_dispatch"):
        return "dynamic_dispatch_forbidden:getattr"
    return flag


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    """Thin adapter: parses `source` and delegates the reachable
    call-graph analysis to cars_ui_transform.scan_reachable_call_graph.
    Returns (clean, violations) exactly as the historical API did.
    `max_depth` is accepted for backward API compatibility; the
    canonical scanner bounds recursion via its own visited-set closure
    and does not require an explicit depth cap for the fixtures used by
    this package.
    """
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
    """Thin adapter around cars_ui_transform.transform_cars_ui.

    Fails closed exactly as the historical API did:
    - if the original reachable call graph (via the adapter scan above)
      contains any dynamic/ambiguous construct, the candidate is None
      and status is BLOCKED;
    - if there are no violations at all (no dynamic issues and no direct
      media calls), the entry points are already text-only and the
      original source is returned unchanged with status OK;
    - otherwise (only direct_media_call violations present, no dynamic
      flags) the actual atomic media-call rewrite is delegated to
      cars_ui_transform.transform_cars_ui, and the canonical result is
      translated into this module's {'candidate','status','reasons'}
      shape. The transformed graph is re-scanned; any remaining
      violation also yields candidate None / BLOCKED.
    """
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


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat, one explicit signature
# ---------------------------------------------------------------------------

def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    """Run transform_fn(source, *args) `repeats` times from the exact same
    original source and compare candidate bytes, unified-diff bytes,
    status, reason list, and a metadata digest across all repetitions.
    transform_fn must return a dict with keys 'candidate', 'status',
    'reasons'. Returns a dict with 'deterministic' (bool), 'repeats', and
    the full list of per-repetition records."""
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


# ---------------------------------------------------------------------------
# Correction C: bounded site/public inventory with test-only max override
# ---------------------------------------------------------------------------

def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    """Non-recursive bounded scan of `root` for entries in `allowed_names`.
    Production callers must use the default max_files_per_root=32. Tests
    may pass a smaller value explicitly to construct real overflow cases
    without lowering the production default."""
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


# ---------------------------------------------------------------------------
# Publication probe -- fails closed on every network ambiguity
# ---------------------------------------------------------------------------

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
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


# ---------------------------------------------------------------------------
# Remaining Gate A predicate checks (evidence-derived, no fabricated True)
# ---------------------------------------------------------------------------

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
    for name, (fn, source, args) in transform_map.items():
        measurement = measure_deterministic_repeat(fn, source, args=args, repeats=10)
        if not measurement["deterministic"]:
            failures.append(name)
    if failures:
        return {"status": "BLOCKED", "failures": failures}
    return {"status": "OK", "checked": list(transform_map.keys())}


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


def evaluate_gate_a(evidence):
    """Derive final status only from measured evidence. No predicate may
    default to True. Missing/failed evidence -> BLOCKED."""
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


def run_gate_a(fixture):
    """Single, real, executable orchestration entry point. `fixture` supplies
    every bounded input needed for one full Gate A evaluation (production
    launcher builds it from DEFAULT_CONFIG bound to real /home/Carix paths;
    tests pass a synthetic fixture). This repository never invokes this
    function against production; GATE_A_EXECUTED remains NO for every task
    delivered under cloud/."""
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

    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "generated_at": time.time(),
    }
    if fixture.get("run_dir"):
        writer = SafeWriter(fixture["run_dir"])
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py

```python
'''
CRM-SPEED-001 admin-media transform utilities.

Rewrites direct Telegram media-send calls (reply_photo, reply_video,
send_photo, send_video, reply_document, send_document,
reply_media_group, send_media_group) that are structurally direct and
reachable only from the fixed admin "cars UI" entry routes into
lightweight text-only replies.

Correction applied under TASK 027 (root cause from controller run on
commit 6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e):

The previous pre-scan descended into the argument subtree of an
already-recognized direct media-send call and separately reported the
media arguments (for example open('x.jpg','rb')) as an
unresolved_callable, which made transform_cars_ui BLOCK before the
whole media-send expression could be atomically replaced. This module
now treats a structurally direct media-send call as a single atomic
unit: its target/callee shape is inspected and blocked if dynamic, but
calls strictly inside its own argument subtree are not treated as
independently reachable runtime once the whole expression is replaced,
unless they are not on the small safe-to-drop allowlist
(open/download/thumbnail), in which case the whole call is left
unrewritten and blocked to avoid silently discarding side effects.

Any open()/download() call located outside such a removed expression is
still treated as a normal unresolved call and still blocks, exactly as
before this correction.

TASK 029: this module is the single canonical admin-media transform
implementation for CRM-SPEED-001. crm_speed_gate_a.py delegates to this
module via thin adapters instead of redefining transform/scan logic.
'''

import ast
import copy
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

MEDIA_METHODS = {
    'reply_photo',
    'reply_video',
    'send_photo',
    'send_video',
    'reply_document',
    'send_document',
    'reply_media_group',
    'send_media_group',
}

_TEXT_METHOD_MAP = {
    'reply_photo': 'reply_text',
    'reply_video': 'reply_text',
    'reply_document': 'reply_text',
    'reply_media_group': 'reply_text',
    'send_photo': 'send_message',
    'send_video': 'send_message',
    'send_document': 'send_message',
    'send_media_group': 'send_message',
}

_MEDIA_KIND = {
    'reply_photo': 'photo',
    'send_photo': 'photo',
    'reply_video': 'video',
    'send_video': 'video',
    'reply_document': 'document',
    'send_document': 'document',
    'reply_media_group': 'media group',
    'send_media_group': 'media group',
}

_SAFE_ARG_CALL_PATTERNS = ('open', 'download', 'thumbnail')

DEFAULT_ADMIN_ENTRY_ROUTES = (
    'admin_car_view',
    'admin_car_list',
    'admin_car_edit',
    'admin_car_delete',
)


@dataclass
class MediaCallInfo:
    func_name: str
    node: ast.Call
    stmt: ast.stmt
    method: str
    is_await: bool
    lineno: int


@dataclass
class ScanResult:
    call_graph: Dict[str, Set[str]]
    reverse_callers: Dict[str, Set[str]]
    reachable: Set[str]
    direct_media_calls: Dict[str, List[MediaCallInfo]]
    unresolved_dynamic: Dict[str, List[str]]
    functions: Dict[str, ast.AST]


def _is_static_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute):
        return _is_static_receiver(node.value)
    return False


def _is_direct_attribute_call(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and _is_static_receiver(func.value):
        return func.attr
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return '<unknown>'


def _is_safe_media_arg_call(node: ast.Call) -> bool:
    name = _call_name(node).lower()
    return any(pattern in name for pattern in _SAFE_ARG_CALL_PATTERNS)


def _find_unsafe_arg_calls(call_node: ast.Call) -> List[str]:
    unsafe = []
    exprs = list(call_node.args) + [kw.value for kw in call_node.keywords]
    for expr in exprs:
        for sub in ast.walk(expr):
            if isinstance(sub, ast.Call) and not _is_safe_media_arg_call(sub):
                unsafe.append(_call_name(sub))
    return unsafe


class _FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self, func_name: str, module_func_names: Set[str]):
        self.func_name = func_name
        self.module_func_names = module_func_names
        self.callees: Set[str] = set()
        self.direct_media_calls: List[MediaCallInfo] = []
        self.dynamic_flags: List[str] = []
        self._consumed_attrs: Set[int] = set()

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS:
                unsafe = _find_unsafe_arg_calls(call_node)
                if unsafe:
                    self.dynamic_flags.append(
                        'unsafe_media_argument_side_effect:%s:line%s'
                        % (','.join(unsafe), node.lineno)
                    )
                    self.generic_visit(node)
                    return
                self.direct_media_calls.append(
                    MediaCallInfo(
                        func_name=self.func_name,
                        node=call_node,
                        stmt=node,
                        method=method,
                        is_await=is_await,
                        lineno=node.lineno,
                    )
                )
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            if func.id == 'getattr':
                self.dynamic_flags.append('getattr_dispatch:line%s' % node.lineno)
            elif func.id in self.module_func_names:
                self.callees.add(func.id)
            else:
                self.dynamic_flags.append(
                    'unresolved_callable:%s:line%s' % (func.id, node.lineno)
                )
        elif isinstance(func, ast.Attribute):
            self._consumed_attrs.add(id(func))
            if _is_static_receiver(func.value):
                if func.attr in MEDIA_METHODS:
                    self.dynamic_flags.append(
                        'non_atomic_media_use:%s:line%s' % (func.attr, node.lineno)
                    )
            else:
                self.dynamic_flags.append(
                    'dynamic_attribute_receiver:line%s' % node.lineno
                )
        elif isinstance(func, ast.Subscript):
            self.dynamic_flags.append('subscript_dispatch:line%s' % node.lineno)
        elif isinstance(func, ast.Call):
            self.dynamic_flags.append('computed_call_target:line%s' % node.lineno)
        elif isinstance(func, ast.Lambda):
            self.dynamic_flags.append('lambda_dispatch:line%s' % node.lineno)

        self.visit(func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def visit_Attribute(self, node: ast.Attribute):
        if id(node) not in self._consumed_attrs and node.attr in MEDIA_METHODS:
            self.dynamic_flags.append(
                'attribute_alias_reference:%s:line%s' % (node.attr, node.lineno)
            )
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda):
        self.dynamic_flags.append('lambda_present:line%s' % node.lineno)
        self.generic_visit(node)


def scan_reachable_call_graph(tree: ast.AST, entry_points) -> ScanResult:
    module_funcs: Dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_funcs[node.name] = node
    module_func_names = set(module_funcs.keys())

    call_graph: Dict[str, Set[str]] = {}
    direct_media_calls: Dict[str, List[MediaCallInfo]] = {}
    dynamic_flags: Dict[str, List[str]] = {}

    for name, fn in module_funcs.items():
        analyzer = _FunctionAnalyzer(name, module_func_names)
        for stmt in fn.body:
            analyzer.visit(stmt)
        call_graph[name] = analyzer.callees
        direct_media_calls[name] = analyzer.direct_media_calls
        dynamic_flags[name] = analyzer.dynamic_flags

    reverse_callers: Dict[str, Set[str]] = {name: set() for name in module_func_names}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in reverse_callers:
                reverse_callers[callee].add(caller)

    reachable: Set[str] = set()
    frontier = [e for e in entry_points if e in module_func_names]
    reachable.update(frontier)
    while frontier:
        nxt = []
        for f in frontier:
            for callee in call_graph.get(f, ()):
                if callee not in reachable:
                    reachable.add(callee)
                    nxt.append(callee)
        frontier = nxt

    return ScanResult(
        call_graph=call_graph,
        reverse_callers=reverse_callers,
        reachable=reachable,
        direct_media_calls=direct_media_calls,
        unresolved_dynamic=dynamic_flags,
        functions=module_funcs,
    )


def _build_text_replacement(node: ast.Expr, call_node: ast.Call, method: str, is_await: bool) -> ast.Expr:
    kind = _MEDIA_KIND[method]
    text_method = _TEXT_METHOD_MAP[method]

    if method.endswith('media_group'):
        count = None
        for arg in call_node.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                count = len(arg.elts)
                break
        count_text = str(count) if count is not None else 'multiple'
        message_text = '[%s: %s item(s) - media send disabled in admin fast mode]' % (kind, count_text)
    else:
        message_text = '[%s - media send disabled in admin fast mode]' % kind

    new_args = []
    new_keywords = []
    if text_method == 'send_message':
        if call_node.args:
            new_args.append(call_node.args[0])
        for kw in call_node.keywords:
            if kw.arg == 'chat_id':
                new_keywords.append(kw)

    new_args.append(ast.Constant(value=message_text))

    new_call = ast.Call(
        func=ast.Attribute(
            value=copy.deepcopy(call_node.func.value),
            attr=text_method,
            ctx=ast.Load(),
        ),
        args=new_args,
        keywords=new_keywords,
    )
    value = new_call
    if is_await:
        value = ast.Await(value=new_call)
    new_expr = ast.Expr(value=value)
    ast.copy_location(new_expr, node)
    ast.fix_missing_locations(new_expr)
    return new_expr


class _MediaCallTextTransformer(ast.NodeTransformer):
    '''Replaces exactly one atomic direct media-send expression per Expr
    statement with a text-only equivalent, without evaluating original
    media arguments (open/download/thumbnail/binary operations).'''

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS and not _find_unsafe_arg_calls(call_node):
                return _build_text_replacement(node, call_node, method, is_await)
        return self.generic_visit(node)


def _apply_rewrites(tree: ast.Module, rewrite_targets: Set[str]) -> None:
    transformer = _MediaCallTextTransformer()
    new_body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in rewrite_targets:
            node = transformer.visit(node)
        new_body.append(node)
    tree.body = new_body
    ast.fix_missing_locations(tree)


def _semantic_hash(node: ast.AST) -> str:
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode('utf-8')).hexdigest()


def _protected_function_hashes(tree: ast.Module, exclude_names: Set[str]) -> Dict[str, str]:
    hashes = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in exclude_names:
            hashes[node.name] = _semantic_hash(node)
    return hashes


def transform_cars_ui(source: str, entry_points=None) -> Dict[str, object]:
    entry_points = list(entry_points) if entry_points is not None else list(DEFAULT_ADMIN_ENTRY_ROUTES)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {'status': 'BLOCKED', 'reason': 'syntax_error:%s' % exc, 'candidate': None}

    scan = scan_reachable_call_graph(tree, entry_points)

    missing = [e for e in entry_points if e not in scan.functions]
    if missing:
        return {
            'status': 'BLOCKED',
            'reason': 'missing_entry_points:%s' % sorted(missing),
            'candidate': None,
        }

    rewrite_targets: Set[str] = set()
    block_reasons: List[str] = []

    for func_name in sorted(scan.reachable):
        flags = scan.unresolved_dynamic.get(func_name, [])
        if flags:
            block_reasons.append('%s: %s' % (func_name, flags))
            continue
        media_calls = scan.direct_media_calls.get(func_name, [])
        if not media_calls:
            continue
        if func_name in entry_points:
            rewrite_targets.add(func_name)
            continue
        callers = scan.reverse_callers.get(func_name, set())
        outside_callers = callers - scan.reachable
        if outside_callers:
            block_reasons.append(
                '%s: shared_helper_called_by:%s' % (func_name, sorted(outside_callers))
            )
            continue
        rewrite_targets.add(func_name)

    if block_reasons:
        return {'status': 'BLOCKED', 'reason': '; '.join(block_reasons), 'candidate': None}

    if not rewrite_targets:
        return {
            'status': 'BLOCKED',
            'reason': 'no_direct_media_calls_found_to_rewrite',
            'candidate': None,
        }

    pre_hashes = _protected_function_hashes(tree, rewrite_targets)

    candidate_tree = copy.deepcopy(tree)
    _apply_rewrites(candidate_tree, rewrite_targets)

    post_hashes = _protected_function_hashes(candidate_tree, rewrite_targets)
    if pre_hashes != post_hashes:
        return {
            'status': 'BLOCKED',
            'reason': 'protected_function_hash_mismatch',
            'candidate': None,
        }

    try:
        candidate_src = ast.unparse(candidate_tree)
    except Exception as exc:
        return {'status': 'BLOCKED', 'reason': 'unparse_failed:%s' % exc, 'candidate': None}

    try:
        compile(candidate_src, '<candidate>', 'exec')
    except SyntaxError as exc:
        return {
            'status': 'BLOCKED',
            'reason': 'candidate_compile_failed:%s' % exc,
            'candidate': None,
        }

    post_tree = ast.parse(candidate_src)
    post_scan = scan_reachable_call_graph(post_tree, entry_points)
    for func_name in post_scan.reachable:
        if post_scan.direct_media_calls.get(func_name):
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_media_still_reachable:%s' % func_name,
                'candidate': None,
            }
        flags = post_scan.unresolved_dynamic.get(func_name)
        if flags:
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_dynamic_still_reachable:%s:%s' % (func_name, flags),
                'candidate': None,
            }

    return {
        'status': 'OK',
        'reason': 'rewritten',
        'candidate': candidate_src,
        'rewritten_functions': sorted(rewrite_targets),
    }

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

```python
"""
sqlite_ownership.py

Structural (AST-based) transformation and verifier enforcing short SQLite
ownership: SELECT rows are materialized into ordinary immutable values
and the cursor/connection are closed BEFORE any slow-call category
(formatting/hash/sleep/network/filesystem/Telegram I/O).

Only exact, unambiguous anchors are transformed. Anything ambiguous
raises AnchorNotFoundError so the caller can BLOCK and leave the
candidate file unmodified.
"""
from __future__ import annotations

import ast
import os
import sys
from typing import List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}


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


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) and report violations where a DB handle name (or a
    cursor derived from it) is still open -- i.e. not yet closed -- at
    the point a slow call occurs. Conservative: anything that cannot be
    proven safe is reported as a violation.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    state = {"closed": False}
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("cursor") and isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    if owner in handle_names:
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and (owner in handle_names or owner in cursor_names):
                        state["closed"] = True
                    if any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                           for s in SLOW_CALL_NAMES):
                        if not state["closed"]:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before DB handle close"
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
    guaranteed closed (via try/finally) immediately after the last
    statement referencing the DB handle, before any subsequent
    formatting/slow work. Sets a short (2s) connect timeout if none is
    given. Raises AnchorNotFoundError if a function or its DB handle
    cannot be unambiguously identified.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if not handle_names:
            raise AnchorNotFoundError(
                f"no sqlite3.connect anchor found in function {func.name}"
            )
        _ensure_short_timeout(func, handle_names)

        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            refs_handle = any(
                isinstance(n, ast.Name) and n.id in handle_names
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

        close_stmts = []
        for name in sorted(handle_names):
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

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py

```python
"""
ua0009_publication_check.py

Fail-closed publication check for UA-0009. A missing canonical URL
configuration produces BLOCKED, not SKIPPED -- no environment-variable
omission may silently pass. PRAGMA quick_check must equal exactly 'ok';
a transient lock produces BLOCKED without any mutation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONFIG_ENV_VAR = "UA0009_CANONICAL_URL"
CONFIG_FILE_CANDIDATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "ua0009_endpoint.json"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class PublicationCheckResult:
    ok: bool
    reason: str
    url: Optional[str] = None
    http_status: Optional[int] = None
    quick_check: Optional[str] = None


def resolve_canonical_url() -> Optional[str]:
    env_val = os.environ.get(CONFIG_ENV_VAR)
    if env_val:
        return env_val.strip()
    if os.path.isfile(CONFIG_FILE_CANDIDATE) and not os.path.islink(CONFIG_FILE_CANDIDATE):
        try:
            with open(CONFIG_FILE_CANDIDATE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            url = data.get("ua0009_canonical_url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        except (OSError, json.JSONDecodeError):
            return None
    return None


def probe_no_redirect(url: str, timeout: float = 5.0) -> int:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return -1


def sqlite_quick_check(db_path: str, timeout: float = 2.0) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
    try:
        conn.execute("PRAGMA query_only=1")
        cur = conn.execute("PRAGMA quick_check")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "unknown"
    except sqlite3.OperationalError as exc:
        return f"error:{exc}"
    finally:
        conn.close()


def check_ua0009_not_public(db_path: str) -> PublicationCheckResult:
    url = resolve_canonical_url()
    if not url:
        return PublicationCheckResult(
            ok=False,
            reason="BLOCKED: no configured UA0009 canonical URL "
                   f"(set {CONFIG_ENV_VAR} or {CONFIG_FILE_CANDIDATE})",
        )
    status = probe_no_redirect(url)
    not_served = status in (404, 410) or status == -1
    try:
        quick_check = sqlite_quick_check(db_path)
        quick_ok = (quick_check == "ok")
    except Exception as exc:  # pragma: no cover - defensive
        quick_check = f"error:{exc}"
        quick_ok = False

    ok = bool(not_served and quick_ok)
    reason = "ok" if ok else f"BLOCKED: status={status} quick_check={quick_check!r}"
    return PublicationCheckResult(
        ok=ok, reason=reason, url=url, http_status=status, quick_check=quick_check,
    )

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

```python
"""Builds a deterministic manifest of package code hashes and run output
hashes for one Gate A run. Read-only against the package directory; writes
only when explicitly invoked with a run directory to inspect."""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(package_dir, run_dir=None):
    manifest = {"package_files": {}, "run_outputs": {}}
    for name in sorted(os.listdir(package_dir)):
        full = os.path.join(package_dir, name)
        if name.endswith(".py") and os.path.isfile(full):
            manifest["package_files"][name] = _sha256_file(full)
    if run_dir and os.path.isdir(run_dir):
        for root, _dirs, files in os.walk(run_dir):
            for name in sorted(files):
                path = os.path.join(root, name)
                manifest["run_outputs"][os.path.relpath(path, run_dir)] = _sha256_file(path)
    return manifest


if __name__ == "__main__":
    package_dir = os.path.dirname(os.path.abspath(__file__))
    run_dir = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(build_manifest(package_dir, run_dir), indent=2))

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

```python
"""Read-only verification of a Gate A receipt. Does not execute Gate A and
does not touch production."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")


def verify_receipt(receipt_path):
    with open(receipt_path, "r") as fh:
        receipt = json.load(fh)
    if receipt.get("production_write") != "NO":
        return False, "production_write_not_declared_no"
    if receipt.get("status") not in VALID_STATUSES:
        return False, f"unexpected_status:{receipt.get('status')}"
    if receipt.get("status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL" and receipt.get("unmet_predicates"):
        return False, "pass_status_with_unmet_predicates"
    return True, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json>")
        sys.exit(2)
    ok, reason = verify_receipt(sys.argv[1])
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/media_call_graph.py

```python
"""
media_call_graph.py

Bounded, same-module reachable-call analysis proving (or disproving) that
the four administrator display routes (gallery, video_gallery,
diag_photo_show, diag_video_show) can never reach an automatic Telegram
media-send call, including through statically resolvable helpers and
simple aliases. Ambiguous dynamic dispatch that could reach a media send
is treated as BLOCKED, never as a pass.
"""
from __future__ import annotations

import ast
import hashlib
from typing import Dict, List, Set, Tuple

MEDIA_SEND_ATTRS = {
    "reply_photo", "reply_video", "reply_document", "reply_media_group",
    "reply_animation", "reply_audio", "reply_voice",
    "send_photo", "send_video", "send_document", "send_media_group",
    "send_animation", "send_audio", "send_voice",
}

DYNAMIC_DISPATCH_MARKERS = {"getattr", "eval", "exec"}

ENTRY_POINTS = ("gallery", "video_gallery", "diag_photo_show", "diag_video_show")


class MediaScanResult:
    def __init__(self):
        self.violations: Dict[str, List[str]] = {}
        self.blocked: Dict[str, str] = {}

    def is_clean(self) -> bool:
        return not self.violations and not self.blocked


def _func_defs(tree) -> Dict[str, ast.AST]:
    defs: Dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = node
    return defs


def _called_names(node) -> Set[Tuple[str, int, str]]:
    found: Set[Tuple[str, int, str]] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            func = inner.func
            lineno = getattr(inner, "lineno", 0)
            if isinstance(func, ast.Attribute) and func.attr in MEDIA_SEND_ATTRS:
                found.add(("media", lineno, func.attr))
            elif isinstance(func, ast.Name):
                if func.id in DYNAMIC_DISPATCH_MARKERS:
                    found.add(("dynamic", lineno, func.id))
                else:
                    found.add(("local", lineno, func.id))
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                found.add(("local", lineno, func.attr))
        if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Attribute):
            if inner.value.attr in MEDIA_SEND_ATTRS:
                for t in inner.targets:
                    if isinstance(t, ast.Name):
                        found.add(("media_alias", getattr(inner, "lineno", 0), t.id))
    return found


def build_call_graph(tree) -> Dict[str, Set[Tuple[str, int, str]]]:
    defs = _func_defs(tree)
    graph: Dict[str, Set[Tuple[str, int, str]]] = {}
    for name, node in defs.items():
        graph[name] = _called_names(node)
    return graph


def find_reachable_media_calls(source: str, entry_points=ENTRY_POINTS) -> MediaScanResult:
    tree = ast.parse(source)
    defs = _func_defs(tree)
    graph = build_call_graph(tree)
    result = MediaScanResult()
    alias_media_names: Set[str] = set()
    for edges in graph.values():
        for kind, _lineno, name in edges:
            if kind == "media_alias":
                alias_media_names.add(name)

    for entry in entry_points:
        if entry not in defs:
            result.blocked[entry] = "entry point not found in source"
            continue
        seen: Set[str] = set()
        stack = [entry]
        violations: List[str] = []
        blocked_reason = None
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for kind, lineno, name in graph.get(cur, set()):
                if kind in ("media", "media_alias") or name in alias_media_names:
                    violations.append(f"{cur} -> line {lineno}: media send '{name}'")
                elif kind == "dynamic":
                    blocked_reason = (
                        f"ambiguous dynamic dispatch '{name}' reachable from {cur} "
                        f"at line {lineno}; cannot prove absence of media send"
                    )
                elif kind == "local" and name in defs and name not in seen:
                    stack.append(name)
        if blocked_reason:
            result.blocked[entry] = blocked_reason
        if violations:
            result.violations[entry] = violations
    return result


def normalized_ast_dump(node) -> str:
    clone = ast.parse(ast.unparse(node)) if not isinstance(node, ast.Module) else node
    return ast.dump(clone, annotate_fields=True, include_attributes=False)


def semantic_hash(source: str, function_names) -> Dict[str, str]:
    tree = ast.parse(source)
    defs = _func_defs(tree)
    out: Dict[str, str] = {}
    for name in function_names:
        node = defs.get(name)
        if node is None:
            out[name] = "MISSING"
            continue
        dump = normalized_ast_dump(node)
        out[name] = hashlib.sha256(dump.encode("utf-8")).hexdigest()
    return out

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/media_call_graph.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cross_process_lock.py

```python
"""Thin re-export of the canonical CrossProcessLock implementation.

This module contains no logic. Historical callers/tests that import from
here receive the exact same class object as canonical_modules and
crm_speed_gate_a. Do not add logic to this file.
"""
from canonical_modules import CrossProcessLock, LockEvidence, SingletonGuard

__all__ = ["CrossProcessLock", "LockEvidence", "SingletonGuard"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cross_process_lock.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/rebuild_queue.py

```python
"""Thin re-export of the canonical RebuildQueue implementation.

This module contains no logic of its own; it exists only so historical
imports keep resolving to the exact same object used by the launcher and
orchestrator.
"""
from canonical_modules import RebuildQueue

__all__ = ["RebuildQueue"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/rebuild_queue.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/safe_writer.py

```python
"""Thin re-export of the canonical SafeWriter implementation."""
from canonical_modules import SafeWriter

__all__ = ["SafeWriter"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/safe_writer.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/singleton_guard.py

```python
"""
singleton_guard.py

Process singleton guard built on CrossProcessLock. A duplicate start
exits quickly with a defined nonzero diagnostic code and never disturbs
another process's lock. Release is guaranteed via CrossProcessLock's own
atexit registration plus signal handling installed here.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_process_lock import CrossProcessLock  # noqa: E402

DUPLICATE_START_EXIT_CODE = 78


def acquire_singleton_or_exit(lock_path: str, label: str) -> CrossProcessLock:
    lock = CrossProcessLock(lock_path, label=label)
    if not lock.try_acquire():
        sys.stderr.write(
            f"[singleton_guard] {label}: another live instance already holds "
            f"{lock_path}; refusing to start (exit {DUPLICATE_START_EXIT_CODE}).\n"
        )
        sys.exit(DUPLICATE_START_EXIT_CODE)
    lock.install_signal_handlers()
    return lock

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/singleton_guard.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py

```python
"""Offline test suite for CRM-SPEED-001 Gate A package (round 3 corrections).

Run with: python -m unittest test_crm_speed_gate_a -v
from inside cloud/crm_speed_optimization/. This suite never touches
production, /home/Carix, or PythonAnywhere.
"""
import os
import sys
import time
import uuid
import random
import sqlite3
import tempfile
import unittest
import multiprocessing
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import cross_process_lock
import rebuild_queue as rebuild_queue_module
import safe_writer as safe_writer_module
import crm_speed_gate_a as gate_a

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
from crm_speed_gate_a import (
    scan_reachable_call_graph, transform_cars_ui, measure_deterministic_repeat,
    scan_bounded_inventory, check_ua0009_not_public, evaluate_gate_a, run_gate_a,
    DEFAULT_MAX_FILES_PER_ROOT, ADMIN_ROUTE_NAMES,
)


# ---------------------------------------------------------------------------
# Identity assertions (correction D)
# ---------------------------------------------------------------------------

class IdentityTests(unittest.TestCase):
    def test_cross_process_lock_identity(self):
        self.assertIs(cross_process_lock.CrossProcessLock, canonical_modules.CrossProcessLock)
        self.assertIs(gate_a.CrossProcessLock, canonical_modules.CrossProcessLock)

    def test_rebuild_queue_identity(self):
        self.assertIs(rebuild_queue_module.RebuildQueue, canonical_modules.RebuildQueue)
        self.assertIs(gate_a.RebuildQueue, canonical_modules.RebuildQueue)

    def test_safe_writer_identity(self):
        self.assertIs(safe_writer_module.SafeWriter, canonical_modules.SafeWriter)
        self.assertIs(gate_a.SafeWriter, canonical_modules.SafeWriter)

    def test_singleton_guard_identity(self):
        self.assertIs(cross_process_lock.SingletonGuard, canonical_modules.SingletonGuard)
        self.assertIs(gate_a.SingletonGuard, canonical_modules.SingletonGuard)


# ---------------------------------------------------------------------------
# Correction A: dynamic dispatch call-graph scanner + cars_ui transform
# ---------------------------------------------------------------------------

class CarsUiTransformTests(unittest.TestCase):
    def test_dynamic_dispatch_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('x.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    pass\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(r.startswith("dynamic_dispatch_forbidden") for r in result["reasons"]))

    def test_getattr_computed_name_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    name = pick_name()\n"
            "    fn = getattr(update.message, name)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_bound_method_alias_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    sender(open('x.jpg','rb'))\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_dict_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = {'photo': update.message.reply_photo}\n"
            "    handlers['photo']()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_list_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = [update.message.reply_photo]\n"
            "    handlers[0]()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_lambda_media_call_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    f = lambda: update.message.reply_photo(open('x.jpg','rb'))\n"
            "    f()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_return_alias_blocks(self):
        source = (
            "def _pick(update):\n"
            "    return update.message.reply_photo\n"
            "def gallery(update, context):\n"
            "    fn = _pick(update)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_await_alias_blocks(self):
        source = (
            "async def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    await sender()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_helper_media_call_blocks(self):
        source = (
            "def _send(update):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def gallery(update, context):\n"
            "    _send(update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["candidate"])
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo", result["candidate"])

    def test_ambiguous_unresolved_callable_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    dispatch_table[update.kind](update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_direct_simple_media_call_transforms_cleanly(self):
        source = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('x.mp4','rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo(", result["candidate"])
        self.assertIn("reply_text", result["candidate"])


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat with agreed API
# ---------------------------------------------------------------------------

class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_passes(self):
        source = "def gallery(update, context):\n    update.message.reply_photo(1)\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source, args=(), repeats=10)
        self.assertTrue(measurement["deterministic"])
        self.assertEqual(measurement["repeats"], 10)

    def test_deterministic_transform_passes_with_source_kwarg(self):
        source = "def gallery(update, context): pass\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source=source, repeats=10)
        self.assertTrue(measurement["deterministic"])

    def _nondeterministic_random_content(self, source):
        return {"candidate": source + f"# {random.random()}", "status": "OK", "reasons": []}

    def _nondeterministic_time(self, source):
        return {"candidate": source + f"# {time.time()}", "status": "OK", "reasons": []}

    def _nondeterministic_uuid(self, source):
        return {"candidate": source + f"# {uuid.uuid4().hex}", "status": "OK", "reasons": []}

    def _nondeterministic_unordered_set(self, source):
        s = {random.randint(0, 10**9) for _ in range(5)}
        return {"candidate": source + f"# {sorted(s) if random.random() > 2 else list(s)}", "status": "OK", "reasons": []}

    def _nondeterministic_metadata(self, source):
        return {"candidate": source, "status": "OK", "reasons": [f"seen_at:{time.time()}"]}

    def test_nondeterministic_transform_blocks(self):
        source = "x = 1\n"
        variants = [
            self._nondeterministic_random_content,
            self._nondeterministic_time,
            self._nondeterministic_uuid,
            self._nondeterministic_unordered_set,
            self._nondeterministic_metadata,
        ]
        for variant in variants:
            measurement = measure_deterministic_repeat(variant, source, args=(), repeats=10)
            self.assertFalse(measurement["deterministic"], variant.__name__)
            forced_status, unmet = evaluate_gate_a({
                **{k: {"status": "OK"} for k in gate_a.REQUIRED_PREDICATES},
                "deterministic_repeat_all_transforms": {"status": "BLOCKED", "failures": [variant.__name__]},
            })
            self.assertEqual(forced_status, "BLOCKED")
            self.assertIn("deterministic_repeat_all_transforms", unmet)


# ---------------------------------------------------------------------------
# Correction C: real, honest overflow test with production default preserved
# ---------------------------------------------------------------------------

class SiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ["index.html", "katalog.html", "UA-0001.html"]:
            with open(os.path.join(self.tmp.name, name), "w") as fh:
                fh.write("<html></html>")

    def test_production_default_max_is_32(self):
        self.assertEqual(DEFAULT_MAX_FILES_PER_ROOT, 32)

    def test_overflow_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "overflow")
        self.assertEqual(result["matched_count"], 3)

    def test_exact_boundary_n_passes(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=3)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["matched_count"], 3)

    def test_boundary_n_plus_one_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")

    def test_default_production_cap_accepts_up_to_32(self):
        for i in range(2, 10):
            with open(os.path.join(self.tmp.name, f"UA-000{i}.html"), "w") as fh:
                fh.write("<html></html>")
        allowed = list(gate_a.ALLOWED_SITE_NAMES)
        result = scan_bounded_inventory(self.tmp.name, allowed)
        self.assertEqual(result["status"], "OK")
        self.assertLessEqual(result["matched_count"], 32)

    def test_missing_root_blocks(self):
        result = scan_bounded_inventory(os.path.join(self.tmp.name, "nope"), ["index.html"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_rejected(self):
        target = os.path.join(self.tmp.name, "index.html")
        link = os.path.join(self.tmp.name, "katalog.html")
        os.remove(link)
        os.symlink(target, link)
        result = scan_bounded_inventory(self.tmp.name, ["index.html", "katalog.html"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "symlink_rejected")


# ---------------------------------------------------------------------------
# Publication probe fail-closed behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code


class _FakeOpener:
    def __init__(self, raise_exc=None, response_code=None):
        self.raise_exc = raise_exc
        self.response_code = response_code

    def open(self, req, timeout=5):
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.response_code)


class PublicationProbeTests(unittest.TestCase):
    def test_404_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_410_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_200_blocks(self):
        opener = _FakeOpener(response_code=200)
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_redirect_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 302, "redir", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_network_error_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.URLError("connection refused"))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_https_blocks(self):
        result = check_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_url_blocks(self):
        result = check_ua0009_not_public("")
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# CrossProcessLock stress test (aggregate >=100 contention attempts)
# ---------------------------------------------------------------------------

def _contender_worker(lock_path, start_barrier, result_queue, hold_event):
    guard = CrossProcessLock(lock_path)
    start_barrier.wait()
    acquired = guard.acquire()
    result_queue.put((os.getpid(), acquired))
    if acquired:
        hold_event.wait(timeout=5)
        guard.release()


class CrossProcessLockStressTests(unittest.TestCase):
    def test_simultaneous_stale_takeover_only_one_wins(self):
        ctx = multiprocessing.get_context("fork") if hasattr(multiprocessing, "get_context") else multiprocessing
        rounds = 25
        contenders_per_round = 4
        for round_idx in range(rounds):
            with tempfile.TemporaryDirectory() as tmp:
                lock_path = os.path.join(tmp, "test.lock")
                with open(lock_path, "w") as fh:
                    fh.write(f"999999|stale|deadtoken|{time.time() - 100000}\n")
                start_barrier = ctx.Barrier(contenders_per_round)
                result_queue = ctx.Queue()
                hold_event = ctx.Event()
                procs = [
                    ctx.Process(target=_contender_worker, args=(lock_path, start_barrier, result_queue, hold_event))
                    for _ in range(contenders_per_round)
                ]
                for p in procs:
                    p.start()
                results = [result_queue.get(timeout=10) for _ in procs]
                hold_event.set()
                for p in procs:
                    p.join(timeout=10)
                winners = [r for r in results if r[1]]
                self.assertEqual(len(winners), 1, f"round {round_idx}: {results}")

    def test_release_then_fresh_contender_can_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            first = CrossProcessLock(lock_path)
            self.assertTrue(first.acquire())
            first.release()
            second = CrossProcessLock(lock_path)
            self.assertTrue(second.acquire())
            second.release()

    def test_idempotent_release_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            lock = CrossProcessLock(lock_path)
            self.assertTrue(lock.acquire())
            lock.release()
            lock.release()

    def test_release_after_directory_removed_does_not_raise(self):
        tmp = tempfile.mkdtemp()
        lock_path = os.path.join(tmp, "test.lock")
        lock = CrossProcessLock(lock_path)
        self.assertTrue(lock.acquire())
        import shutil
        shutil.rmtree(tmp)
        lock.release()


# ---------------------------------------------------------------------------
# RebuildQueue and SafeWriter basic behavior
# ---------------------------------------------------------------------------

class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_one_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            q = RebuildQueue(lambda: calls.append(1), os.path.join(tmp, "rebuild.lock"))
            statuses = [q.enqueue() for _ in range(5)]
            self.assertIn("accepted", statuses)
            self.assertGreaterEqual(len(calls), 1)

    def test_requires_bound_callback(self):
        with self.assertRaises(ValueError):
            RebuildQueue(None, "/tmp/whatever.lock")


class SafeWriterTests(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            with self.assertRaises(ValueError):
                writer.write_text("../escape.txt", "x")

    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            target = writer.write_text("out.txt", "hello")
            with open(target) as fh:
                self.assertEqual(fh.read(), "hello")


# ---------------------------------------------------------------------------
# Correction E: real synthetic end-to-end Gate A
# ---------------------------------------------------------------------------

CLEAN_CARS_UI = (
    "def gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'photos: {count}')\n"
    "def video_gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'videos: {count}')\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_text('diag photo text')\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_text('diag video text')\n"
    "def count_media(update):\n"
    "    return len(update.media)\n"
    "def upload_media(path, data):\n"
    "    with open(path, 'wb') as fh:\n"
    "        fh.write(data)\n"
    "    return True\n"
    "def delete_media(path):\n"
    "    import os as _os\n"
    "    _os.remove(path)\n"
    "    return True\n"
)

CLEAN_USERCUSTOMIZE = "import sys\n\n\ndef _noop():\n    return None\n"

CLEAN_AVTOPEREDACHA = (
    "import sqlite3\n"
    "import time\n"
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

DB_FUNCTION_SOURCE = (
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)


class EndToEndGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.required_input_paths = []
        for name in ["usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
                     "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py"]:
            p = os.path.join(self.tmp.name, name)
            with open(p, "w") as fh:
                fh.write("# fixture\n")
            self.required_input_paths.append(p)

        self.db_path = os.path.join(self.tmp.name, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        self.required_input_paths.append(self.db_path)

        self.backup_archive = os.path.join(self.tmp.name, "backup.tar.gz")
        with open(self.backup_archive, "wb") as fh:
            fh.write(b"fixture-backup-bytes")
        self.backup_sha256 = gate_a._sha256_file(self.backup_archive)

        self.site_root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.site_root)
        with open(os.path.join(self.site_root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(self.site_root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

        self.run_dir = os.path.join(self.tmp.name, "run")

        fp = {"a": 1}
        self.fixture = {
            "required_inputs": self.required_input_paths,
            "backup_archive": self.backup_archive,
            "backup_archive_sha256": self.backup_sha256,
            "cars_ui_source": CLEAN_CARS_UI,
            "usercustomize_source": CLEAN_USERCUSTOMIZE,
            "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
            "protected_fingerprints_before": fp,
            "protected_fingerprints_after": dict(fp),
            "db_path": self.db_path,
            "ua0009_fingerprint_before": {"h": "same"},
            "ua0009_fingerprint_after": {"h": "same"},
            "ua0009_url": "https://example.com/UA-0009.html",
            "ua0009_opener": _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None)),
            "site_root": self.site_root,
            "allowed_site_names": ["index.html", "katalog.html"],
            "protected_function_names": ["upload_media", "delete_media"],
            "tmp_dir": self.tmp.name,
            "db_function_source": DB_FUNCTION_SOURCE,
            "site_before": {"x": 1},
            "site_after": {"x": 1},
            "run_dir": self.run_dir,
        }

    def test_clean_fixture_reaches_pass_awaiting_approval(self):
        receipt = run_gate_a(self.fixture)
        self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", receipt["unmet_predicates"])
        self.assertEqual(receipt["unmet_predicates"], [])
        self.assertEqual(receipt["production_write"], "NO")
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "receipt.json")))

    def test_backup_hash_mismatch_blocks(self):
        bad = dict(self.fixture)
        bad["backup_archive_sha256"] = "0" * 64
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("backup_verified", receipt["unmet_predicates"])

    def test_protected_fingerprint_change_blocks(self):
        bad = dict(self.fixture)
        bad["protected_fingerprints_after"] = {"a": 2}
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("protected_fingerprints_unchanged", receipt["unmet_predicates"])
        self.assertIn("no_production_write", receipt["unmet_predicates"])

    def test_publication_probe_200_blocks(self):
        bad = dict(self.fixture)
        bad["ua0009_opener"] = _FakeOpener(response_code=200)
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ua0009_not_public", receipt["unmet_predicates"])

    def test_dynamic_dispatch_in_cars_ui_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
            "def upload_media(path, data): return True\n"
            "def delete_media(path): return True\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("admin_routes_text_only", receipt["unmet_predicates"])

    def test_usercustomize_forbidden_import_blocks(self):
        bad = dict(self.fixture)
        bad["usercustomize_source"] = "import team_bot\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("usercustomize_inert", receipt["unmet_predicates"])

    def test_rebuild_subprocess_blocks(self):
        bad = dict(self.fixture)
        bad["avtoperedacha_source"] = "import subprocess\ndef run():\n    subprocess.Popen(['x'])\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("rebuild_queue_bound_no_process_spawn", receipt["unmet_predicates"])

    def test_slow_work_before_close_blocks(self):
        bad = dict(self.fixture)
        bad["db_function_source"] = (
            "def kolonki_cars(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    time.sleep(0)\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("db_closed_before_slow_work", receipt["unmet_predicates"])

    def test_site_inventory_overflow_blocks(self):
        bad = dict(self.fixture)
        bad["allowed_site_names"] = ["index.html", "katalog.html"]
        bad["max_files_per_root"] = 1
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("site_inventory_unchanged", receipt["unmet_predicates"])

    def test_media_persistence_function_removed_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = CLEAN_CARS_UI.replace(
            "def delete_media(path):\n    import os as _os\n    _os.remove(path)\n    return True\n", "")
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("media_persistence_unchanged", receipt["unmet_predicates"])

    def test_missing_input_blocks(self):
        bad = dict(self.fixture)
        bad["required_inputs"] = self.required_input_paths + [os.path.join(self.tmp.name, "missing.py")]
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("inputs_present_and_regular", receipt["unmet_predicates"])


if __name__ == "__main__":
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_cars_ui_transform.py

```python
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cars_ui_transform import transform_cars_ui, scan_reachable_call_graph  # noqa: E402


class CarsUiTransformTests(unittest.TestCase):
    def test_direct_simple_media_call_transforms_cleanly(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'), caption='Car')\n"
            "    await message.reply_video(open('car.mp4', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_reachable_private_helper_exclusive_to_admin_transforms_cleanly(self):
        # Historical fixture name was 'nested helper media call blocks'.
        # The correct required behavior is that a helper reachable only
        # from an admin route, containing an exact direct media
        # expression, is rewritten cleanly (status OK), not blocked.
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertNotIn('reply_photo', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_shared_helper_with_external_caller_blocks(self):
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
            "\n"
            "def customer_car_view(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('shared_helper_called_by', result['reason'])

    def test_media_group_count_and_async_await_ok(self):
        src = (
            "async def admin_car_edit(message):\n"
            "    await message.reply_media_group([open('a.jpg', 'rb'), open('b.jpg', 'rb')])\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        self.assertIn('2 item', result['candidate'])
        self.assertIn('await', result['candidate'])

    def test_open_call_outside_media_expression_blocks(self):
        src = (
            "def admin_car_delete(message):\n"
            "    f = open('car.jpg', 'rb')\n"
            "    message.reply_text('deleted')\n"
        )
        result = transform_cars_ui(src, ['admin_car_delete'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unresolved_callable:open', result['reason'])

    def test_getattr_dynamic_dispatch_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    getattr(message, 'reply_photo')(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_attribute_alias_assignment_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    fn = message.reply_photo\n"
            "    fn(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_lambda_wrapped_media_call_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    handlers = [lambda: message.reply_photo(open('car.jpg', 'rb'))]\n"
            "    handlers[0]()\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_callback_container_media_reference_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    callbacks = {'photo': message.reply_photo}\n"
            "    callbacks['photo'](open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_return_alias_of_media_method_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    return message.reply_photo\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_side_effectful_media_argument_helper_blocks(self):
        src = (
            "def _prepare_photo():\n"
            "    log_side_effect()\n"
            "    return b'data'\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(_prepare_photo())\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unsafe_media_argument_side_effect', result['reason'])

    def test_protected_customer_function_untouched_when_not_reachable(self):
        src = (
            "def customer_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('y.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate_tree = ast.parse(result['candidate'])
        funcs = {n.name: n for n in candidate_tree.body if isinstance(n, ast.FunctionDef)}
        customer_src = ast.dump(funcs['customer_car_view'])
        admin_src = ast.dump(funcs['admin_car_view'])
        self.assertIn('reply_photo', customer_src)
        self.assertNotIn('reply_photo', admin_src)

    def test_missing_entry_point_blocks(self):
        src = (
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_missing'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('missing_entry_points', result['reason'])

    def test_candidate_compiles_for_all_ok_cases(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_list(message):\n"
            "    message.reply_document(open('doc.pdf', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view', 'admin_car_list'])
        self.assertEqual(result['status'], 'OK')
        compile(result['candidate'], '<test>', 'exec')


if __name__ == '__main__':
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_cars_ui_transform.py


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_canonical_integration.py

```python
"""TASK 029 identity and monkeypatch integration tests.

These tests prove crm_speed_gate_a.py no longer redefines a duplicate
admin-media transformer/scanner and instead delegates to the canonical
cars_ui_transform module for the actual atomic media-call rewrite.

Run as part of the package-wide discovery command:
    python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cars_ui_transform
import crm_speed_gate_a as gate_a


MEDIA_SOURCE = (
    "def gallery(update, context):\n"
    "    update.message.reply_photo(1)\n"
    "def video_gallery(update, context): pass\n"
    "def diag_photo_show(update, context): pass\n"
    "def diag_video_show(update, context): pass\n"
)


class CanonicalIdentityTests(unittest.TestCase):
    def test_gate_a_module_reference_is_canonical_module_object(self):
        self.assertIs(gate_a.cars_ui_transform, cars_ui_transform)

    def test_no_duplicate_legacy_transformer_class(self):
        self.assertFalse(hasattr(gate_a, "_MediaCallTextTransformer"))

    def test_no_duplicate_legacy_scanner_class(self):
        self.assertFalse(hasattr(gate_a, "_FunctionVisitor"))

    def test_gate_a_transform_delegates_rewrite_to_canonical_function(self):
        with mock.patch.object(
            cars_ui_transform, "transform_cars_ui", wraps=cars_ui_transform.transform_cars_ui
        ) as spy:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        spy.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertIn("reply_text", result["candidate"])
        self.assertNotIn("reply_photo(", result["candidate"])

    def test_gate_a_transform_does_not_call_canonical_when_no_rewrite_needed(self):
        clean_source = (
            "def gallery(update, context): pass\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        with mock.patch.object(
            cars_ui_transform, "transform_cars_ui", wraps=cars_ui_transform.transform_cars_ui
        ) as spy:
            result = gate_a.transform_cars_ui(clean_source)
        spy.assert_not_called()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["candidate"], clean_source)


class CanonicalMonkeypatchTests(unittest.TestCase):
    def test_gate_a_surfaces_canonical_blocked_reason(self):
        stub_result = {"status": "BLOCKED", "reason": "stubbed_block_for_test", "candidate": None}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result) as stub:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        stub.assert_called_once()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("stubbed_block_for_test", result["reasons"])
        self.assertIsNone(result["candidate"])

    def test_gate_a_surfaces_canonical_ok_candidate_unmodified(self):
        stub_candidate = (
            "def gallery(update, context):\n"
            "    update.message.reply_text('[stubbed]')\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        stub_result = {"status": "OK", "reason": "rewritten", "candidate": stub_candidate}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result) as stub:
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        stub.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["candidate"], stub_candidate)

    def test_gate_a_rejects_canonical_result_that_reintroduces_violation(self):
        # Canonical layer claims OK but returns a candidate that still
        # contains a direct media call (simulated canonical bug); the
        # gate_a adapter's post-rewrite re-scan must still fail closed.
        stub_candidate = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(1)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        stub_result = {"status": "OK", "reason": "rewritten", "candidate": stub_candidate}
        with mock.patch.object(cars_ui_transform, "transform_cars_ui", return_value=stub_result):
            result = gate_a.transform_cars_ui(MEDIA_SOURCE)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["candidate"])


if __name__ == "__main__":
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_canonical_integration.py
