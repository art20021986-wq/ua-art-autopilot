# TASK 022 CRM CORE — compact Claude stage 1 after TASK 020 cancellation

## Why this task is smaller

The owner approved CRM speed optimization and requires Claude to write the implementation files. The earlier all-in-one CRM task was canceled when a newer shared Autopilot task entered the single concurrency queue; no CRM files were committed and Production was untouched.

This stage must produce only a compact, independently testable core. Do not write the full PythonAnywhere Gate A launcher or long operator documentation yet. A later stage will wrap this core in live-input fingerprinting and Gate A evidence.

## Non-production boundary

Write only the exact cloud/ deliverables below. Do not access or modify PythonAnywhere, Production, CRM DB, site, media, processes, scheduled tasks, or UA-0009. Never include passwords, tokens, customer PII, database blobs, live media, or invented passing evidence.

## Confirmed faults the core must address

- usercustomize.py for Python 3.10 and 3.13 starts CRM/background imports in every interpreter.
- avtoperedacha.py has in-process and subprocess-based stranica rebuild paths; logs showed BlockingIOError(11, Resource temporarily unavailable).
- SQLite reads were held across slow work for about 21.7 seconds and other requests waited about 30 seconds with database is locked.
- cars_ui.py administrator functions gallery, video_gallery, diag_photo_show, and diag_video_show automatically send photos/videos.
- Administrator CRM must be text-only while upload/save/delete/database references/public-site/customer media behavior remains.
- Exactly one explicit worker and one bounded coalescing rebuild queue are required.
- Production site and UA-0009 must remain unchanged.

## Implement a reusable runtime core

Create an import-safe Python 3.10+ standard-library module that provides:

1. SingletonProcessLock
   - atomic, non-blocking acquisition;
   - lock record contains PID and process-start evidence;
   - bounded safe stale-lock detection;
   - never kills processes;
   - duplicate acquisition fails quickly and clearly;
   - context manager plus explicit release;
   - no filesystem action on module import.

2. CoalescingRebuildQueue
   - constructed inert and starts only by explicit call;
   - one worker thread at most;
   - repeated request calls while pending/running collapse into at most one follow-up run;
   - request returns immediately;
   - bounded stop/join, no infinite retry/spin;
   - cross-process execution lock support;
   - callback executes in-process only;
   - no subprocess, shell, os.system, multiprocessing, or import-time start;
   - bounded structured diagnostics with duration, no secrets.

3. short_read_rows
   - opens SQLite only inside the function;
   - URI read-only mode and query_only ON;
   - short explicit busy timeout;
   - parameterized SELECT only;
   - materializes rows to immutable ordinary values;
   - closes cursor/connection before returning;
   - rejects multiple statements and mutating SQL/PRAGMA;
   - raises a fast actionable busy error;
   - no schema or journal mutations.

4. text_media_summary
   - returns concise administrator text containing media kind, count, and sanitized optional labels;
   - never opens/downloads media and never calls Telegram;
   - handles zero items and bounded output.

## Implement a fail-closed source transformer

Create a separate import-safe module that receives source text plus a logical target name and returns transformed source plus structured evidence. It must never read/write files itself.

Use ast/tokenize and explicit function/class/import anchors with expected match counts. Broad regex rewriting of Python is forbidden.

Supported logical targets:

- usercustomize_py310 and usercustomize_py313:
  default output is inert; remove application/background imports and startup expressions; preserve only provably harmless interpreter customization; ambiguous top-level side effects are BLOCKED.

- cars_ui:
  target exactly gallery, video_gallery, diag_photo_show, diag_video_show;
  replace only automatic administrator media presentation with concise text calls while preserving navigation and media upload/save/delete/reference functions;
  after transform, a call-graph-aware static check must prove those four functions cannot reach reply_photo, reply_video, send_photo, send_video, send_media_group, media-group creation, binary open/download, or thumbnail fetch;
  ambiguity or missing target is BLOCKED.

- avtoperedacha:
  reject/remove subprocess, shell, os.system, multiprocessing, and import-time generator execution;
  convert the recognized rebuild trigger to an injected CoalescingRebuildQueue request using an explicit structural anchor;
  preserve one recognized in-process generator callable;
  prove no SQLite handle can remain live across the rebuild callback;
  ambiguous or multiple rebuild anchors are BLOCKED.

- samokontrol:
  transform recognized long read functions so rows are fully materialized and DB handles close before formatting/comparison/Telegram/slow work;
  ambiguity is BLOCKED.

- start_safe and run_all:
  preserve callable names where practical;
  prevent startup on import;
  require an explicit main entry and SingletonProcessLock;
  ambiguity is BLOCKED.

Transformation must be deterministic and idempotent: transforming the same source twice yields byte-identical output and evidence. It must preserve unrelated functions and must never claim a live patch was installed.

## Offline tests

Write standard-library unittest fixtures that prove, with at least 10 complete repetitions:

- imports cause no process, thread, DB, network, or filesystem mutation;
- duplicate SingletonProcessLock is rejected quickly and stale handling never kills a process;
- a burst of at least 25 queue requests produces no more than two callback executions;
- request p95 is <= 2 seconds and labeled synthetic;
- short_read_rows returns immutable data and the DB file can be exclusively manipulated after return, proving close;
- mutating/multiple SQL is rejected;
- text_media_summary never invokes media I/O;
- each supported transformer target has one valid fixture that passes;
- missing/duplicate/ambiguous anchors fail closed;
- four admin routes have no reachable media-send/I/O call after transform;
- upload/save/delete/reference fixture functions remain byte/AST-equivalent;
- transformed avtoperedacha contains no process spawning and uses one coalescing queue request;
- no import-time startup remains;
- deterministic/idempotent transform passes 10 times;
- Python outputs compile.

Do not fake executed results. Claude may report only static reasoning; GitHub worker compile checks are separate. Status must be READY_FOR_CORE_REVIEW only when the returned code is complete and internally consistent; otherwise BLOCKED. Always state PRODUCTION_TOUCHED: NO, CRM_TOUCHED: NO, UA_0009_SAFE_TO_PUBLISH: NO.

## Deliverables

Return complete contents for every exact file:

- `cloud/crm_speed_optimization/runtime_core.py`
- `cloud/crm_speed_optimization/source_transformer.py`
- `cloud/crm_speed_optimization/test_core.py`
- `cloud/crm_speed_optimization/cloud_report_022.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

No placeholders, ellipses, TODO-only code, production-write capability, or claims that live tests/deployment occurred. cloud/owner_reply.md must be concise Russian and state that Claude authored the core, Production is unchanged, and the next step is independent review plus a separate Gate A wrapper.
