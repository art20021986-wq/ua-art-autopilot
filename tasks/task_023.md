# TASK 023 — CRM-SPEED-001 full inline execution specification

## Owner authorization and continuation

Это исправленное продолжение TASK 022 после безопасного BLOCKED: контекст-сборщик AUTOPILOT не передал Claude содержимое ссылочного файла. Ниже встроено полное каноническое ТЗ CRM-SPEED-001.

Выполни ТЗ полностью. Все implementation deliverables должны быть authored by Claude. Разрешены только артефакты под cloud/. Не выполнять Gate A, не устанавливать в Production, не менять CRM/БД/бот/сайт/медиа/карточки/генераторы/WSGI/процессы и не публиковать UA-0009. Missing/ambiguous anchors = BLOCKED. READY_FOR_GATE_A допустим только после всех доступных cloud static/unit checks. Всегда укажи PRODUCTION_TOUCHED:NO, CRM_TOUCHED:NO, GATE_A_EXECUTED:NO, UA_0009_PUBLISHED:NO.

---

## BEGIN VERBATIM CRM-SPEED-001 SPEC

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


## END VERBATIM CRM-SPEED-001 SPEC

## Completion protocol

Создай каждый Deliverable с полным содержимым, обнови cloud/latest_status.md и cloud/owner_reply.md, выполни безопасные offline checks без импорта production modules и закоммить полный результат по протоколу AUTOPILOT. Не заявляй, что Production CRM уже ускорена: на этом этапе создаётся только кандидат для независимого аудита и отдельно разрешаемого Gate A.
