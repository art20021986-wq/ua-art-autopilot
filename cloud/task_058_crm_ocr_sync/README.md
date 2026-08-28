# TASK 058 — CRM-OCR-SYNC-001 Round 1: Read-Only Discovery Package

STATUS MARKER: READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Purpose

This package is a fail-closed, read-only discovery tool intended to be synced to the
PythonAnywhere safe inbox at
`/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/` and executed exactly once
by an isolated controller. It never writes production, CRM, crm.db, website pages,
bot sources, generators, WSGI files, schedules, services, or UA-0009. It never
reloads or restarts anything and never triggers a rebuild.

No live execution has occurred yet. Everything under `evidence/` is a NOT_RUN
placeholder until a controller actually runs this against production and relays a
sanitized receipt back into this repository.

## Files

- `live_discovery.py` — stdlib-only, read-only. Computes SHA-256/size/mtime for an
  allowlisted set of source/db/site/log paths, scans bounded recent log lines for
  the four required counters, opens the CRM sqlite database strictly in
  `mode=ro` with `PRAGMA query_only=ON`, performs a `PRAGMA quick_check`, hashes
  the DB before/after, and emits sanitized JSON with no secrets, PII, tokens, or
  raw image bytes.
- `task058_readonly_controller.py` — validates a sync manifest (path + sha256 for
  every file that must exist in the safe inbox before remote execution), builds
  exactly one remote command (python3.10 + explicit allowlist args + exact
  receipt redirect path), polls for exactly one receipt file, relays the
  sanitized JSON, and deletes the temporary trigger and receipt in a `finally`
  block on success, failure, or timeout.
- `tests/` — offline unit tests using only temporary fixtures and the two
  committed JPEG fixtures under `tasks/fixtures/task_058/`.
- `run_tests.py` — compiles every `.py` file in this package and runs the full
  test suite 10 consecutive times, failing loudly on any error or nondeterminism
  beyond timestamps.
- `evidence/task_058_live_discovery.json` — placeholder, `status: NOT_RUN`.
- `TASK_058_CONTROLLER_REPORT.md` — placeholder, `status: NOT_RUN`.

## Safety invariants enforced by design

- `live_discovery.py` contains zero write, DDL, PRAGMA-write, INSERT/UPDATE/DELETE,
  reload, restart, or rebuild-invoking code paths. It only reads.
- All allowlisted paths must resolve under `/home/Carix`, must be regular files
  (no symlinks, no hardlink surprises via `st_nlink` check), must not exceed a
  hard size ceiling, and must not escape the allowlist root via `..` or absolute
  path tricks.
- The sqlite connection string is always
  `file:<path>?mode=ro` opened with `uri=True`, followed immediately by
  `PRAGMA query_only=ON;`. Any attempt to execute a mutating statement against
  that connection raises `sqlite3.OperationalError: attempt to write a readonly
  database` — verified by tests.
- The controller never issues `sudo`, shell globs, `find -exec`, or any command
  other than the one exact allowlisted invocation. It never redirects into any
  path other than the single expected receipt path under the safe inbox.
- The controller does not treat safe-inbox sync permission as production-write
  permission (OWNER_DIRECTIVE REC-0003). It performs no CRM or Production write
  of any kind.
- UA-0009 remains `NOT_SAFE_TO_PUBLISH`/`UNKNOWN` — this package never sets or
  claims otherwise, and never publishes anything.

## What Round 1 does NOT do

- It does not fix the OCR failure message.
- It does not fix the stale-page/rebuild failure.
- It does not execute against PythonAnywhere from this environment (no network
  access here). A human/controller with SSH access to PythonAnywhere must run
  `task058_readonly_controller.py` and commit the resulting sanitized receipt.
- It does not install any Round 2 candidate. Round 2 candidates are designed
  conceptually in `TASK_058_REPORT.md` but not implemented or synced.

## Mandatory markers

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SITE_REBUILT: NO
SERVICE_RELOADED: NO
OCR_FIX_INSTALLED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```
