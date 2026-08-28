# TASK 072 — CRM-DESCRIPTION-SAVE-072 v1.0

## Scope

This package implements a root-cause repair for the "description does not save" incident,
as a standalone module intended for `/home/Carix` on PythonAnywhere, plus a durable FIFO
queue sidecar, an installer with dry-run/apply/rollback, and offline call-path tests built
against a synthetic reference schema that mirrors the schema facts confirmed in TASK 071
evidence (`cars_count=11`, UA-0001..UA-0011, single UA-0009, `PRAGMA quick_check=ok`).

## IMPORTANT — why Gate A is BLOCKED, not PASS

This worker (Claude/Cloud) has **no network egress and no PythonAnywhere API credentials**
in this execution environment. The task requires:

1. GET-only download of the *real* live `db.py`, `cars_ui.py`, `trace_zhurnal.py`, schema
   modules and `crm.db` from PythonAnywhere into a temp runner folder.
2. Fresh full SHA + AST anchors computed on that *real* downloaded content, with fail-closed
   drift detection.
3. Patch application and testing against those *real* temporary copies.

None of step 1–3 can be executed here: this environment cannot reach PythonAnywhere, and the
task text only supplies **hashes** of `db.py` / `cars_ui.py` / `trace_zhurnal.py`, not their
actual source. A SHA+AST transformer cannot be safely constructed or validated against source
code that was never provided — doing so would mean guessing at real production code structure,
which this task explicitly forbids ("without drift, fail closed, without blind patch").

Therefore:

- All code below (writer, queue, installer, transformer harness) is fully implemented and
  ready to run.
- All call-path tests are run against a **synthetic reference implementation** that
  reproduces the two confirmed root-cause defects (car_wait lost on lock; multi-connection
  non-atomic write) inside this package, not against real live files.
- This is reported honestly as `GATE_A: BLOCKED — REAL_LIVE_ACCESS_UNAVAILABLE`, not as PASS.
- Nothing here touches production, CRM, or PythonAnywhere. No LLM tokens were used for any
  save-path logic (rule-based only).

## Files

- `live_controller.py` — GET-only downloader (requires operator to supply
  `PYTHONANYWHERE_API_TOKEN` / host / username via environment variables at real run time;
  contains no embedded credentials; not executed in this sandbox).
- `sha_ast_transformer.py` — generic SHA256 + AST-anchor verifier/patcher framework.
  Fail-closed on any hash or anchor mismatch. Operates only on local temp file paths.
- `writer.py` — standalone description-save module. Discovers real `cars`/`audit` columns
  at runtime via `PRAGMA table_info`, builds an allowlist dynamically, writes
  `condition_text` (canonical) with `description` legacy alias-on-input semantics, single
  transaction (SELECT + UPDATE + INSERT audit) on one connection/one commit, read-back
  verification, ≤0.8s direct budget, safe error mapping.
- `queue_sidecar.py` — durable FIFO sidecar SQLite queue with `operation_id` UNIQUE,
  last-intended-wins per card, crash-safe drain, idempotent apply.
- `installer.py` — dry-run/apply/rollback against **local temp copies only**. Refuses to run
  against any path containing `/home/Carix` unless `--i-understand-this-is-production=NO`
  is explicitly not set (defense in depth; this build never sets it).
- `tests/` — offline tests against the synthetic reference DB/module (see below).
- `GATE_A_REPORT.md` — full, honest Gate A status.
- `GATE_B_PLAN.md` — production plan, **not executed**.
