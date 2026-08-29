# TASK 081 technical report — UA-0013-PUBLISH-REPAIR-001 v1.0

## Status

BLOCKED for the live-evidence half of Gate A. Fully delivered for the
tooling/fix-design half.

## What was requested

Automatically diagnose why cars are not publishing, immediately set the
correct stage for UA-0013, fix the critical bug, and prevent recurrence for
future cards — under BACKUP -> fresh GET-only LIVE AUDIT -> SANDBOX/CANARY ->
GATE A, with production/CRM/site writes and restarts forbidden in this round.

## What could actually be verified in this round

This worker has no PythonAnywhere API token, no PythonAnywhere username, and
no outbound path to production or the public site from this environment.
Therefore:

- No GET request was actually made against PythonAnywhere or the public
  catalogs in this round.
- No SHA/AST evidence of the *real* `cars_ui.toggle_publish`,
  `publikaciya.opublikovat`, `stranica._ua_seo068_normalize`, or any other live
  file was collected.
- No real `crm.db` row for `UA-0013` was read.
- No real correct stage/category for UA-0013 was determined, because that
  determination is defined by the task to come only from the fresh live row
  plus approved logic — and no fresh live row was available.

Per protocol, none of that is claimed as done. The `CURRENT_STATUS` shared
memory block already records `ua0009_safe_to_publish: NO` and
`gate_a_executed: NO`; this task round does not change either fact, and does
not claim UA-0013 is safe to publish or that its stage has been corrected on
the live system.

## What was delivered

A complete, self-contained toolkit at `cloud/task_081_publish_repair/` that:

1. Performs the required GET-only audit the moment repo secrets
   (`PYANYWHERE_API_TOKEN`, `PYANYWHERE_USERNAME`, optional `PYANYWHERE_HOST`,
   `UA_SITE_BASE_URL`) are configured and `gate_a_workflow.yml` runs
   (`live_probe.py`).
2. Implements the exact two-defect root cause named by the owner and by the
   task (unconditional success in `toggle_publish`; ordering bug in
   `_ua_seo068_normalize`), with a deterministic, SHA-anchored patcher that
   fails closed on any drift between the audited source and the source it is
   about to touch (`patcher.py`).
3. Provides atomic backup/install/rollback primitives with mandatory
   read-back verification (`installer.py`), never invoked against production
   in this round.
4. Provides immediate + delayed postcheck for HTTP 200 on primary/diag,
   exactly-one occurrence per catalog, category presence, and protected-hash
   stability (`postcheck.py`).
5. Provides an orchestrating `controller.py` that is coded to refuse to ever
   print `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` unless a real live
   audit report file is present, so this package cannot be mistaken for a
   passed Gate A just because its offline fixtures pass.
6. Provides an offline fixture test suite (`tests/`) that reproduces, in
   isolation, both named defects and proves the fix logic prevents them,
   including compensating rollback, exactly-one-message behavior, and generic
   handling for any `UA-[0-9]{4,}` card (not hardcoded to UA-0013).
7. Provides `gate_a_workflow.yml` (GET-only; push-trigger scoped only to this
   task's own path, plus manual dispatch) and `gate_b_workflow.yml`
   (`workflow_dispatch` only, requires the exact literal token
   `UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED`, and additionally
   refuses to proceed unless a prior Gate A live-evidence file already
   exists).

## Blocker for full Gate A completion

`BLOCKER: PYTHONANYWHERE_CREDENTIALS_NOT_AVAILABLE_TO_WORKER.` The owner or
ChatGPT/Codex controller must configure `PYANYWHERE_API_TOKEN` and
`PYANYWHERE_USERNAME` (and optionally `PYANYWHERE_HOST`, `UA_SITE_BASE_URL`)
as GitHub repository secrets, then trigger `gate_a_workflow.yml`. Once that
run uploads a real `live_audit_report.json`, `controller.py` will either
emit `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` or a precise fail-closed
blocker derived from the real anchors/row/catalog evidence, and the correct
UA-0013 stage can be computed from the real row per the task's approved
logic (terminal/Georgia/Kyiv never rolled back; confirmed container signals
-> `sea_loaded`/"На пароме"/`more`; otherwise normalize only within the active
Korea-family canonical status/category).

## Merge note

This package continues and merges TASK 073, TASK 077, and TASK 079 as
instructed: it does not introduce a second publisher or a second ETA writer.
All publish-time bundle construction, diagnostic placeholder creation, and
install/rollback logic route through the single existing publisher/toggle
path (`cars_ui.toggle_publish` -> `publikaciya.opublikovat` /
`sobrat_kartochku`), patched in place rather than duplicated.

## Runtime LLM tokens

0 — all tooling in this package is deterministic Python with no LLM calls at
runtime.
