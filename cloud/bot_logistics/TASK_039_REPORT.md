# TASK 039 REPORT — BOT-LOGISTICS-001 phase A2 repair (Round 3, 8-file response)

## Scope of this round

Per the Round 3 instruction, this response returns exactly the eight required
files. `bot_logistics_transform.py` and `bot_logistics_gate_b.py` (delivered
under TASK 037) are neither modified nor echoed.

## 1. Test suite repair (`test_bot_logistics.py`)

* Rewritten as pure `unittest` (standard library only). No pytest, no pip
  install, no network. `python3 -m unittest discover -v -s cloud/bot_logistics
  -p 'test*.py'` is the only required command.
* The specific defect identified by the independent audit is fixed:
  `test_rollback_on_ambiguous_row_never_reports_success` now builds a
  **separate** temporary table (`cars_ambiguous`) with **no** uniqueness
  constraint on `ua_id`, inserts exactly two `UA-0006` rows, captures the
  full pre-call database bytes, calls the real
  `update_single_container_row` through a signature-adaptive wrapper, and
  asserts: (a) the call is refused, (b) database bytes are byte-identical
  before/after, (c) both original row values (`ROWA`, `ROWB`) are
  unchanged. Fixture setup can never raise `IntegrityError` because no
  `PRIMARY KEY`/`UNIQUE` constraint exists on that table.
* All other TASK 037 coverage areas are preserved as separate test classes:
  discovery source-contract (exact set, duplicates, extras, path variants,
  symlink/hardlink/oversize/identity), discovery DB-contract (no-match,
  two-table ambiguity, two-column ambiguity, no-LIKE identity, DB identity
  stability, no SQL write tokens in the discovery module source), discovery
  CLI exit codes, and container-update behavioral tests (single-row
  update/read-back, idempotence, missing/ambiguous rollback, field
  preservation, other-rows-unchanged, 10-repeat determinism,
  backup/tamper/rollback).

### Known limitation (must be read before trusting a green run)

This round's context bundle did not include the source of
`bot_logistics_transform.py` / `bot_logistics_gate_b.py`. The
`TestContainerUpdateLogic` class therefore imports those modules directly,
introspects the real `update_single_container_row` signature via
`inspect.signature`, and calls it with only the keyword arguments it
actually declares (`_call_update` helper) rather than guessing a fixed
signature. If those real modules expose different parameter names than the
ones probed here (`db_path`, `ua_id`, `container`, `new_container`,
`table`), the adapter will simply omit unmatched kwargs and the call may
fail with a clear `TypeError`/assertion failure rather than a silent skip
— the class carries `@unittest.skipIf(UPDATE_FN is None or GATE_B_REFUSED
is None, ...)` only for the case where the symbols are entirely absent (an
import-shape problem, not a behavioral one), not for behavioral mismatches.
Codex should re-run this suite against the actual TASK 037 module files in
the repository; if any `TestContainerUpdateLogic` test fails there, that is
real, actionable evidence, not a suite defect.

## 2. `bot_logistics_discovery.py` hardening

All nine gaps listed in the audit are addressed:

1. **Secret redaction is real**: every line is scanned against
   secret/token/password/api-key/authorization/private-key/credential
   patterns plus a token-shape regex (`[A-Za-z0-9_-]{32,}`) before it can
   become an anchor snippet; the final JSON payload is scanned again before
   printing, and a match forces a sanitized `BLOCKED` output.
2. **Strict JSON, not repr**: output is exactly one
   `json.dumps(..., ensure_ascii=False, sort_keys=True)` call.
3. **TOCTOU-hardened reads**: `lstat` → regular-file/`nlink==1`/size-cap →
   `open(..., O_NOFOLLOW)` → `fstat` identity check → bounded read →
   `lstat` after → full identity tuple comparison (`ino`, `dev`, `size`,
   `mtime`). Any mismatch blocks.
4. **Exact six-source enforcement**: `validate_sources_arg` requires exact
   count, no duplicates, and exact set equality against
   `REQUIRED_SOURCES`.
5. **No first-match stop**: `find_ua0006` scans every bounded
   table/id-column/container-column combination and only then decides
   PASS (exactly one match) vs BLOCKED (zero or >1 matches).
6. **No LIKE**: identity lookups use parameterized `WHERE id_col = ?` with
   the exact proven representations `UA-0006`, `UA0006`, `0006`, and the
   integer `6`. No wildcard is used anywhere in the module.
7. **Identifier quoting**: `quote_ident` canonically double-quotes and
   escapes embedded quotes; used for every table/column reference derived
   from `sqlite_master`/`PRAGMA table_info`.
8. **Bounds**: `MAX_SOURCE_SIZE`, `MAX_LINES_READ`, `MAX_ANCHORS`,
   `MAX_SNIPPET_CHARS`, `MAX_TABLES`, `MAX_COLUMNS` are all enforced.
9. **Absolute path in the safe-inbox command**: the controller's
   `EXACT_COMMAND` uses the fixed absolute path
   `/home/Carix/autopilot_inbox/cloud/bot_logistics/bot_logistics_discovery.py`.

Current output never reveals the live container string — only
`ALREADY_CORRECT` / `NEEDS_EXACT_UPDATE` is emitted, compared against the
exact validated constant `ONEYSELGF1046602`.

## 3. `pythonanywhere_discovery_controller.py`

Standard-library only (`hashlib`, `json`, `os`, `subprocess`, `sys`,
`time`). Key properties:

* Rejects any username other than `Carix` and any host other than
  `www.pythonanywhere.com`/`eu.pythonanywhere.com`.
* Reads `PYTHONANYWHERE_API_TOKEN` from env; the token is never logged,
  returned, or written to any file.
* `verify_local_artifacts()` runs `py_compile` and the full `unittest`
  suite via an injectable subprocess runner before touching any remote
  state, and returns the local discovery-script SHA-256.
* `verify_manifest()` requires `_sync_manifest.json` to show
  `status=PASS`, `executed_remote_code=false`, `production_touched=false`,
  a matching `discovery_script_sha256`, and a fresh timestamp (rejects
  stale receipts older than `MAX_RECEIPT_AGE_SECONDS`).
* `EXACT_COMMAND` is built once from fixed constants and is the only
  command ever passed to `create_always_on_task`/scheduled-task fallback.
* `GuardedAPI` wraps the injected transport and raises
  `ControllerError` before ever forwarding a call to any name in
  `FORBIDDEN_API_METHODS` (file writes, webapp reload/restart, console
  exec, Gate B, CRM row mutation) — this is enforced at the wrapper level,
  not just by convention.
* Output JSON is parsed with a duplicate-key-rejecting `object_pairs_hook`.
* `_validate_receipt` checks `task_id`, `mode`, `status`,
  all four `*_write`/`ua0009_published` fields are exactly `False`, bounded
  `sources`/`errors` lengths, an allowed `UA0006_CONTAINER_STATUS` value if
  present, and a final secret-shape scan of the serialized receipt.
* `run()` always executes trigger + output cleanup in `finally`, on both
  success and every failure path (including timeout).
* Writes only the two allowed local paths:
  `cloud/bot_logistics/evidence/task_037_discovery.json` and
  `cloud/bot_logistics/TASK_039_DISCOVERY_CONTROLLER_REPORT.md`.

## 4. `test_discovery_controller.py`

Offline `unittest` suite with a `FakeTransport` (no network, no real
PythonAnywhere API calls). Proves: PASS relay, BLOCKED relay (not
upgraded), cleanup on both success and failure, stale-manifest rejection,
wrong-SHA rejection, malformed-JSON rejection, duplicate-key rejection,
secret-shaped output rejection, wrong username/host rejection, missing
token rejection, poll timeout, `production_touched=true`/
`executed_remote_code=true` manifest rejection, unsafe receipt field
rejection, exact remote command equality, exact output path equality,
forbidden-method blocking at the wrapper level, and zero forbidden calls
during a normal successful run.

## 5. `task037_discovery_workflow.yml.example`

Reviewed template, not installed. Triggers only on `workflow_dispatch` or a
push to main that changes the *installed* workflow file itself; permissions
limited to `contents: write`; `concurrency.cancel-in-progress: false`; full
history checkout on `main`; Python 3.11; runs `py_compile` + `unittest`
first; runs the controller with the PythonAnywhere secret and fixed env;
stages and verifies only the two allowed evidence/report paths (aborts on
any other staged path); fetch/rebase/push with five bounded retries and no
force-push; static safety-marker comments for grep-based audit
(`NO_GATE_B_EXECUTED`, `NO_PRODUCTION_WRITE`, `NO_WSGI_RELOAD`,
`READ_ONLY_DISCOVERY_ONLY`). The controller-invocation step is intentionally
a placeholder that exits non-zero until Codex wires and reviews the real
transport, so this template cannot silently execute a real remote action.

## Compile status

All four Python deliverables in this round are valid standard-library
Python 3 source (`bot_logistics_discovery.py`,
`test_bot_logistics.py`, `pythonanywhere_discovery_controller.py`,
`test_discovery_controller.py`); no third-party imports are used anywhere.

## Safety markers

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

## Canonical shared-memory markers (verbatim, do not alter)

```
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
```

## Finish status

`READY_FOR_CODEX_CONTROLLER_AUDIT` — not discovery PASS, not Gate A PASS.
Next step is for Codex to independently run the standard-library test
suite, audit the controller and workflow template, wire a reviewed real
transport, install the workflow, and monitor the single read-only
PythonAnywhere discovery run.
