# TASK 039 — BOT-LOGISTICS-001 phase A2: repair false-green test and prepare automatic read-only discovery

## Authority and immutable safety boundary

Continue TASK 037 only. Work under `cloud/bot_logistics/`, plus `cloud/latest_status.md` and `cloud/owner_reply.md`.

Do not execute any PythonAnywhere action in this Claude worker. Do not modify Production, BOT CRM, `/home/Carix/crm.db`, site, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Do not execute Gate B. Do not touch `cloud/crm_speed_optimization/` or `tasks/`. Tests use temp dirs only and no network.

Required markers:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

The owner asked for autonomous completion. Prepare a controller and reviewed workflow template so Codex can launch the one read-only discovery without asking the owner to type commands.

## Independent Codex audit of TASK 037 commit c615fd069ef33d5ad9f95cf238468eb595b275b2

All four Python files compile.

Because pytest is absent from the independent controller runtime, Codex used a minimal semantics-compatible audit runner. Result:

```text
34 PASS
1 FAIL
35 total
```

Exact failing test:

`test_rollback_on_ambiguous_row_never_reports_success`

The fixture creates `cars.ua_id TEXT PRIMARY KEY`, then the test itself executes a second `INSERT ... UA-0006`. SQLite raises `sqlite3.IntegrityError: UNIQUE constraint failed: cars.ua_id` during test setup, before `update_single_container_row` is exercised. The function body then ends without an assertion. Therefore TASK_037_REPORT's claim that rollback-on-ambiguous-row was proven is false.

Also, source audit of `bot_logistics_discovery.py` found safety/completeness gaps that must be fixed before any live read:
- bounded source snippets are not actually secret-redacted;
- output is Python repr, not strict JSON;
- source reads have TOCTOU windows;
- exact six-source presence/uniqueness is not enforced;
- table discovery stops at the first heuristic match and can miss ambiguity across tables/columns;
- `LIKE '%0006%'` is not an exact UA identity rule;
- identifier quoting is incomplete;
- no bounded table/column/file-size limits;
- current command uses a relative repo path, but safe inbox execution requires an exact absolute script path;
- no independently validated GitHub→PythonAnywhere read-only controller exists for TASK 037.

Fix these executable defects, not only the report.

## 1. Repair and make the test suite zero-dependency

Replace `test_bot_logistics.py` with a standard-library `unittest` suite preserving all TASK 037 test coverage. Do not require pytest or any pip install.

The ambiguous-row regression must:
- build a separate temporary table whose UA identifier is deliberately non-unique;
- insert exactly two UA-0006 rows before measuring the pre-call database evidence;
- call the real `update_single_container_row`;
- assert exact `GateBRefused`;
- prove no row value and no DB bytes/state changed because of the refused call;
- prove no success result/message is possible;
- never fail during fixture setup.

Keep/prove all prior requirements: the exact ONEYSELGF1046602 validator, one hub entry in main and card menus, shared handler, duplicate labels absent, callbacks, back navigation, ETA, exact single-row update/read-back, idempotence, missing/ambiguous rollback, field preservation, quick_check, other rows unchanged, UA-0009 unchanged/not published, compile, 10-repeat determinism, backup/tamper/rollback, phase-A Gate B refusal and no media calls.

Controller command must be standard-library only:

```bash
python3 -m py_compile cloud/bot_logistics/*.py
python3 -m unittest discover -v -s cloud/bot_logistics -p 'test*.py'
```

No skipped/expected-failure tests and no background traceback.

## 2. Harden bot_logistics_discovery.py before live use

### Exact invocation contract

Require exactly this source set, once each, no duplicates or omissions:

- `/home/Carix/cars_ui.py`
- `/home/Carix/team_bot.py`
- `/home/Carix/avtoperedacha.py`
- `/home/Carix/db.py`
- `/home/Carix/run_all.py`
- `/home/Carix/start_safe.py`

Require DB exactly `/home/Carix/crm.db`.

The safe-inbox absolute command is:

```bash
python3.10 /home/Carix/autopilot_inbox/cloud/bot_logistics/bot_logistics_discovery.py --db /home/Carix/crm.db --source /home/Carix/cars_ui.py --source /home/Carix/team_bot.py --source /home/Carix/avtoperedacha.py --source /home/Carix/db.py --source /home/Carix/run_all.py --source /home/Carix/start_safe.py
```

### Secure reads and bounded evidence

- lstat + regular-file + nlink==1 + size cap;
- no-follow descriptor open where supported;
- fstat identity before/read/after and stable SHA;
- max six sources, bounded lines, bounded anchors/snippets, bounded SQLite tables/columns;
- no recursive scanning;
- read sources only, DB URI `mode=ro`, `PRAGMA query_only=ON`, `PRAGMA quick_check`;
- no SQL writes, mutable PRAGMA, ATTACH, VACUUM or migrations.

Source evidence must include enough sanitized anchor/function/callback context for the next exact transform. Redact entire lines containing case-insensitive secret/token/password/api-key/authorization/private-key/credential patterns or token-like shapes. Never merely claim redaction. The final JSON must be scanned against the same forbidden patterns before output.

### Exact UA-0006 discovery

- quote identifiers with a canonical double-quote helper;
- examine all bounded candidate table/id/container-column combinations;
- use parameterized exact identity values only, including proven representations such as `UA-0006`, `UA0006`, `0006`, and numeric 6 where type-compatible;
- never use `LIKE '%0006%'`;
- accept exactly one unambiguous table + row + ID column + container column;
- multiple candidate tables/rows/columns BLOCK with structural metadata only;
- missing match BLOCKS and returns sanitized bounded schema metadata for the next round;
- never output the current container string; output only `ALREADY_CORRECT` or `NEEDS_EXACT_UPDATE`;
- SHA/identity before and after must match exactly; concurrent production change BLOCKS.

### Strict JSON receipt

Stdout must be exactly one UTF-8 JSON object using `json.dumps(..., ensure_ascii=False, sort_keys=True)`, even on BLOCKED. No Python repr and no other stdout noise.

Required fields:
- `task_id: task_037`;
- `mode: READ_ONLY_DISCOVERY`;
- `status: PASS|BLOCKED`;
- `production_write: false`;
- `crm_write: false`;
- `db_write: false`;
- `ua0009_published: false`;
- bounded `sources`, `db`, `errors`;
- `UA0006_CONTAINER_STATUS` only when unambiguous.

Exit 0 only for PASS; nonzero for BLOCKED.

## 3. Prepare GitHub→PythonAnywhere controller

Create `pythonanywhere_discovery_controller.py`, standard library only. It will later run inside GitHub Actions, not in this task.

It must:
- accept only PythonAnywhere account `Carix` and host `www.pythonanywhere.com` or `eu.pythonanywhere.com`;
- read `PYTHONANYWHERE_API_TOKEN` from environment and never print it;
- verify local discovery script/test hashes and compile/tests before remote action;
- verify `/home/Carix/autopilot_inbox/_sync_manifest.json` is PASS, executed_remote_code=false, production_touched=false, and binds exact remote discovery-script SHA;
- allow only the exact command above;
- remove only one exact stale output path under `/home/Carix/autopilot_inbox/cloud/bot_logistics/`;
- create one temporary always-on task, with one-shot scheduled fallback, to execute the read-only command with stdout redirected to that exact safe-inbox output path;
- never invoke Gate B, bot restart, WSGI reload or any production write;
- poll only that exact output file;
- parse duplicate-key-rejecting strict JSON;
- validate every required safety field, allowed path, count, bound, SHA format, status, absence of secrets/PII and allowed container status;
- relay both PASS and safely BLOCKED evidence for the next task round without converting BLOCKED to PASS;
- write only local GitHub checkout artifacts:
  - `cloud/bot_logistics/evidence/task_037_discovery.json`
  - `cloud/bot_logistics/TASK_039_DISCOVERY_CONTROLLER_REPORT.md`;
- delete the temporary trigger and remote output in `finally`;
- fail closed on API/auth/rate-limit/timeout/malformed/stale/tampered output;
- never expose remote arbitrary file contents or other CRM rows.

Add offline controller tests with a fake PythonAnywhere API/opener proving PASS, discovery BLOCKED relay, stale receipt rejection, wrong SHA, malformed JSON, duplicate keys, secret-shaped output, wrong paths, timeout, trigger cleanup and zero production endpoints.

## 4. Reviewed workflow template

Create `task037_discovery_workflow.yml.example` under `cloud/bot_logistics/`. It must be ready for Codex to copy verbatim to `.github/workflows/task037_discovery.yml` after independent audit.

Requirements:
- runs on push to main only when that installed workflow file itself changes, and supports workflow_dispatch;
- permissions contents: write;
- concurrency cancel-in-progress false;
- checkout main with full history and no persisted credentials after checkout where practical;
- Python 3.11;
- run py_compile + unittest first;
- run controller with PythonAnywhere secret and exact fixed env;
- commit only the two allowed evidence/report paths;
- reject any unexpected staged path;
- fetch/rebase/push with bounded retries and never force-push;
- no production execution beyond the read-only discovery command;
- do not run Gate B.

## 5. Mandatory new tests

In addition to the repaired complete suite, prove:
- exact source set only (missing/duplicate/extra/path variant blocked);
- source symlink/hardlink/oversize/identity change blocked;
- secret-adjacent anchor line redacted;
- output strict JSON and single stdout object;
- exact UA identifiers, no LIKE;
- ambiguity across two tables blocked;
- ambiguity across two container columns blocked;
- DB/source SHA unchanged;
- no SQL write tokens in executed discovery path;
- controller sync-manifest hash binding;
- remote command exact equality;
- output path exact;
- controller never calls production file-write endpoints;
- cleanup always occurs;
- both PASS and BLOCKED safe receipts relay accurately;
- workflow template static safety markers and exact staged path allowlist.

## Deliverables

Exactly:
- `cloud/bot_logistics/bot_logistics_discovery.py`
- `cloud/bot_logistics/test_bot_logistics.py`
- `cloud/bot_logistics/pythonanywhere_discovery_controller.py`
- `cloud/bot_logistics/test_discovery_controller.py`
- `cloud/bot_logistics/task037_discovery_workflow.yml.example`
- `cloud/bot_logistics/TASK_039_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not modify `bot_logistics_transform.py` or `bot_logistics_gate_b.py` unless a real compile/test failure requires it; if so, report why and include it in FILES_CREATED.

## Finish status

Success means `READY_FOR_CODEX_CONTROLLER_AUDIT`, not discovery PASS and not Gate A PASS.

```text
TASK_ID: task_039
CLAUDE_STATUS: DONE
CURRENT_ACTION: READY_FOR_CODEX_CONTROLLER_AUDIT
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE
NEXT_FOR_CHATGPT: independently run standard-library tests, audit controller/workflow, install reviewed workflow, and monitor the one read-only PythonAnywhere discovery.
```
