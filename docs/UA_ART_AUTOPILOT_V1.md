# UA ART AUTOPILOT V1

## Goal
Create a controlled automation bridge between ChatGPT, Claude/Cloud and PythonAnywhere with minimal owner actions.

## Roles
- ChatGPT: defines the task, reviews reports, issues the next technical specification, and closes the task.
- Claude/Cloud: writes or revises code according to the current task specification and saves its output in `cloud/`.
- PythonAnywhere runner: pulls the repository, validates allowed changes, creates backup, runs sandbox/tests, applies only allowed changes, rolls back on failure, and writes a report to `python/`.
- Owner: intervenes only for visual approval or CRITICAL actions.

## Modes
### READ_ONLY
Automatic. No production writes.

### SAFE_PATCH
Automatic only when all of the following are true:
1. backup PASS
2. whitelist PASS
3. sandbox PASS
4. tests PASS
5. unexpected changes = 0
6. rollback path verified

### CRITICAL
Never auto-apply. Stop at `WAITING_OWNER_APPROVAL` for:
- CRM database writes or schema changes
- journal mode changes
- mass card regeneration
- deletes
- production publication
- generator-wide changes
- any change affecting multiple existing production cards

## Iteration loop
Maximum 10 rounds per task.

1. ChatGPT writes `tasks/task_NNN.md`.
2. Cloud writes code/response to `cloud/`.
3. PythonAnywhere executes validation and writes `python/report_NNN.txt`.
4. ChatGPT reads report and either:
   - writes next task round,
   - requests OWNER_VISUAL_CHECK,
   - requests OWNER_APPROVAL,
   - or marks TASK_CLOSED.
5. Stop automatically after 10 rounds if unresolved.

## Mandatory safety
- Never store passwords, API keys, Telegram tokens, GitHub tokens, PythonAnywhere tokens or `crm.db` in this repository.
- Never upload customer personal data.
- Never modify files outside an explicit whitelist.
- Every production change requires a pre-change backup manifest.
- Every failed SAFE_PATCH must rollback automatically.
- Existing UA-0001...UA-0008 must be checked for unexpected change before and after tasks related to cards/site.
- UA-0009 and every new card must be tested in sandbox before publication.

## CPU protection
If PythonAnywhere CPU quota used is >= 85%, heavy jobs must stop with:
`DEFERRED_CPU_LIMIT`

No heavy sandbox, mass SHA walk, media conversion, or regeneration should start above the threshold.

## Standard report
Every PythonAnywhere report must end with:

TASK_ID:
ROUND:
MODE:
BACKUP: PASS/FAIL
WHITELIST: PASS/FAIL
SANDBOX: PASS/FAIL
TESTS: PASS/FAIL
PRODUCTION_CHANGED: YES/NO
FILES_CHANGED:
UNEXPECTED_CHANGES:
ROLLBACK: NOT_NEEDED/PASS/FAIL
CRM_INTEGRITY: PASS/FAIL/NOT_APPLICABLE
SITE_INTEGRITY: PASS/FAIL/NOT_APPLICABLE
UA_0001_0008_UNCHANGED: PASS/FAIL/NOT_APPLICABLE
UA_0009_READY: YES/NO/NOT_APPLICABLE
OWNER_VISUAL_CHECK_REQUIRED: YES/NO
OWNER_APPROVAL_REQUIRED: YES/NO
NEXT_ACTION:
STATUS: CONTINUE/WAITING_OWNER_APPROVAL/WAITING_VISUAL_CHECK/TASK_CLOSED/STOPPED

## Owner interaction policy
Owner should normally receive only one of:
- `VISUAL CHECK: <one URL> — answer YES/NO`
- `CRITICAL APPROVAL: <short description> — answer APPROVE/CANCEL`
- `TASK CLOSED`

## Current priority
Stabilize CRM/SQLite and safely prepare UA-0009 without changing existing production cards unexpectedly.
