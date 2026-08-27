# cloud_report_020.md — CRM-SPEED-001 controller-repair report (Task 024)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

This is a corrective iteration of the CRM-SPEED-001 package
(`cloud/crm_speed_optimization/`) after the independent controller audit
of commit `8421b4a728187ee28a2e57d31e8396c31c8826d6` found the package
NOT READY_FOR_GATE_A. Every implementation change in this iteration was
authored by Claude. No Gate A execution occurred. No production, CRM,
bot, site, media, card, generator, WSGI, or process was touched.

## Defect-by-defect correction summary

**Defect 1 — rebuild queue.** Replaced the non-functional
`threading.Lock`-based design with `CrossProcessLock`
(`cross_process_lock.py`), an atomic, non-blocking, cross-process lock
using PID + `/proc` start-time evidence, an ownership token, and an
fcntl-guarded compare/replace section that removes the prior TOCTOU
exposure without ever killing a process. `rebuild_queue.py` now (a)
locates the real in-process `stranica` generation anchor structurally via
`find_stranica_generation_anchors()`, requiring exactly one unambiguous
candidate or raising `AnchorNotFoundError` (BLOCKED, candidate left
unmodified) — it never binds a `None` default; (b) implements a
marker-file-based coalescing mechanism so a burst across two independent
processes collapses to at most one pending follow-up, verified by
`RebuildQueueCoalescingTests` using real subprocesses; (c) `enqueue()` is
non-blocking and returns immediately in all cases; (d) failures are
logged with a bounded traceback excerpt and the loop terminates rather
than retrying forever.

**Defect 2 — singleton lifecycle.** `singleton_guard.py` +
`CrossProcessLock` now provide PID/start-time/token evidence, liveness
verification before treating a lock as live, safe stale-lock takeover
guarded by `fcntl.flock` (no TOCTOU overwrite, no process killing),
release gated on token+PID match, guaranteed release via `atexit` and
installed `SIGTERM`/`SIGINT` handlers, and a defined nonzero exit code
(`78`) on duplicate start. Tests cover live duplicate, stale dead PID,
foreign token, clean release, exception-path release, and four-process
simultaneous stale takeover (exactly one winner asserted).

**Defect 3 — SQLite ownership.** `sqlite_ownership.py` performs an
AST-based transform (`transform_short_ownership`) that wraps the SELECT
/fetch prefix of each named function in a `try/finally` that closes the
connection immediately, and sets a short (2s) `timeout` on `connect()` if
none was given. A companion verifier
(`verify_no_live_handle_across_slow_call`) walks statement order
(including nested `if/for/while/with/try` blocks) and reports any slow
call (`sleep`, `send_*`, `reply_*`, `requests.*`, `open`, `render`,
`generate`, etc.) that occurs while a DB handle/cursor is still open. The
orchestrator (`crm_speed_gate_a.py`) runs this verifier against the
*patched* AST and raises `GateABlocked` if any violation remains — the
transform is never accepted merely because it ran without raising.
Ambiguous anchors (no `connect()`, handle unused, function missing) raise
`AnchorNotFoundError`, which the orchestrator converts to BLOCKED with
the candidate left unmodified, per the task's explicit fallback
instruction.

**Defect 4 — publication/protected-state proof.**
`ua0009_publication_check.py` now returns BLOCKED (not SKIPPED) when no
canonical UA-0009 URL is configured via `UA0009_CANONICAL_URL` or the
fixed config file; it performs a no-redirect probe
(`urllib.request.HTTPRedirectHandler` returning `None`) and only accepts
`404`/`410`/connection-refused as "not served"; any other status (`200`,
unexpected `3xx`, `5xx`) is BLOCKED. `PRAGMA quick_check` must equal
exactly the string `'ok'`; any `OperationalError` (including a transient
lock) is BLOCKED without mutation (`query_only=1`, `mode=ro` URI,
`timeout=2`). The orchestrator's `_final_fingerprints_and_predicate`
includes `ua0009_publication_proven_unpublished` and
`ua0009_fingerprint_unchanged` as required members of the final
all-`True` predicate — publication status is no longer excluded from
`all_checks_ok`.

**Defect 5 — reachable media-call proof.** `media_call_graph.py` builds a
bounded same-module call graph starting from the four admin entry points,
follows statically resolvable local-function calls (including through
helper indirection, e.g. `gallery -> helper_send -> reply_photo`), detects
assignment-based aliasing of a media-send bound method
(`f = obj.send_photo`), and treats `getattr`/`eval`/`exec`-based dynamic
dispatch as BLOCKED rather than passing. `semantic_hash()` computes a
normalized AST-dump SHA-256 for named media-persistence functions so the
orchestrator records before/after evidence rather than merely checking
name presence. Tests cover a clean module, an indirect-helper violation,
and a dynamic-dispatch BLOCKED case.

**Defect 6 — SafeWriter/manifest hardening.** `safe_writer.py` rejects a
symlinked run root, symlinks in any parent path component, symlinked or
non-regular or hard-linked (`st_nlink != 1`) write targets, and path
traversal/escape; it opens sources with `O_NOFOLLOW` where available and
verifies `(st_ino, st_dev)` identity between `lstat` and `fstat` to catch
a swap race; writes go through `tempfile.mkstemp` in the same directory,
`fsync` on the file and the containing directory, `os.replace` for
atomicity, and `0o600` mode; free space is checked before every write.
`build_manifest.py` produces a deterministic manifest keyed by sorted
`(path, sha256)` pairs plus the exact SHA-256 of every `.py` file in the
package itself (`package_code_hashes`), binding the receipt to the exact
code that produced it. `verify_gate_a.py` independently recomputes the
manifest and checks every required predicate field before accepting a
"pass" receipt as internally consistent.

**Defect 7 — tests and status.** All prior self-referential/static-
presence assertions were replaced with behavioral tests, including real
independent-subprocess tests for every cross-process requirement (locks,
singleton guard, rebuild coalescing). See the explicit limitation below
regarding execution evidence.

## Explicit limitation on execution evidence

Claude authored this package in a delivery context without a code-
execution tool. Claude did not run `python3 -m unittest` here and does
not claim 10/10 (or any number of) actual passing runs. This mirrors the
prior accepted pattern for TASK 015 (`REC-0009`: "execution results were
not fabricated"; independently verified later by the controller as
`REC-0011`/`REC-0013`). Per the completion rule for this task, the
honest final status is **`READY_FOR_CONTROLLER_REVIEW`**, not
`READY_FOR_GATE_A_EXECUTION`. The controller must run
`python3 -m py_compile cloud/crm_speed_optimization/*.py` and
`python3 -m unittest -v cloud/crm_speed_optimization/test_crm_speed_gate_a.py`
at least 10 full times and record the pass/fail evidence before this
package can be promoted further.

## Known simplifications, stated explicitly (not hidden)

* `_snapshot_and_transform` marks `usercustomize_no_default_startup` based
  on absence of forbidden top-level imports/calls; it does not attempt a
  full behavioral rewrite of `usercustomize.py`/`start_safe.py`/`run_all.py`
  bodies, because those files' exact real content was not available in
  this delivery context. If the real files contain more subtle startup
  side effects than top-level imports/calls, the controller must extend
  this check before Gate A execution; the orchestrator is written so this
  extension raises `GateABlocked` rather than silently passing.
* `site_inventory_unchanged` is currently a placeholder `True` pending
  the owner-approved bounded page/site inventory definition referenced in
  the canonical spec ("bounded production page/site inventories"). This
  must be replaced with a real inventory fingerprint comparison before
  the receipt's PASS predicate can be trusted for Gate A execution on
  real production data. This is flagged, not concealed.

## Compliance restatement

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
