# TASK 071 — CRM-ALL-FIELDS-WRITE-071 — Package Overview

## Scope delivered in this package

This package implements, as pure offline code artifacts, the point-fix design required by
TASK 071 to remove the multi-connection / multi-commit / unbounded-timeout root cause behind
CRM field-save failures (including the `price_uah=11400` reproduction case):

1. `patch_transformer.py` — deterministic, SHA-gated, AST-anchor-guarded point patch
   generator/applier for `db.py`, `cars_ui.py`, `trace_zhurnal.py`. Refuses to touch any file
   whose SHA256 does not exactly match the SHA recorded in
   `cloud/task_070/evidence/real_context.json`. Never rewrites a whole file — only inserts a
   bounded, anchored block at a verified AST location and asserts the file still parses after
   the edit.
2. `installer.py` — dry-run/apply installer that operates ONLY on local temporary copies
   (never on any live path). Produces a diff, a backup, and an apply/rollback pair.
3. `writer.py` — the single real writer for `cars`/`clients`. Table and field are resolved
   only through a hard-coded allowlist built from the real schema names confirmed in
   `cloud/task_070/evidence/real_context.json` (`price_uah`, `mileage_km`, `status`
   with legacy alias `stage`, `sea_container`, `days_to_kyiv`, `eta_manual`, plus a small
   `clients` allowlist). One UPDATE + one audit INSERT + (for `price_uah`) one embedded
   `price_history` JSON update happen inside a single transaction and a single commit/
   connection. No second `remember_price` call is issued after an atomic price write.
4. `durable_queue.py` — a process-safe, crash-safe FIFO SQLite queue used only when the
   direct write budget (≤0.8s) is exceeded on `locked`/`busy`. Enqueue is followed by an
   immediate `"Принято, сохраняю"` acknowledgement; `"Сохранено"` is only emitted after a
   committed drain. Idempotency is enforced by a unique `operation_id`, so a crash between
   CRM commit and queue ack cannot create a duplicate audit/price_history row and cannot let a
   stale queued value overwrite a newer committed value (queue drain re-checks the current
   row version before applying).
5. `controller.py` — the independent Gate A controller/workflow described in the task. It is
   written to: fetch the live files via **GET-only** PythonAnywhere API calls, hash-verify them
   against the recorded SHA, make local temporary copies of source + `crm.db`, apply the patch
   to the temporary copies only, AST-compile/import the patched copies, and run the full call-
   path test matrix (100x per real field, concurrency, crash-recovery, malicious-field
   rejection, UA-0009 integrity, canary protection, p95/p99 timing, rollback).
6. `rollback.py` — restores the pre-patch backup of the temporary copies and truncates any
   test-only queue rows; does not touch anything outside the runner's temp directory.
7. `tests/test_gate_a_local.py` — an offline pytest suite that exercises `writer.py` and
   `durable_queue.py` against a synthetic SQLite schema whose table/column names mirror the
   real schema recorded in `cloud/task_070/evidence/real_context.json` (`cars`, `audit`,
   `price_uah`, `mileage_km`, `status`, `sea_container`, `days_to_kyiv`, `eta_manual`,
   `UA-0001..UA-0011`). This corrects the TASK 070 defect of testing invented
   `probeg/etap/kontainer/srok` fields and invented `cards/price_history/log_action` tables.

## Why Gate A is reported BLOCKED, not PASS

`controller.py` is written to perform the real GET-only download of live `db.py`, `cars_ui.py`,
`trace_zhurnal.py`, and `crm.db` from PythonAnywhere, exactly as TASK 071 requires. This
execution environment (the sandbox that produced this response) has **no PythonAnywhere API
token and no network egress to pythonanywhere.com**. Without that credential/egress, the
controller cannot legitimately claim it downloaded, hashed, or patched the real live files, and
it cannot claim the 100x-per-field / concurrency / crash-recovery matrix ran against a real copy
of the live `crm.db`.

To avoid fabricating Gate A evidence (explicitly forbidden by the task and by the operating
rules of this bridge), this package instead:

- ships all code fully implemented and unit-tested against a **synthetic schema built from the
  already-confirmed real field/table names** (`cloud/task_070/evidence/real_context.json`), and
- reports the *local* simulation results honestly in `GATE_A_REPORT.md`, clearly labelled
  `SIMULATED_LOCAL_SCHEMA`, separate from the *required* live-file Gate A run, which is marked
  `NOT_EXECUTED — BLOCKED (no PythonAnywhere API credential/network egress in this runner)`.

The next runner that has a configured PythonAnywhere API token and outbound network access can
run `python cloud/task_071/controller.py --live` unmodified to perform the real GET-only Gate A
run described by the task, using the exact same writer/queue/patch code validated here.
