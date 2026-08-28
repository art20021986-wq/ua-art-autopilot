# TASK 058 — CRM-OCR-SYNC-001 P0: READ-ONLY DISCOVERY AND ISOLATED GATE A

OWNER APPROVAL: The owner approved the exact specification CRM-OCR-SYNC-001 revision 2 by saying «Запускай в работу» and separately requested live percentage updates and recommendations.

PRIORITY: P0 CRITICAL
MODE: READ_ONLY_LIVE_DISCOVERY + ISOLATED_GATE_A_PREPARATION
MAX_ROUNDS: 2
MEMORY_PREFLIGHT: REQUIRED

## Non-negotiable safety boundary

- Do not write production, CRM, crm.db, website pages, bot sources, generators, WSGI, schedules, services, or UA-0009.
- Do not reload/restart any service.
- Do not run a production rebuild.
- The only permitted remote mutation is a tightly bounded temporary trigger plus one receipt under `/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/`; the trigger and receipt must be deleted by the controller in `finally` after the receipt is relayed.
- All candidate code and tests stay under `cloud/task_058_crm_ocr_sync/`.
- Fail closed on missing evidence, source drift, secrets, PII, ambiguous paths, multiple bot copies, or any attempted write outside the safe inbox.

## User-visible incident

Two exact fixtures are committed with this task:

- `tasks/fixtures/task_058/IMG_8128.jpeg`
  - SHA-256 `333ca420282590d774f9f8f834987ea00aa7ec71361b8c4a6016391863ce4caf`
  - 224419 bytes
- `tasks/fixtures/task_058/IMG_8129.jpeg`
  - SHA-256 `5db32cee3e95fb5d5e738eb18250a730af928a0f47952cc706bb620396cdb4ad`
  - 285625 bytes

The Telegram bot first answered:

`Изображение сохранено, но разобрать его не получилось. Опишите машину текстом или голосом.`

It then answered:

`CRM: страницы сайта отстали от базы, и пересобрать их не получилось.`

The screenshots show a legible vehicle card. The expected readable fields are:

- make/model: Kia K5
- year: 2018
- generation: II покоління (FL)
- USD price: 11 400
- UAH price: 510 720
- mileage: 198 000 km
- fuel: gas/LPG
- engine: 2.0 L
- VIN: KNAGU416BKA324445
- transmission: unknown because cropped; do not invent
- location: unknown because cropped; do not invent

The OCR must ignore Telegram chrome and the bot's own failure messages. A cropped right column must cause a partial result, never a total rejection.

## Known historical evidence that must be checked, not blindly assumed

Prior owner evidence recorded these production symptoms:

- `sqlite3.OperationalError: database is locked`
- `BlockingIOError(11, 'Resource temporarily unavailable')`

Determine whether either error is causally related to the current OCR and stale-page messages. Do not declare root cause without current live evidence.

## Round 1 goal

Build and fully test a fail-closed read-only discovery package that can inspect the exact live PythonAnywhere code paths responsible for:

1. receiving Telegram photos/documents;
2. choosing/downloading the image variant;
3. OCR/vision invocation, retry, timeout and parsing;
4. the exact generic OCR failure message;
5. CRM draft/database writes performed before or after OCR;
6. stale-page detection;
7. rebuild invocation and its exact failure path;
8. SQLite connection settings, transaction duration and concurrent writers;
9. process/lock/resource errors in bounded recent logs;
10. UA-0009 publication/readiness coupling.

Do not guess filenames. Discovery may inspect an allowlisted initial set based on known production files (`team_bot.py`, `db.py`, `cars_ui.py`, `avtoperedacha.py`, `run_all.py`, `start_safe.py`) and may discover additional candidate paths only through bounded imports/call references. Any newly discovered path must remain under `/home/Carix`, be a regular non-symlink file, and be reported before any future candidate generation.

## Required remote discovery evidence

The read-only receipt must contain no tokens, credentials, phone numbers, emails, raw customer records, raw image bytes, or full VIN values. The control fixture VIN may be represented only as its SHA-256 in evidence.

Record:

- exact source path, SHA-256, size and mtime;
- function/class names and line numbers for each relevant handler;
- sanitized bounded snippets around the two exact user-facing error messages;
- OCR provider/adapter name without exposing keys;
- whether highest-resolution Telegram `PhotoSize` is selected;
- whether photo and image-document handlers share the same pipeline;
- retry count, timeout and fallback behavior;
- whether partial fields are discarded by schema validation;
- ordering of `save image`, `DB write`, `rebuild`, and `reply` actions;
- exact rebuild command/call target and sanitized failure class;
- SQLite journal mode, busy timeout, open connection count where safely observable, and transaction ownership;
- bounded recent counts for `database is locked`, `Resource temporarily unavailable`, OCR failure, and rebuild failure;
- database SHA-256 before/after, read-only URI proof, quick_check, and identity stability;
- protected site inventory hashes before/after;
- whether UA-0001..UA-0008 remain unchanged;
- UA-0009 status as `SAFE_TO_PUBLISH`, `NOT_SAFE_TO_PUBLISH`, or `UNKNOWN`, with evidence; never publish it.

## Required local deliverables for Round 1

Create under `cloud/task_058_crm_ocr_sync/`:

1. `README.md`
2. `live_discovery.py` — Python 3.10 standard-library-only, bounded and read-only
3. `task058_readonly_controller.py` — validates sync manifest, runs one exact remote command, polls one exact receipt, deletes trigger/receipt in `finally`, relays sanitized evidence
4. `tests/test_live_discovery.py`
5. `tests/test_readonly_controller.py`
6. `run_tests.py`
7. `TASK_058_REPORT.md`
8. `evidence/task_058_live_discovery.json` placeholder with status `NOT_RUN`
9. `TASK_058_CONTROLLER_REPORT.md` placeholder with status `NOT_RUN`

Also update `cloud/latest_status.md` and `cloud/owner_reply.md` per CLAUDE.md.

`FILES_CREATED` in latest_status must list every file required for safe-inbox upload, including `live_discovery.py`, `task058_readonly_controller.py`, tests, reports, and status files. Do not include the JPEG fixtures in safe-inbox upload; they are for GitHub-side offline tests only.

## Mandatory controller contract

The repository already contains a proven pattern at `cloud/bot_logistics/pythonanywhere_discovery_controller.py`. Reuse its safety approach but create task-specific code; do not modify or weaken the existing controller.

The exact remote command must:

- invoke Python 3.10;
- execute only the synced `live_discovery.py` from the safe inbox;
- use an explicit allowlist of source/db/site/log paths;
- redirect JSON only to the exact safe-inbox receipt path;
- never use `sudo`, shell globs, recursive find, production redirects, or broad filesystem scans.

## Offline test requirements

Use only temporary fixtures. Tests must prove:

- both JPEG hashes and dimensions are verified before fixture use;
- expected visible fields are represented in the acceptance contract;
- cropped fields stay null and do not fail the whole parse contract;
- source/database/site bytes are unchanged before/after discovery;
- SQLite is opened with `mode=ro` and `PRAGMA query_only=ON`;
- no INSERT/UPDATE/DELETE/DDL/PRAGMA-write path exists;
- symlinks, hardlinks, path escapes, oversized files and unknown paths fail closed;
- sensitive receipt content is rejected;
- malformed/stale receipts are rejected;
- temporary remote trigger and receipt cleanup occurs on success, failure and timeout;
- no production, CRM, DB, reload, rebuild, or UA-0009 write marker can become true;
- repeated runs are deterministic except timestamps.

Run compile plus the complete task suite at least 10 consecutive times. Do not claim tests ran unless they actually ran in the workflow.

## Candidate design requirements for later Round 2 (do not install now)

Based on evidence, Round 2 must prepare isolated candidates implementing:

- highest-resolution Telegram image selection;
- one shared image pipeline for photo/document inputs;
- partial structured OCR result instead of all-or-nothing rejection;
- bounded retry and fallback;
- explicit nulls for unreadable fields;
- no site rebuild on OCR failure or unconfirmed data;
- draft/published revision separation or an equivalent proven transaction boundary;
- single-writer/idempotent rebuild protection;
- staging generation and atomic promotion only after validation;
- unchanged live production after any failed build;
- compact text response without echoing the image.

No provider change, new paid dependency, database migration, WAL change, service restart, or production install may be performed without a separately reviewed Gate B and exact owner approval.

## Acceptance markers for this task

Round 1 may end only as one of:

- `READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058`
- `BLOCKED_WITH_EXACT_REASON_TASK_058`

It may not claim the OCR bug fixed, the rebuild fixed, Gate A passed, production ready, or UA-0009 safe before live evidence and Round 2 candidate tests exist.

Mandatory markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SITE_REBUILT: NO
SERVICE_RELOADED: NO
OCR_FIX_INSTALLED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

