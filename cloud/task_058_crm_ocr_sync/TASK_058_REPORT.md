# TASK_058 Round 1 Report — CRM-OCR-SYNC-001 Read-Only Discovery Package

MEMORY MARKERS (verbatim, do not alter):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

## Scope actually completed this round

Round 1 required building and fully testing a fail-closed, read-only
discovery package, plus an isolated controller, **before** any live
PythonAnywhere execution. That is exactly what was delivered:

1. `live_discovery.py` — stdlib-only, Python 3.10 syntax, bounded, read-only.
   Implements: SHA-256/size/mtime capture; symlink/path-escape/oversize
   rejection with an explicit `/home/Carix` base; handler/function scan via
   regex for photo/document/OCR/vision/rebuild/stale handlers with line
   numbers; sanitized bounded snippet extraction around the two exact
   user-facing error strings; SQLite read-only probe using `mode=ro` +
   `PRAGMA query_only=ON`, `journal_mode`, `busy_timeout`, `quick_check`,
   and an explicit blocked-write self-test; bounded recent log counting for
   `database is locked`, `Resource temporarily unavailable`, and the two
   error messages; atomic receipt writing constrained to a caller-specified
   safe-inbox base directory; a sensitive-pattern redaction filter (tokens,
   API keys, Telegram-bot-token shape, VIN-shaped strings, emails, phone
   numbers) applied to every extracted snippet before it can appear in any
   report.
2. `task058_readonly_controller.py` — dependency-injected controller
   (`sync_fn`/`run_fn`/`poll_fn`/`cleanup_fn`) reusing the safety approach of
   `cloud/bot_logistics/pythonanywhere_discovery_controller.py` without
   modifying that file. Validates a manifest of local files against expected
   SHA-256 before any sync; builds one exact command string and rejects it if
   it contains `sudo`, `*`, `find `, redirection, `&&`, `|`, `;`, `rm `, or
   `reload`; polls for exactly one receipt with a bounded timeout; validates
   receipts for size, sensitive-token presence, malformed JSON, missing
   timestamp, and staleness; always calls `cleanup_fn()` in `finally`
   regardless of success, `ControllerError`, an unrelated exception from
   `run_fn`, or a timeout.
3. Two full offline test suites (`tests/test_live_discovery.py`,
   `tests/test_readonly_controller.py`) using only temporary fixtures,
   covering: fixture hash/size self-consistency and drift detection;
   acceptance-contract null handling for cropped fields; safe-path rejection
   of symlinks, path escapes, oversized files, and missing files; redaction
   correctness; handler/error-message scan correctness with no secret leakage;
   SQLite read-only probe write-blocking and byte-identity preservation;
   receipt path-escape rejection; manifest validation (pass, hash-mismatch,
   missing-file); remote-command forbidden-token absence; receipt validation
   (valid, sensitive-content, malformed, stale, missing-timestamp,
   oversized); guaranteed cleanup on success, timeout, run-time exception, and
   manifest failure; and determinism of repeated scans/validations excluding
   timestamps.
4. `run_tests.py` compiles every package source file and then runs the full
   suite 10 consecutive times, failing loudly on the first failure.

## What was NOT done this round (by design)

- No connection to the live PythonAnywhere host was made. This chat/build
  environment has no network access to production infrastructure, and the
  task's own safety boundary requires the controller step to be a separate,
  explicitly authorized action outside this deliverable.
- No file was written to `/home/Carix/autopilot_inbox/...` on any real
  server.
- No production, CRM, database, site, bot, generator, WSGI, schedule, or
  service file was read or written.
- No claim is made about the true root cause of the OCR failure or the
  stale-site-rebuild failure. The historical `database is locked` and
  `BlockingIOError` symptoms are **not** attributed to a cause in this
  report; that requires the live evidence this package is built to collect.
- `evidence/task_058_live_discovery.json` and
  `TASK_058_CONTROLLER_REPORT.md` remain `NOT_RUN` placeholders, exactly as
  required, because no live evidence exists yet.

## Round 1 acceptance marker

`READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058`

This marker means: the offline package is complete, safe by construction,
and fully tested against temporary fixtures. It does **not** mean the OCR
bug is fixed, the rebuild path is fixed, Gate A has passed, production is
ready, or UA-0009 is safe to publish. None of those claims are made.

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

## Recommended next step for ChatGPT/Codex

1. Audit this package's tests by actually running `run_tests.py` in CI (10/10
   consecutive passes required, plus compile success).
2. If accepted, hand `live_discovery.py`, `allowlist.json` (with paths
   confirmed against the real filesystem layout), and
   `task058_readonly_controller.py` to whatever process has real, audited
   SSH/SCP access to PythonAnywhere, bound only to the safe-inbox directory,
   to perform exactly one controller run.
3. Only after a real receipt is relayed should
   `evidence/task_058_live_discovery.json` and
   `TASK_058_CONTROLLER_REPORT.md` be replaced with real findings, and only
   then should Round 2 candidate design/testing (highest-resolution image
   selection, shared photo/document pipeline, partial-result OCR, bounded
   retry, draft/publish separation, single-writer rebuild protection, atomic
   promotion) begin — still without any install, migration, or service
   restart, and still gated behind a separately reviewed Gate B and explicit
   owner approval.
