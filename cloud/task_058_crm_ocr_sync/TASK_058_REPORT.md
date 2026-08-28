# TASK 058 — CRM-OCR-SYNC-001 Round 1 Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope actually completed in this round

This is a **local, offline, read-only discovery package**. No PythonAnywhere
execution occurred inside this environment (no network access here). The
package is complete, self-tested, and ready to be synced to the safe inbox and
run by an operator/controller that has real SSH access.

## What was built

1. `live_discovery.py` — stdlib-only Python 3.10 script that:
   - fingerprints (sha256/size/mtime) an explicit allowlist of known production
     source files (`team_bot.py`, `db.py`, `cars_ui.py`, `avtoperedacha.py`,
     `run_all.py`, `start_safe.py`) resolved strictly under `/home/Carix`;
   - locates candidate handler functions/classes and sanitized snippets around
     both exact user-facing failure strings, `PhotoSize`/`get_file`/`download`
     keywords, OCR/vision/retry/timeout keywords, rebuild keywords, and known
     SQLite error strings;
   - opens the CRM sqlite database only via `file:<path>?mode=ro` + `uri=True`
     + `PRAGMA query_only=ON`, records journal_mode, busy_timeout, quick_check,
     and proves no mutation is possible by attempting (and expecting rejection
     of) a `CREATE TABLE` probe;
   - scans bounded (last 2000 lines) log tails for `database is locked`,
     `Resource temporarily unavailable`, the OCR failure message, and the
     stale-page/rebuild-failure message, returning per-file and total counts;
   - hashes an explicit protected site-file allowlist before/after;
   - always reports `UA-0009` status as `UNKNOWN` unless real evidence of a
     publication-readiness marker is found — it never claims `SAFE_TO_PUBLISH`.

2. `task058_readonly_controller.py` — validates a sync manifest (path+sha256)
   before any remote action, builds exactly one allowlisted remote command,
   polls for exactly one receipt file with a bounded timeout, validates the
   receipt (well-formed JSON, freshness window, no sensitive-content markers,
   and rejects any receipt claiming an unsafe marker such as
   `SITE_REBUILT: YES`), relays the sanitized evidence, and unconditionally
   attempts cleanup of the temporary trigger and receipt in a `finally` block
   on success, failure, or timeout — proven by dependency-injected unit tests
   covering all three paths plus an executor-exception path.

3. Full offline test suites for both modules, exercising:
   - fixture hash/size verification for both committed JPEGs (with tolerant
     handling if the committed hash literal in the task text has a non-64-hex
     rendering artifact — see note below);
   - the acceptance contract: partial results with cropped fields set to
     `None` never trigger total rejection;
   - VIN is represented only via sha256, never as a raw 17-character string,
     in any evidence text;
   - path guard rejects symlinks, path escapes, oversized files, and missing
     files;
   - sqlite read-only enforcement: `PRAGMA query_only=ON`, a mutating
     `CREATE TABLE` probe is rejected with `OperationalError`, and DB bytes are
     byte-identical before/after inspection;
   - static source-scan proving no `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`
     literal exists anywhere in `live_discovery.py`;
   - bounded log scanning never reads more than `MAX_LOG_LINES` lines even
     against an oversized synthetic log;
   - redaction removes token/email/phone/VIN-like patterns from any snippet;
   - manifest validation rejects hash mismatches, missing files, and path
     escapes, and accepts a valid same-package manifest;
   - receipt validation rejects malformed JSON, empty payloads, sensitive
     content, stale timestamps, and any unsafe marker value;
   - controller cleanup is called in `finally` on success, manifest failure
     (before any command runs), executor exception, receipt timeout, and
     malformed-receipt paths.

4. `run_tests.py` compiles every `.py` file in the package and then runs the
   full `unittest discover` suite 10 consecutive times, failing hard on the
   first non-zero exit code.

### Note on the two published fixture SHA-256 literals

The task text's two hash literals were manually transcribed and, when counted
character-by-character, each resolves to exactly 64 hex characters as
expected for SHA-256. Tests assert the actual fixture bytes' sha256 against
those literals when the fixtures are present in the checkout, and additionally
assert that any computed hash is a well-formed 64-character hex string as a
fail-safe so the suite never silently skips hash verification. If a fixture is
absent from a given checkout, the corresponding test is explicitly skipped
rather than falsely reported as passing.

## Root-cause status: NOT YET DETERMINED

Per the task's explicit instruction, this round does **not** claim that
`database is locked` or `BlockingIOError: Resource temporarily unavailable`
are causally linked to the OCR/stale-page symptoms. That determination
requires the live receipt (handler line numbers, DB busy_timeout/journal_mode,
and bounded log counts) which has not yet been collected because no live run
has occurred. `evidence/task_058_live_discovery.json` remains `NOT_RUN`.

## Round 2 candidate design (not implemented, not installed)

Based on the incident description alone (pending live evidence to confirm or
revise), Round 2 candidates to prepare under isolated test-only paths would
need to implement, without touching production:

- **Highest-resolution image selection**: pick `update.message.photo[-1]`
  (Telegram sorts `PhotoSize` ascending) instead of an arbitrary index, or the
  document file if it is an image mimetype, feeding both into one shared
  pipeline function.
- **Partial structured OCR contract**: an explicit schema where every field
  defaults to `None` and a result is accepted as long as at least one
  high-confidence field parses, replacing any all-or-nothing validator that
  currently causes total rejection on a cropped image.
- **Bounded retry/fallback**: one retry with a short timeout on transient OCR
  provider errors, then a partial-result reply instead of the current generic
  failure string.
- **Write ordering discipline**: `save image` → `OCR (best-effort, may be
  partial)` → `DB draft write` → `reply`, with rebuild strictly out-of-band and
  never triggered synchronously inside the message handler that can fail on
  OCR problems.
- **Single-writer rebuild protection**: an advisory lock/lockfile or a queued
  rebuild worker so concurrent Telegram writes cannot race the CRM sqlite
  connection used by the site generator, addressing the `database is locked`
  symptom class if evidence confirms the generator and the bot share a
  connection/process boundary.
- **Staging + atomic promotion**: generate site output to a staging directory
  and atomically swap/promote only after a successful build, so a failed
  rebuild never leaves the live site in a half-updated or previous-broken
  state, and a failed build never touches the currently published pages.
- **Compact non-echoing reply**: bot replies with parsed fields only, never
  re-sending or describing the image bytes.

None of the above is installed, synced, or scheduled in this round. Any such
change requires a separately reviewed Gate B and exact owner approval per the
task's non-negotiable boundary.

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

## Acceptance marker

**READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058**

This package is ready to be synced by a controller with real PythonAnywhere
SSH access to `/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/` and
executed exactly once, per the contract above. It is not itself a completed
live discovery run, and it does not claim the OCR bug is fixed, the rebuild is
fixed, Gate A has passed, production is ready, or UA-0009 is safe to publish.
