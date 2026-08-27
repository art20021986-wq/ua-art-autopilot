# TASK 039 — independent Codex repair and controller audit

## Result

The first generated TASK 039 package was not accepted. Independent execution
found 5 failures and 8 skipped tests, and the proposed workflow contained a
controller placeholder that always exited without contacting PythonAnywhere.
No production, CRM or database action occurred during that failed audit.

Codex repaired the package and reran it using only the standard library.
The final result is 76 tests passed, with zero failures, errors, skips or
resource warnings. All Python files compile.

## Repaired discovery

bot_logistics_discovery.py now:

- accepts exactly the six approved /home/Carix source paths and exactly
  /home/Carix/crm.db; an unapproved database path is rejected before reading;
- uses no-follow, regular-file, single-link, size, inode/device, nanosecond
  timestamp and SHA-256 checks;
- opens SQLite with URI mode=ro and PRAGMA query_only=ON;
- executes only traced SELECT and PRAGMA statements;
- checks quick_check, data_version, file identity and SHA before and after;
- checks every bounded table and candidate ID/container column combination
  with parameterized exact identities, never wildcard UA matching;
- blocks missing rows, multiple rows, multiple tables and multiple container
  columns;
- relays structural match metadata but never the current container value;
- captures bounded menu/handler context for duplicate and canonical controls;
- redacts secret-, token-, email-, phone-, VIN- and container-shaped lines;
- emits exactly one strict JSON object for both PASS and BLOCKED.

## Repaired tests

The import shape now loads the real TASK 037 modules as a package, so the
container update tests cannot silently skip. The ambiguous-row regression
creates a deliberately non-unique table, requires the exact GateBRefused
exception, proves no result was returned, proves byte-identical database
state, and proves both values stayed unchanged.

The suite also proves:

- exactly one centralized logistics entry in the main menu and card editor;
- old duplicate labels are absent;
- the hub exposes stage, container/date, days and back navigation;
- callbacks fit Telegram limits;
- ETA uses one canonical calculation;
- ONEYSELGF1046602 is accepted exactly;
- deterministic transforms and exact one-row container updates;
- field preservation, rollback and other-row preservation;
- exact source and DB whitelists, link/size/concurrent-change refusal,
  strict JSON, redaction, exact IDs and read-only executed SQL.

## Real PythonAnywhere controller

pythonanywhere_discovery_controller.py now contains a real standard-library
PythonAnywhere REST transport. It is no longer a placeholder.

Before any trigger it:

1. runs compile plus the complete offline test suite;
2. computes hashes for the discovery script, both tests and controller;
3. validates the real safe-inbox sync manifest and all safety flags;
4. binds every local hash to its exact remote path;
5. downloads the exact remote discovery script and verifies its bytes.

It then deletes only the exact stale safe-inbox receipt, creates one temporary
always-on task with a scheduled fallback using one fixed command, polls only
that receipt, validates bounded strict JSON, relays PASS or BLOCKED without
changing the status, and removes the trigger and receipt in finally.

The transport rejects arbitrary paths, arbitrary commands, other accounts,
other hosts and unsafe receipt fields. It has no method for production file
upload, web-app reload, bot restart, Gate B, or CRM mutation.

## Workflow

task037_discovery_workflow.yml.example parses as YAML and is ready to install
as .github/workflows/task037_discovery.yml. It triggers only when that
installed workflow changes or by manual dispatch, runs compile/tests first,
runs the real controller, stages exactly two relay artifacts, and uses bounded
non-destructive push retries.

## Safety state

- PRODUCTION_TOUCHED: NO
- CRM_TOUCHED: NO
- CRM_DB_WRITTEN: NO
- GATE_B_EXECUTED: NO
- UA_0009_PUBLISHED: NO

Terminal state: READY_FOR_SAFE_INBOX_SYNC_AND_READ_ONLY_DISCOVERY.

The first real read-only receipt safely returned BLOCKED because a generic
container anchor exceeded the bounded result limit in cars_ui.py. The retry
removes that generic anchor, keeps exact UI labels and logistics identifiers,
and adds a regression with 200 irrelevant container references. It remains
read-only and does not weaken any file, database or receipt bound.

The second receipt proved the real CRM aliases auto_number and sea_container.
The next read therefore adds only that proven UA identity column and targeted
handler identifiers (card/edit/stage, eta_days, sea_container, sea_date_out
and related callbacks). A real-schema regression requires UA-0006 to resolve
through auto_number while preserving every other field.
