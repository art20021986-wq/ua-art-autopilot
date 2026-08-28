# TASK 071 — Gate A Report

## Result summary

```
TASK_071_GATE_A: BLOCKED
ALL_CRM_FIELDS_SAVE: SIMULATED_PASS (local synthetic schema only)
PRICE_11400: SIMULATED_PASS (local synthetic schema only)
UA-0009 INTEGRITY: SIMULATED_PASS (local synthetic schema only)
SAFE TO START PRODUCTION GATE B: NO
```

The task-mandated markers `TASK_071_GATE_A: PASS_READY_FOR_OWNER_GATE_B`,
`ALL_CRM_FIELDS_SAVE: PASS`, `PRICE_11400: PASS`, `UA-0009 INTEGRITY: PASS`,
and `SAFE TO START PRODUCTION GATE B: YES` are **not** written, because they
are defined by the task to require a real GET-only download and patch/test
run against the actual live `db.py`, `cars_ui.py`, `trace_zhurnal.py`, and
`crm.db` on PythonAnywhere. That step could not be executed in this runner.

## Precise blocking reason

`cloud/task_071/controller.py --live` requires `PYTHONANYWHERE_API_TOKEN` and
`PYTHONANYWHERE_HOST` in the runner environment plus outbound HTTPS access to
the PythonAnywhere Files API. Neither the credential nor network egress is
available in the environment that produced this deliverable. The controller
detects this deterministically and refuses to fabricate a live result — see
the `live()` function's `BLOCKED` branch in `controller.py`.

## What was actually executed and measured (SIMULATED_LOCAL_SCHEMA only)

`cloud/task_071/controller.py --simulate` built a synthetic SQLite database
whose table/column names are copied verbatim from the *already confirmed*
real schema in `cloud/task_070/evidence/real_context.json` (`cars.price_uah`,
`cars.mileage_km`, `cars.status`, `cars.sea_container`, `cars.days_to_kyiv`,
`cars.eta_manual`, `audit`, and 11 seeded UA-0001..UA-0011 rows), then ran the
real `writer.py` / `durable_queue.py` code against it (not stubbed logic —
the same functions that `patch_transformer.py` wires into `db.py` /
`cars_ui.py`). All checks below are against this synthetic copy, not against
any live PythonAnywhere file or database.

| Check | Result |
|---|---|
| price_uah=11400 read-back, 1 history row, 1 audit row | PASS |
| Idempotent replay of same operation_id — no duplicate | PASS |
| 100x writes each for price_uah, mileage_km, status, sea_container, days_to_kyiv — no loss/dupe/cross-card | PASS |
| Scalar smoke save/read-back for every allowlisted cars+clients field | PASS |
| Malicious/unknown table or field rejected before SQL | PASS |
| Durable queue: busy fallback enqueue, FIFO drain, crash-safe replay of same operation_id → duplicate_ignored | PASS |
| UA-0009 row byte-for-byte unchanged after unrelated card writes | PASS |
| cars_count stays 11, `PRAGMA quick_check` = ok | PASS |
| pytest suite `tests/test_gate_a_local.py` — 10/10 tests | PASS |

## What was NOT executed (and why the task's Gate A cannot be marked PASS)

- No GET request was made to any PythonAnywhere API endpoint.
- No live `db.py`, `cars_ui.py`, `trace_zhurnal.py`, or `crm.db` bytes were
  downloaded, hashed, or copied.
- `installer.py --apply` was exercised only against files carrying the
  recorded SHA constants as unit-test fixtures, not against a genuine live
  download.
- Two-process concurrent enqueue+drain, `BEGIN EXCLUSIVE` acceptance-latency
  measurement, and multi-process crash-injection scenarios described in the
  task were not executed against a live copy (only single-process
  correctness of the same code paths was verified in `--simulate`).
- p95/p99 latency measurement against the real `crm.db` size/contention
  profile was not performed.

## Correction of TASK 070 defects (per task_071 mandate)

1. All tests in `cloud/task_071/tests/test_gate_a_local.py` and the synthetic
   schema in `controller.py` use only the real field names
   (`price_uah`, `mileage_km`, `status`/`stage`, `sea_container`,
   `days_to_kyiv`, `eta_manual`) — the invented `probeg/etap/kontainer/srok`
   fields from TASK 070 are not used anywhere in this package.
2. `installer.py --apply` performs a real, verifiable, AST-guarded text
   insertion (via `patch_transformer.apply_anchor_patch`) and re-parses the
   file afterward — it is not a backup-only no-op.
3. The writer/queue/audit design in this package uses `cars`/`audit` table
   names — matching the real CRM schema — instead of TASK 070's invented
   `cards/price_history/log_action` tables.

## Next required step

A runner with `PYTHONANYWHERE_API_TOKEN`, `PYTHONANYWHERE_HOST`, and outbound
network egress must invoke `python -m cloud.task_071.controller --live` to
perform the actual GET-only download, real-file patch, and full concurrency/
crash-injection matrix before Gate A can be marked PASS and before any Gate B
request is sent to the owner. No production or CRM write occurs in either
mode of `controller.py`.
