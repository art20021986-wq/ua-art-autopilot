# TASK 047 — FERRY WORDING PHASE 1: CONTEXTUAL TRANSFORM AND REAL READ-ONLY DISCOVERY

OWNER REQUEST: «Полная автоматическая замена текста “В море” на “На пароме” во всей системе UA ART. 9 карточек и все будущие».
PARENT_TASKS: task_042, task_043, task_045
MODE: SMALL_EXECUTABLE_PHASE / NO_PRODUCTION_WRITE
MAX_ROUNDS: 3
MEMORY_PREFLIGHT: REQUIRED.

## Reason for split

TASK 045 generated 17 in-memory files but stopped before commit:

PYTHON_STATIC_CHECK_FAIL:cloud/task_045_ferry_wording/transform.py:line=5:offset=15

No TASK 045 output was committed. This smaller phase implements only:

1. exact contextual RU/UA presentation transform;
2. bounded fail-closed read-only discovery;
3. standard-library tests.

Do not build Gate A, a network controller or workflow in this phase.

## Safety

No PythonAnywhere execution. No production, CRM, crm.db, site, card or generator write. No UA-0009 publication. No WSGI/bot/service/schedule change. No Gate B. Do not import/execute production files.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Exact contextual mapping

| Context | Old RU | New RU | Old UA | New UA |
|---|---|---|---|---|
| status/chip/filter | В море | На пароме | У морі | На поромі |
| long | В море · Корея → Грузия | На пароме · Корея → Грузия | У морі · Корея → Грузія | На поромі · Корея → Грузія |
| heading | В море: Корея → Грузия | На пароме: Корея → Грузия | У морі: Корея → Грузія | На поромі: Корея → Грузія |
| short route/timeline | Море | Паром | Море | Пором |

Internal stage sea, data-stage="sea", ?f=sea, IDs, URLs, CSS/API/analytics/database enums remain byte-identical.

data-ru always uses RU mapping and data-uk always uses UA mapping in the same pass. Visible text uses proven document language/context. Ambiguous standalone «Море» without proven language/short-stage context becomes AMBIGUOUS, never guessed.

Scripts, styles, comments, ordinary prose, history and Python/JavaScript/config legacy input aliases remain unchanged. Standalone status «В море» becomes «На пароме», never «Паром». Standalone short «Море» becomes «Паром» only in a proven short-stage node/attribute.

Every Python file must compile.

## Structural transform

Use deterministic target-span edits only. Handle:

- one-line <span class="status-pill">В море</span>;
- proven short-stage classes/anchors such as timeline-legend and stage-step;
- data-ru and data-uk together;
- single/double-quoted attributes;
- void elements, uppercase tags/end tags, entities, comments, doctype;
- script/style and nested elements;
- non-target bytes unchanged.

Return machine-readable applied/ambiguous occurrences with language, form, context, before and after.

## Fixed real-source registry

Use exact bounded candidates relative to /home/Carix, no account recursion:

- video/index.html, video/katalog.html, video/info.html, video/podbor.html;
- video/UA-0001.html through video/UA-0009.html;
- exact site/ equivalents for those names;
- exact bounded UA-0001..UA-0009 diag/track naming candidates;
- stranica.py, yadro.py, master_card.py, cars_ui.py, team_bot.py;
- avtoperedacha.py, db.py, run_all.py, start_safe.py;
- crm.db.

Record missing files honestly. Do not use video/public or catalog.html.

## Fail-closed reads

For every present file:

- canonical containment and every parent checked for symlink escape;
- lstat final regular file, nlink==1;
- O_RDONLY plus O_NOFOLLOW where supported;
- fstat before/read/after;
- stable dev/inode/size/mtime_ns;
- complete bounded read; oversize/truncated/concurrent change blocks;
- hash full bytes only;
- strict UTF-8 or explicit BLOCKED, never errors="ignore".

When run as a script, always emit exactly one strict JSON object including exceptions; no traceback/noise. Redact entire secret-bearing lines and scan final serialized receipt for secret/token/password/api-key/authorization/private-key/credential/token-like values.

## Structural inventory

Do not classify whole HTML source lines. Inventory HTML visible text nodes and data-ru/data-uk structurally. Inspect Python/JS/template string-literal context without executing.

Classifications:

USER_FACING_STATUS, USER_FACING_LONG, USER_FACING_HEADING, USER_FACING_SHORT_STAGE, LEGACY_INPUT_ALIAS, INTERNAL_IDENTIFIER, ORDINARY_PROSE, HISTORICAL_REPORT_OR_TEST_FIXTURE, AMBIGUOUS.

Each occurrence: relative path, full-file SHA, language, form, exact value, bounded redacted context, stable anchor and intended action. Deduplicate overlaps. Required AMBIGUOUS occurrences block future Gate A.

## CRM read-only evidence

Open only /home/Carix/crm.db with URI mode=ro and PRAGMA query_only=ON.

Use lstat/nofollow/stable identity/full SHA, quick_check, bounded schema discovery through explicit table/column alias allowlists and exact UA-0001..UA-0009 queries. Return only sanitized proven stage, catalog identity, container/tracking, diagnostics and CTA fields. No wildcard unrelated rows, ATTACH, VACUUM, mutable PRAGMA or writes. Require DB identity/size/mtime/SHA unchanged after close. Missing/ambiguous schema returns BLOCKED, never invented values.

## Mandatory tests

Standard-library unittest only:

- all exact RU/UA status/long/heading/short mappings;
- status «В море» -> «На пароме»;
- proven short «Море» -> «Паром»;
- data-ru + data-uk simultaneously;
- previously failing <span>В море</span> classification;
- nested/one-line HTML;
- ordinary phrases unchanged: «Автомобиль в море уже 20 дней», «Море волнуется, паром в порту», «Отдых на море»;
- script/style/comment/legacy aliases unchanged;
- quote/void/uppercase/end-tag/entity and internal-marker preservation;
- ambiguous «Море» blocks;
- exact registry has video/katalog.html and no video/public/catalog.html;
- path escape, parent/final symlink, hardlink, oversize, truncation, simulated TOCTOU block;
- secret redaction/final scan;
- strict single JSON on failures;
- CRM exact nine, schema ambiguity/missing, quick_check, read-only, unchanged SHA/identity;
- compile, 10-run determinism and idempotence.

No skipped or expected-failure tests.

## Deliverables

Create exactly:

- `cloud/task_047_ferry_discovery/README.md`
- `cloud/task_047_ferry_discovery/transform.py`
- `cloud/task_047_ferry_discovery/discover.py`
- `cloud/task_047_ferry_discovery/tests/test_transform.py`
- `cloud/task_047_ferry_discovery/tests/test_discover.py`
- `cloud/task_047_ferry_discovery/run_tests.py`
- `cloud/task_047_ferry_discovery/TASK_047_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Finish: READY_FOR_CODEX_PHASE1_AUDIT. Do not claim real discovery, Gate A, production completion or UA-0009 readiness. UA0009_SAFE_TO_PUBLISH remains NO.