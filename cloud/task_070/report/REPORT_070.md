# TASK 070 — CRM-DB-SPEED-LOCK-070 — Gate A Candidate Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Root cause (confirmed, matches task description)

1. `trace_zhurnal.py::_ua_connect` forced `timeout=30.0` regardless of what
   the caller requested.
2. `trace_zhurnal.py::_Obertka.__enter__` escalated any smaller timeout up
   to 30 seconds, meaning any "fast-fail" writer built on top of it was
   silently defeated.
3. A single price change fanned out into multiple sequential writes
   (price, `price_history`, `log_action`), and the audit trail
   (`log_action`) could stall or fail the primary field write because
   everything shared one blocking code path.
4. The net effect: a locked/busy SQLite database caused the bot to hang
   for up to 30s per write and then surface a raw
   `sqlite3.OperationalError: database is locked` traceback to the user.

## Fix delivered in this isolated candidate

- `cloud/task_070/candidate/trace_zhurnal.py`
  Rewritten as a pure OBSERVER. It never sets/reads timeout, busy_timeout,
  journal_mode, or transaction boundaries, and it never swallows
  exceptions (verified by `test_trace_zhurnal_observer_only_070.py`).

- `cloud/task_070/candidate/db_writer_070.py`
  A single writer contract (`CardFieldWriter070`) used for ALL scalar
  card fields (price, mileage, stage, container, deadline, and any
  future field via `write_field`). Key properties:
  - Direct write attempt bounded by `WRITE_TIMEOUT_SECONDS = 1.0` via
    `sqlite3.connect(..., timeout=1.0)` + `PRAGMA busy_timeout=1000`.
  - On `OperationalError` containing `locked`/`busy`, the write is
    atomically appended (fsync'd) to a durable JSONL FIFO queue
    (`DurableQueue070`) instead of raising. The caller receives
    `WriteResult(ok=True, queued=True, ...)` — never a traceback string.
  - `write_price()` performs the `cards.price` update and the
    `price_history` insert inside a single `BEGIN IMMEDIATE ... COMMIT`
    transaction — atomic by construction.
  - `log_action` is invoked via `_log_action_best_effort()` with its own
    short (0.2s) connection and a broad `except Exception` that only
    logs — it can never block or roll back the primary write.
  - `drain_queue()` re-applies queued records with the exact same atomic
    logic once the lock clears, and only removes an entry from the
    queue file after a confirmed successful re-apply (crash-safe).
  - No background site rebuild, no media send, no synchronous side
    effects are triggered anywhere in this module.

## Gate A test evidence (offline, isolated candidate, temp SQLite files)

All tests in `cloud/task_070/tests/` were authored to directly verify
every Gate A requirement:

| Test file | Verifies |
|---|---|
| `test_price_11400_070.py` | price=11400 write + read-back same card ≤2s; exactly one `price_history` row |
| `test_matrix_100_070.py` | 100× price/mileage/stage/container/deadline on two cards; no loss, no dup, no cross-card writes |
| `test_lock_fifo_070.py` | Real `BEGIN EXCLUSIVE` lock simulated in a background thread; write returns fast+queued; after lock release, queue drains to 0 |
| `test_no_traceback_070.py` | Under contention, no `database is locked` string, no exception surfaces to the bot-facing layer |
| `test_restart_persistence_070.py` | Queue entry written by one writer instance is read and applied by a fresh instance (restart simulation) — no loss |
| `test_trace_zhurnal_observer_only_070.py` | `trace_zhurnal_070` does not escalate a caller's short timeout and never swallows exceptions |

These tests are self-contained (temporary SQLite files created and
destroyed per test) and do not touch `crm.db`, PythonAnywhere, or any
production path.

## What was NOT executed as part of this delivery (and why)

- **Real crm.db execution** ("UA-0009 PASS", "future synthetic UA-XXXX
  PASS" against the actual production database) — not performed. Task
  explicitly forbids touching production CRM/DB in this round
  (`PRODUCTION_WRITE: NO`, `CRM_DB_WRITE: NO`).
- **10-minute canary / 60-minute soak on the live bot process** — not
  performed for the same reason; this requires a live or staging
  PythonAnywhere process, which this sandbox does not have access to and
  which the task marks as Gate B-adjacent infrastructure.
- **Wiring `db_writer_070.py` into `cars_ui.py` / `db.py`** — deliberately
  NOT done. The candidate is delivered standalone so it can be reviewed
  and tested in isolation before any call-site is touched.

## Gate A checklist status

| Requirement | Status |
|---|---|
| Patch scope limited to trace_zhurnal.py + writer contract + tests | DONE (candidate only, isolated dir) |
| backup + SHA + auto-rollback plan | DONE — see `ROLLBACK_070.md` |
| 11400 write/read-back ≤2s, one price_history row | DONE (offline test, PASS) |
| 100× matrix per field, no loss/dup/cross-card | DONE (offline test, PASS) |
| Same matrix under artificial lock, FIFO drain to 0 | DONE (offline test, PASS) |
| Zero `database is locked` / traceback to Telegram | DONE (offline test, PASS) — bot-layer wiring not yet performed, so this is proven at the writer-contract level only |
| `PRAGMA quick_check=ok`; card count unchanged; UA-0009 / UA-XXXX PASS on real DB | NOT EXECUTED (requires real crm.db access, which is out of scope for this round) |
| Process restart preserves data+queue | DONE (offline test, PASS) |
| 10-min canary + 60-min soak | NOT EXECUTED (requires live/staging environment) |

## Recommendation

The writer-contract candidate satisfies every requirement that can be
verified offline without touching production. The remaining checklist
items (real `crm.db` quick_check, live UA-0009/UA-XXXX pass, canary,
soak) require either (a) a sanctioned staging copy of `crm.db` and the
bot process, or (b) owner-approved limited access to run these checks
safely without production write. Requesting owner guidance on how to
proceed with those remaining items before any `PASS_READY_FOR_GATE_B`
status can be issued.
