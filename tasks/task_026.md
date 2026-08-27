# TASK 026 — CRM-SPEED-001 controller rejection round 3

## Owner authorization and safety boundary

Continue the owner-approved CRM-SPEED-001 repair. Correct only files under cloud/. Do not execute Gate A, install candidates, modify Production/CRM/database/bot/site/media/cards/generators/WSGI/processes, or publish UA-0009.

## Executed controller result for commit 73ac2b4744e27172a7011967f70e47df4ba86ca8

Python compile: PASS.
First unittest run: 59 total; 56 PASS, 2 FAIL, 1 ERROR. Required 10 full green runs were not attempted because run 1 failed.

Exact failures:

1. CarsUiTransformTests.test_dynamic_dispatch_blocks
   - source used: fn = getattr(update.message, 'reply_photo'); fn(open(...))
   - expected candidate is None/BLOCKED
   - actual: unsafe candidate returned unchanged and was accepted.

2. DeterministicRepeatTests.test_nondeterministic_transform_blocks
   - TypeError: measure_deterministic_repeat() got an unexpected keyword argument 'src'
   - test and implementation API are inconsistent.

3. SiteInventoryTests.test_overflow_blocks
   - no overflow blocker was emitted.
   - Current test slices ALLOWED_SITE_NAMES to MAX_FILES_PER_ROOT + 1, but the fixed allowlist contains fewer entries than the production max, so it never constructs an overflow. This is a false test.

Current package is NOT READY FOR GATE A.

## Mandatory corrections

### A. Dynamic dispatch must fail closed

Before rewriting any admin route:
- run the bounded reachable call-graph scan on the original route graph;
- any getattr/setattr, eval, exec, globals/locals lookup, alias assignment from a media method, indirect callback, or unresolved callable inside the four routes or reachable helpers that could send/read/download media must BLOCK;
- specifically detect the executed regression case above;
- do not return an unchanged candidate as safe;
- after transformation, run the graph scan again and require clean;
- add cases for getattr literal media name, getattr computed name, bound-method alias, callback list/dict, lambda, return alias, await alias, nested helper, and dynamic clean-but-ambiguous dispatch. Ambiguity => BLOCKED.

### B. Deterministic repeat API and test must agree

- use one explicit signature: measure_deterministic_repeat(transform_fn, source, args=(), repeats=10);
- tests must call it positionally or with source=, never undefined src=;
- do not merely fix the typo: execute a deterministic case and at least five deliberately nondeterministic transforms (random content, time, UUID, unordered set serialization, changing metadata);
- each nondeterministic case must return failed evidence and force final Gate A status BLOCKED;
- compare candidate bytes, unified diff bytes, status, reason list, and metadata digest for all 10 repetitions.

### C. Inventory overflow test must be real while production default remains max 32

Keep production MAX_FILES_PER_ROOT = 32. Add an explicit max_files_per_root parameter used only by tests (default 32). Construct a test with at least 3 allowed names and max_files_per_root=2; assert overflow. Also:
- overflow count must be based on matched allowed entries;
- default production scan must accept up to 32 and BLOCK on >32 if the future allowlist grows;
- do not lower the production cap only to make the test pass;
- test exact boundary N and N+1.

### D. Consolidate duplicate implementations

The package now contains old module implementations (cross_process_lock.py, rebuild_queue.py, etc.) plus new implementations embedded in crm_speed_gate_a.py. This creates ambiguity and future drift.

- one canonical implementation per mechanism;
- crm_speed_gate_a.py must import canonical modules rather than duplicate CrossProcessLock/SafeWriter/etc.;
- tests must import the exact same classes/functions used by the launcher;
- delete obsolete code or make it a thin re-export with byte-identical API;
- add identity assertions that launcher/orchestrator/test imports resolve to the same object/module.

### E. Execute-ready end-to-end truth

- A synthetic clean full Gate A test must actually call the public no-argument-equivalent orchestration function and reach GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL with all evidence measured.
- Remove or block every placeholder proof.
- Confirm UA-0009 network errors still BLOCK; only HTTPS 404/410 pass.
- Confirm site inventory, candidates, diffs, DB close-before-slow-work, singleton, rebuild call replacement, media persistence semantic hashes, protected fingerprints, manifest, and zero outside-QA writes are all part of the final predicate.
- Full suite must compile and be capable of 10 consecutive green runs.

Update latest_status, owner_reply, cloud_report, test matrix, and instructions truthfully. Claude status: READY_FOR_CONTROLLER_REVIEW or BLOCKED only.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

---

## BEGIN COMPLETE PRIOR TASK 025 CONTRACT

# TASK 025 — CRM-SPEED-001 controller rejection round 2

## Owner authorization

Владелец поручил продолжать работу. Это обязательная корректирующая итерация после независимого исполнения и аудита commit 6207fc5a6b1f540475116d646261f37181a6bb22.

Claude must correct the existing package under cloud/crm_speed_optimization. All implementation changes must be Claude-authored. Work only under cloud/. Do not execute Gate A, do not install anything, and do not touch Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, or UA-0009 publication.

## Controller execution result — current package rejected

Python compilation passed. The very first full unittest run failed, therefore the required 10/10 runs were not reached:

- failing test: CrossProcessLockTests.test_simultaneous_stale_takeover_only_one_wins
- observed: expected exactly 1 successful takeover, got 3
- additional runtime defects: multiple atexit callbacks raised FileNotFoundError while opening <temporary>/test.lock.guard after TemporaryDirectory cleanup

This is a real executed result, not a theoretical review. Current status remains NOT READY FOR GATE A.

## Mandatory corrections for this round

### 1. Make stale takeover test and implementation truly concurrent

The current subprocess test lets a winner release before other contenders attempt, so sequential successes are counted as simultaneous winners. Replace it with a deterministic multiprocess barrier/handshake:

- create one stale lock;
- start N independent contender processes;
- wait until every contender reports ready;
- release one common start barrier;
- the winning process must hold ownership until the parent confirms all contenders have attempted;
- exactly one contender may report acquired while the hold barrier is active;
- every loser must return immediately and must not alter owner evidence;
- after explicit winner release, exactly one later fresh contender may acquire;
- run this stress scenario at least 100 rounds inside one behavioral test or an equivalent deterministic high-contention loop;
- verify lock contents/token/PID/start-time remain the winner's throughout the hold interval.

If the implementation permits more than one owner during any overlap, fix CrossProcessLock; do not weaken the assertion.

### 2. Eliminate atexit lifecycle errors

- release() must be idempotent and exception-safe;
- atexit must never recreate a deleted parent directory and must silently return when the run/test directory is gone;
- unregister atexit callbacks on explicit release where supported;
- signal/atexit handlers must never raise;
- test explicit release + directory cleanup, implicit atexit simulation after cleanup, repeated release, forked child cleanup, and foreign-token cleanup.

### 3. Remove every fabricated/placeholder True from Gate A predicates

The current orchestrator contains unconditional proof assignments, including:
- site_inventory_unchanged = True (documented placeholder);
- no_production_write = True;
- repeat_runs_byte_identical = True;
- singleton_guard_present = True;
- no_process_spawn_in_rebuild_path = True;
- db_handles_closed_before_slow_work = True;
- media_persistence_functions_unchanged = True after incomplete evidence.

No required PASS field may be assigned True without fresh measured evidence stored in the receipt. Implement an evidence object for each predicate and have the final boolean derive only from that evidence. Tests must mutate one piece of evidence at a time and prove final status becomes BLOCKED.

### 4. Implement a real bounded site/public inventory

Replace the placeholder with before/after fingerprints using fixed non-recursive roots and fixed allowed patterns:

Roots:
- /home/Carix/site
- /home/Carix/video
- /home/Carix/public_html

Allowed bounded names/patterns only:
- index.html
- katalog.html
- UA-0001.html through UA-0009.html
- UA-0001-diag.html through UA-0009-diag.html
- UA-0001-track.html through UA-0009-track.html

Rules:
- no recursive scanning;
- maximum 32 matched files per root; overflow or unexpected ambiguity => BLOCKED;
- missing required root => BLOCKED;
- each matched entry must be a regular non-symlink, single-link file;
- record canonical path, mode, size, mtime_ns, SHA-256;
- compare canonical sorted before/after inventories byte-for-byte;
- inventory comparison must be part of final PASS predicate;
- tests: mutation, add/remove allowed file, symlink, hard link, missing root, overflow, unchanged pass.

### 5. Publication probe must fail closed on network errors

Current code treats status -1 / connection-refused as “not served.” That is ambiguity, not proof.

Only an actual no-redirect HTTP 404 or 410 may pass. DNS error, TLS error, timeout, connection refused, 3xx, 2xx, 5xx, missing URL, malformed URL, non-HTTPS URL, redirect, or proxy error must BLOCK. Add behavioral tests for every case. Bind the exact canonical HTTPS UA-0009 URL into the review configuration/receipt; do not guess it.

### 6. Real candidate transforms, not snapshots/placeholders

The current report admits that usercustomize.py/start_safe.py/run_all.py were not deeply rewritten because real sources were unavailable. Gate A exists precisely to transform bounded real source copies; it must implement safe structural transformations at runtime:

- usercustomize: generate an inert candidate; remove all top-level application/background imports, calls, thread/process creation, network/DB/filesystem mutation; preserve only proven harmless interpreter customization. Any unclassified top-level effect => BLOCKED.
- start_safe.py and run_all.py: inject the tested singleton lifecycle around the exact main execution in candidate copies, guaranteed release on normal/exception/signal paths, no import-time side effects. Missing/ambiguous main anchor => BLOCKED.
- avtoperedacha.py: actually replace the exact rebuild invocation with the bound in-process RebuildQueue path in the candidate; prove no subprocess/os.system/multiprocessing remains reachable in the rebuild call graph; a descriptor-only anchor is not sufficient.
- cars_ui.py: actually generate text-only candidates for the four admin routes. If current source has reachable media calls, transform exact structural call sites or BLOCKED; after-transform call graph must be clean. Preserve media persistence/customer/public functions by before/after semantic hashes.
- samokontrol/avtoperedacha SQLite: keep the structural transformation, but prove it against candidate functions and fail closed on unsupported control flow.

Candidate files and unified diffs must be written only inside the QA run directory. Original sources remain byte-identical.

### 7. Deterministic repeat must be measured, not asserted

Run every transform 10 times from the exact original bytes and compare candidate bytes + diff bytes + metadata hashes. Store all 10 hashes in receipt. True only when all hashes are identical. Add a deliberately nondeterministic transform test that must BLOCK.

### 8. no_production_write must be derived

Derive it from:
- before/after fingerprints of every bounded protected source/DB;
- before/after fixed site/public inventory;
- audit of every write target opened by the Gate A process, all constrained beneath the resolved run QA directory;
- zero unexpected writes.

Do not set it unconditionally. Any missing evidence => BLOCKED.

### 9. End-to-end behavioral coverage

Add a full synthetic Gate A fixture containing all required source files, DB, backup, three site roots, exact URL probe mock, and representative admin/rebuild/SQLite structures.

Required end-to-end tests:
- clean fixture reaches GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL;
- each mandatory proof independently fails closed;
- original fixture tree hashes unchanged after every pass and blocked run;
- candidates contain actual requested behavior, not markers only;
- complete suite must pass 10 full controller runs.

Update all status/report/docs truthfully. Final Claude status may only be READY_FOR_CONTROLLER_REVIEW or BLOCKED, never READY_FOR_GATE_A_EXECUTION without controller evidence.

Always state:
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

---

## BEGIN COMPLETE PRIOR TASK 024 CONTRACT

# TASK 024 — CRM-SPEED-001 controller repair after independent audit

## Owner authorization

Владелец поручил продолжать работу. Это обязательная корректирующая итерация после независимого аудита коммита 8421b4a728187ee28a2e57d31e8396c31c8826d6.

Claude должен исправить существующий пакет `cloud/crm_speed_optimization/`. Все implementation changes должны быть authored by Claude. Разрешены только reviewable files under `cloud/`. Не выполнять Gate A, не устанавливать в Production, не менять CRM/БД/бот/сайт/медиа/карточки/генераторы/WSGI/процессы и не публиковать UA-0009.

## Controller verdict on current package

Current package is NOT READY_FOR_GATE_A. Python compile and 21/21 synthetic tests passed, but those tests missed mandatory behaviors from CRM-SPEED-001. Fix every item below; do not merely change status text or tests.

### Critical defect 1 — rebuild queue is non-functional and not cross-process safe

Current `REBUILD_QUEUE_TEMPLATE` uses only `threading.Lock`; this is not an atomic cross-process lock. Its callback defaults to None and the transform replaces production generator calls with enqueue calls without binding the actual existing in-process generator, so a rebuild may silently do nothing.

Required correction:
- structurally identify the exact existing in-process `stranica` generation callable/call path in the source;
- bind it explicitly as the queue callback without importing or executing it during Gate A;
- if exactly one safe callback anchor cannot be proven, BLOCKED and leave candidate unchanged;
- implement an atomic non-blocking cross-process rebuild lock with PID + process-start evidence, ownership token, safe stale validation, no killing of processes, and owner-only release;
- a burst during a running rebuild must produce at most one pending follow-up;
- handler enqueue must return immediately;
- failures must be bounded/logged without secrets and must never spin/retry forever;
- tests must use two independent processes, not only two calls in one process, and must prove exactly one concurrent rebuild plus one coalesced follow-up.

### Critical defect 2 — singleton lifecycle is incomplete

Current guard never calls release and treats any old file as a permanent live owner.

Required correction:
- PID/start-time/ownership-token evidence;
- verify liveness and process identity before considering a lock live;
- safe stale-lock takeover with atomic compare/retry, no TOCTOU overwrite, and no process killing;
- release only if token still belongs to this process;
- guaranteed release via `try/finally`, `atexit`, and clean signal handling where compatible;
- duplicate start exits quickly with a nonzero/defined diagnostic and must not alter another process lock;
- tests must use independent processes and cover live duplicate, stale dead PID, PID reuse/start-time mismatch, foreign token, clean release, exception release, and simultaneous stale takeover.

### Critical defect 3 — SQLite ownership requirement is not implemented

Adding `timeout=5` is insufficient. The original specification requires SELECT rows to be materialized into immutable ordinary values and cursor/connection/transaction closed before formatting, page generation, hashing, sleep, Telegram/network I/O, or filesystem work.

Required correction:
- structurally transform the anchored functions in `avtoperedacha.py` and `samokontrol.py`, or BLOCKED if exact safe transformation cannot be proven;
- use short interactive timeout (target <=2 seconds unless actual compatibility requires a documented smaller value);
- no write transaction, WAL/schema/VACUUM/REINDEX/mutable PRAGMA;
- materialize results and close cursor/connection in context/finally before any slow-call category;
- AST/data-flow verification must fail if a DB handle can remain live across a slow operation;
- behavioral tests must instrument fake DB handles and simulated slow work to prove close happens first;
- actionable fast-fail admin result on lock instead of 30-second blocking.

### Critical defect 4 — publication and protected-state proof is not fail-closed

Current `_check_ua0009_not_public` returns SKIPPED when URL is absent, and its result is not part of `all_checks_ok`. `quick_check` is recorded but not required to equal `ok`.

Required correction:
- Gate A must BLOCK if the exact no-redirect UA-0009 publication probe cannot prove 404/410/not-served;
- no environment-variable omission may silently pass; resolve a fixed configured canonical URL from the task contract or produce BLOCKED;
- publication status must be included in final pass predicate;
- require `PRAGMA quick_check` exactly `ok`; transient lock => BLOCKED without mutation;
- canonically serialize bounded non-PII UA-0009 evidence and hash before/after; compare identical;
- fingerprint bounded production page/site inventories before/after and include them in the final predicate;
- fingerprint every protected input before/after including mode, size, mtime_ns, sha256;
- unexpected protected changes must be exactly zero.

### Critical defect 5 — direct-call scan is not reachable-call proof

Current `find_reachable_media_calls` only scans calls lexically inside four functions. A route can call a helper that sends media and still pass.

Required correction:
- build a bounded same-module call graph starting from gallery, video_gallery, diag_photo_show, diag_video_show;
- follow statically resolvable helpers/aliases/method wrappers; ambiguous dynamic dispatch capable of media send => BLOCKED;
- detect Telegram media calls in assignments, returns, awaits, comprehensions, nested branches, callbacks, aliases, media groups, binary reads/download/thumbnail fetch and helper indirection;
- verify text-only output includes type, count, optional safe labels/actions;
- prove upload/attach/save/delete/metadata/DB reference and customer/public media functions are semantically unchanged by hash/AST comparison, not only that names remain;
- add indirect-helper and alias regression tests.

### Critical defect 6 — SafeWriter and manifest hardening

Required correction:
- reject symlinks in every parent component, target symlinks, non-regular targets, hard-link targets (st_nlink != 1), traversal and path escape;
- open sources with no-follow semantics where available and verify fstat identity before/after reading;
- exclusive secure temporary files, fsync file + directory, atomic replace, restrictive mode;
- verify free space before snapshot;
- generate a deterministic manifest of exact code/input/output hashes inside each run and verify it before final PASS;
- bind receipt to the exact package code hashes and source fingerprints;
- tests for symlink parent, hard link, replacement race, target swap, traversal and insufficient free space.

### Critical defect 7 — tests and status

- Replace self-referential/static-presence assertions with behavioral negative tests.
- Run the complete test suite at least 10 full times after fixes; every run must pass.
- Compile every Python deliverable.
- Test fail-closed cases for every mandatory proof.
- `READY_FOR_GATE_A_EXECUTION` is forbidden unless all corrected checks pass.
- If any item cannot be implemented safely without real source anchors, final status must be BLOCKED with exact reasons.
- Update `cloud/latest_status.md`, `cloud/owner_reply.md`, `cloud/crm_speed_optimization/cloud_report_020.md`, `TEST_MATRIX.md`, and operator/rollback docs.
- Explicitly state `PRODUCTION_TOUCHED: NO`, `CRM_TOUCHED: NO`, `GATE_A_EXECUTED: NO`, `UA_0009_PUBLISHED: NO`.

---

## BEGIN FULL CANONICAL CRM-SPEED-001 SPEC

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


## END FULL CANONICAL CRM-SPEED-001 SPEC

## Completion rule

Do not claim the production CRM is fixed. The only acceptable outcomes are:
- `READY_FOR_CONTROLLER_REVIEW` after complete offline evidence, or
- `BLOCKED` with exact unmet anchors/proofs.

Commit the complete corrected package through AUTOPILOT. Production and Gate A remain untouched.


## END COMPLETE PRIOR TASK 024 CONTRACT


## END COMPLETE PRIOR TASK 025 CONTRACT
