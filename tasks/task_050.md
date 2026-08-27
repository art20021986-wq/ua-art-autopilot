# TASK 050 — CORRECT TASK 047 RUNNER, SECRET SCAN, REAL UI COVERAGE AND INVENTORY

OWNER REQUEST: replace «В море» with «На пароме» across all 9 UA ART cards and every future card.
PARENT_TASK: task_047
MODE: SMALL_CORRECTION / NO_PRODUCTION_WRITE
MAX_ROUNDS: 3

## Independent Codex audit

Commit audited: 8d0b37bd62416e8587dd2dddef4ecedca6ddfe52.

Required command python3 run_tests.py fails before tests:

ImportError: Start directory is not importable: .../tests

Cause: unittest discovery uses top_level_dir while tests/ is not a package.

Direct fallback compile + unittest result:

- 48 tests;
- 47 PASS;
- 1 FAIL.

Failure: test_discover.TestSecretRedaction.test_scan_detects_secret.
scan_for_secrets('{"token": "abcdef123"}') incorrectly returns false.

## Further verified defects

1. discover_registry returns only file metadata and builds no occurrence inventory.
2. safe_read_file discards verified bytes before structural analysis.
3. CLI reports status OK even when required sources/CRM are blocked or evidence is incomplete.
4. CRM read path does not use full nofollow contract or before/after full SHA.
5. CRM chooses first table/id column, ignores ambiguity, accepts missing rows and fetchone hides duplicates.
6. Real UA ART snippets not covered:
   - <div class="chip">В море · Корея → Грузия</div>
   - <div class="etap tut"><div class="krug">2</div>Море: Корея → Грузия</div>
   - four-stage progress sequence Корея / Море / Грузия / Киев
   - «Море Корея → Грузия — около 60 дней»
   - «Море: Корея → Грузия»
7. transform does not recognize chip, etap/tut or the two route forms.
8. standalone «Море» outside known classes is silently ignored instead of inventoried AMBIGUOUS.

## Safety

No PythonAnywhere execution. No production, CRM, database, site, card or generator write. No UA-0009 publication, restart, schedule change or Gate B.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Corrections

### Runner

Make python3 run_tests.py work from any cwd. Make tests importable or remove invalid top_level_dir. Compile every package/test Python file, run determinism/idempotence and all tests, nonzero on failure.

### Secrets

Detect and fully redact plain and JSON forms:

- token=VALUE
- "token": "VALUE"
- api-key : VALUE
- password with safe whitespace/quotes.

Scan final serialized receipt. Do not flag ordinary safe keys such as status, sha256, container or tracking.

### Real UI mapping

Keep TASK 047 mappings and add only proven exact route forms:

- Море: Корея → Грузия -> Паром: Корея → Грузия
- Море Корея → Грузия — около 60 дней -> Паром Корея → Грузия — около 60 дней
- exact Ukrainian counterparts only when present.

Recognize chip as status/long context; etap tut as route-heading context while preserving nested krug; exact four-stage sequence as short RU context; data-ru/data-uk independently.

Do not globally replace «Море». Outside proven class/sequence/exact route phrase, preserve and inventory AMBIGUOUS.

Add literal one-line tests using all exact snippets.

### Structural inventory

Refactor verified read so complete verified bytes can be analyzed internally without serializing raw contents.

For every present HTML, structurally analyze visible text and data-ru/data-uk and return each target/ambiguous occurrence with:

- path and full SHA;
- language/form/classification;
- exact before/after;
- stable structural anchor;
- bounded redacted context;
- intended action.

For Python, parse/tokenize without import/execute. Inventory target string literals; prove alias-map/list literals as LEGACY_INPUT_ALIAS, proven renderer constants as USER_FACING, otherwise AMBIGUOUS. Never rewrite Python in this phase.

Overall BLOCKED if any required source is blocked, CRM is blocked, or required target is AMBIGUOUS. Missing optional files remain explicit MISSING.

### CRM

Use verified nofollow identity/size/mtime/full-SHA before and after SQLite mode=ro/query_only/quick_check.

- explicit bounded alias allowlists;
- not exactly one matching table blocks;
- not exactly one ID column blocks;
- exact parameterized UA-0001..UA-0009;
- require exactly one row per ID;
- duplicate/missing blocks;
- sanitized allowlisted fields only;
- full SHA/identity unchanged;
- include all safety markers.

### Tests

Keep prior tests and add:

- python3 run_tests.py success;
- JSON/plain secret detection/redaction;
- chip, etap tut, four-stage progress and info snippets;
- unrelated standalone «Море» preserved + AMBIGUOUS;
- discovery inventory contains exact occurrences;
- Python legacy literal preserved/classified;
- overall BLOCKED on required source/CRM/ambiguity;
- CRM multiple tables, multiple ID columns, duplicate/missing rows, quick_check failure simulation and SHA checks.

## Deliverables

Modify/create exactly:

- `cloud/task_047_ferry_discovery/transform.py`
- `cloud/task_047_ferry_discovery/discover.py`
- `cloud/task_047_ferry_discovery/tests/__init__.py`
- `cloud/task_047_ferry_discovery/tests/test_transform.py`
- `cloud/task_047_ferry_discovery/tests/test_discover.py`
- `cloud/task_047_ferry_discovery/run_tests.py`
- `cloud/task_047_ferry_discovery/TASK_050_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Finish READY_FOR_CODEX_PHASE1_REAUDIT. Do not claim real discovery, Gate A, production completion or UA-0009 readiness. UA0009_SAFE_TO_PUBLISH remains NO.