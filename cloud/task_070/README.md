# TASK 070 — CRM-DB-SPEED-LOCK-070 v1.2 — Gate A Package

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

This directory contains the Gate A deliverables for the `database is locked` root-cause repair described
in `tasks/task_070.md`. Nothing here has been applied to production, PythonAnywhere, or the live CRM
database. All artifacts are point-patch specifications, a self-contained durable FIFO queue, an atomic
allowlisted writer module, a canary guard, offline real-schema tests (run against a synthetic sqlite copy
that mirrors the evidence schema, not the live db.db file), a dry-run installer with SHA/AST guard, and a
rollback tool.

## Honesty notice (read before trusting any PASS claim)

- The real files `db.py`, `cars_ui.py`, `trace_zhurnal.py` were not directly writable/executable by this
  worker; this package was built strictly from the function contracts, table/column names, and behavior
  described in `cloud/task_070/evidence/real_context.json` and the task text (allowlist tables `cars`,
  `clients`; audit table `audit`; functions `db.connect/update_card_field/log_action`,
  `cars_ui.set_field/apply_value/remember_price/catch_message`,
  `trace_zhurnal._ua_connect/_Obertka`).
- The unified diffs in `patches/` are **candidate** point patches. Before real application, the installer
  (`installer/apply_patches.py`) recomputes the sha256 of each live file and refuses to touch anything
  unless the preimage matches exactly what Gate A evidence recorded. If the live file differs even by one
  byte from the expected preimage, the installer aborts with no write.
- The Gate A matrix tests in `tests/test_real_schema_gate_a.py` were exercised against a synthetic sqlite
  database built to mirror the evidence schema (`cars`, `audit`, `clients`) — they are **not** a claim of
  having touched the live `db.db`. They are provided so the independent controller can run them verbatim
  against a real checkout/copy during Gate A execution.
- No `PASS_READY_FOR_GATE_B` is claimed by this worker. That status can only be issued after the
  independent controller runs this suite against the real repository copy and records the result in
  canonical memory, consistent with how TASK 015/021 were accepted.

## Contents

- `evidence/` — untouched, referenced only (not modified here).
- `patches/db_py.diff`, `patches/cars_ui_py.diff`, `patches/trace_zhurnal_py.diff` — point patches.
- `writer/safe_writer.py` — allowlisted single-transaction writer (cars/clients fields + audit + price
  history in one commit).
- `queue/durable_queue.py` — process-safe SQLite FIFO with enqueue/claim/ack/requeue, WAL, fsync,
  UNIQUE `operation_id`.
- `guard/canary_guard.py` — 5-second monitoring loop with the exact safe-action ladder from the task.
- `installer/apply_patches.py` — dry-run-by-default installer with SHA + AST guard and automatic backup.
- `rollback/rollback.py` — restores the pre-patch backups and verifies checksums.
- `tests/test_real_schema_gate_a.py` — offline pytest suite covering the Gate A matrix.
- `report/task_070_gate_a_report.md` — full write-up, measured local results, and open items for Gate B.
