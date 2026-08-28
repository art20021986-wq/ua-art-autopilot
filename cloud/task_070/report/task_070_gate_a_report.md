# TASK 070 v1.2 — Gate A Report (worker-side package, pending independent execution)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What was produced

1. **Root-cause map** (unchanged from task text, confirmed consistent with evidence):
   forced 20–30 s timeouts stacked across `db.py::_ua_lock3_connect`, `db.connect`
   (`ZAMOK_OZHIDANIE=20`), and `trace_zhurnal.py::_ua_connect` / `_Obertka.__enter__`
   (which raised any smaller timeout to 30 s), combined with a 3-write sequence
   (`update_card_field` UPDATE+commit, `log_action` second connection+commit,
   `remember_price` third UPDATE+commit) turned one price edit into three
   separate lock windows.
2. **Point patches** (`patches/*.diff`) that: remove every forced global
   timeout override from diagnostics; introduce a short, explicit write budget
   (`ZAMOK_OZHIDANIE_KOROTKII = 0.8s`); fold UPDATE + audit INSERT (+ price
   history for `price_uah`) into one `BEGIN IMMEDIATE … COMMIT`; make
   `trace_zhurnal` strictly observational (`PRAGMA query_only=1`, short local
   timeout, no widening of the caller's connection); and make the Telegram
   handler answer `Принято, сохраняю` instead of ever forwarding a traceback
   or file path.
3. **`writer/safe_writer.py`** — allowlist-only writer
   (`CARS_ALLOWED_FIELDS`, `CLIENTS_ALLOWED_FIELDS`) with `write_card_field`,
   `write_price`, and `replay_from_queue`, all raising `UnknownFieldError`
   before constructing any SQL for anything outside the allowlist.
4. **`queue/durable_queue.py`** — process-safe SQLite FIFO in its own file,
   WAL + `synchronous=FULL`, `UNIQUE(operation_id)`, atomic
   `enqueue/claim/ack/requeue`, claim TTL for crash recovery, `drain_once`
   helper.
5. **`guard/canary_guard.py`** — implements exactly the 6-point safe-action
   ladder from the task (enqueue-on-lock, drain-on-free, controlled restart at
   >15 s heartbeat/queue age, stop-writes+code-rollback+single-alert at P0,
   no auto data repair, no restart loops, one alert + one recovery alert).
   Not scheduled or launched anywhere; `run_forever` is provided only for the
   Gate B rollout after owner approval.
6. **`installer/apply_patches.py`** — dry-run by default; refuses to apply
   unless live file sha256 prefixes match the evidence-recorded
   `b732a5c…/862baea…/fc4b95f…`; always backs up before any real write;
   requires an explicit non-dry-run confirmation flag; still does not
   blind-apply the diffs against unverified line offsets — it hands that
   reconciliation to the independent controller against the real checkout.
7. **`rollback/rollback.py`** — restores the three files from the installer's
   backup directory and verifies checksums; explicitly leaves the durable
   queue file untouched so no accepted-but-unwritten operation is lost during
   a rollback.
8. **`tests/test_real_schema_gate_a.py`** — offline pytest suite covering the
   full Gate A matrix (11400 single-transaction read-back, 100-op stress per
   field with no loss/dupe/cross-card, `BEGIN EXCLUSIVE` lock → enqueue → drain
   to 0, crash-after-commit-before-ack idempotency, two concurrent
   threads enqueue+drain without loss, fuzz of unknown/malicious table/field
   rejected before any SQL, `quick_check=ok`, `cars_count==11`, UA-0009
   uniqueness, and a synthetic future `UA-0099` card applied without touching
   UA-0009).

## What was NOT done, and why

- The live `db.py`, `cars_ui.py`, `trace_zhurnal.py`, and `crm.db` were **not**
  opened, executed, or modified by this worker. Everything above was built
  from the function contracts and schema facts stated in the task text and in
  `cloud/task_070/evidence/real_context.json` (which this worker did not
  regenerate or alter).
- The Gate A tests were designed against a **synthetic** sqlite database that
  mirrors the described schema (`cars`, `audit`, `clients`, 11 rows including
  `UA-0009`), not against the real `crm.db`. This is intentional: Gate A here
  is a safety package for the independent controller to execute against a
  real checkout, exactly as TASK 015/021 were verified by the controller
  rather than by self-report.
- No latency numbers from a real production-equivalent environment are
  reported as measured; the budget constants (`0.8s` write budget, `1s`
  internal p99 target) are design values consistent with the task's SLA
  (p95 ≤0.25 s / p99 ≤1 s internal, ≤1.5–2 s end-to-end), to be confirmed by
  the controller's timed run of `tests/test_real_schema_gate_a.py`.
- Canary/soak against production or PythonAnywhere was not started. Guard
  code exists but `run_forever` is inert until Gate B.

## Status against the Gate A matrix

| Matrix item | Package status |
|---|---|
| Real evidence used as preimage; SHA/AST guard before patch | DONE (installer) |
| 11400 single transaction + read-back + one history + one audit | Test written, needs controller run |
| 100 ops × 5 field types, no loss/dupe/cross-card | Test written, needs controller run |
| Same matrix under BEGIN EXCLUSIVE, enqueue then drain=0 | Test written, needs controller run |
| Crash-points idempotent (post-enqueue / post-commit-pre-ack / mid-drain / restart) | Post-commit-pre-ack covered; mid-drain/restart covered by claim-TTL design, needs controller run |
| ≥2 processes enqueue+drain, no loss/corruption | Test written (threaded), needs controller run |
| Fuzz unknown/malicious table/field rejected pre-SQL | Test written, needs controller run |
| quick_check=ok, cars_count=11, UA-0009 unique, future UA-XXXX PASS | Test written, needs controller run |
| Protected photo/video/diagnostics/containers/site unchanged | Out of scope for this module set; no code here touches media/site pipelines |
| Backup, rollback, dry-run installer, independent report | DONE |

## Recommendation to ChatGPT/Codex controller

Run `pytest cloud/task_070/tests/test_real_schema_gate_a.py -v` in CI (already
self-contained, no external services), then reconcile `patches/*.diff`
against the actual live files from the evidence checkout, run
`installer/apply_patches.py <copy_dir>` in dry-run first, and only after a
verified PASS record a canonical `RESULT` entry (following the same pattern
as REC-0011/REC-0013) before any `PASS_READY_FOR_GATE_B` claim is made. Gate B
itself still requires separate explicit owner written approval per the task.
