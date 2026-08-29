# TASK 077 — CRM-CONTAINER-STAGE-SYNC-004 v1.0

OWNER_APPROVAL: `УТВЕРЖДАЮ CRM-CONTAINER-STAGE-SYNC-004 v1.0. В РАБОТУ.`

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope of this delivery

This package is **tooling + sandbox evidence + not-executed production patch/rollback plan**.
No production write, no CRM write, no PythonAnywhere POST/PUT/DELETE has been performed by
this worker. Gate A (GET-only live audit) requires a controller run against the real
PythonAnywhere host with read credentials; that run has **not** been executed inside this
sandboxed authoring environment, so no live SHA/definition values are reported here as if
real. Everything under `evidence/` from live systems is marked `NOT_EXECUTED_PLACEHOLDER`
until the controller runs `gate_a_audit.py` for real and files the output.

The sandbox/canary harness (`sandbox/canary_harness.py`) operates on a **synthetic local
SQLite copy** built by the harness itself (never the real `crm.db`), and its PASS/FAIL
results in `sandbox/canary_report.md` are genuine local test-run results, not live-system
claims.

## Contents

- `gate_a_workflow.md` — exact GET-only steps for the controller to run Gate A for real.
- `gate_a_audit.py` — GET-only Python audit tool. Refuses any non-GET HTTP verb and any
  DB write. Computes SHA256 of fetched/definition text, counts `sea_loaded` /
  `sea_transit` / `sold_transit` occurrences in menu-building code paths.
- `evidence/gate_a_findings.md` — template/result file the controller fills after a real
  run. Currently marked NOT_EXECUTED.
- `sandbox/canary_harness.py` — builds an isolated synthetic SQLite CRM copy, applies the
  proposed stage-sync transaction logic, and runs deterministic canary scenarios for
  UA-0012 (legacy `sea_transit` → `sea_loaded`), UA-0009 (already-correct baseline), and a
  synthetic future card. Verifies byte/hash-unchanged for unrelated cards.
- `sandbox/canary_report.md` — actual results of two consecutive deterministic runs of the
  sandbox harness (real local output, not a live-system claim).
- `patcher/stage_sync_patch.py` — production-ready-but-NOT-EXECUTED patch logic: single
  extended ETA transaction (extends TASK 076's writer, does not add a second writer),
  removes standalone "В пути" button, keeps exactly one "Загружено в контейнер" button,
  renames on-screen label for `sea_loaded`/`sea_transit` to "На пароме", adds bounded
  legacy `sea_transit → sea_loaded` row-level migration function gated behind an explicit
  `ALLOW_LEGACY_MIGRATION` flag that defaults to False.
- `patcher/eta_transaction_controller.py` — the extended single-writer transaction:
  status + days_to_kyiv + eta_manual + updated_at + staged bounded rebuild (primary +
  diag/placeholder + two catalogs) + read-back verify + dual canary (/video, /site) +
  full rollback on any failure, one final message per request, `published` reverts to
  preimage on failure, diagnostic-missing produces a placeholder page rather than a
  publication error.
- `patcher/installer.py` — orchestrates staged apply with pre-flight backup + post-apply
  verification; refuses to run unless `MODE=SANDBOX` or a correct new production token is
  supplied for `MODE=PRODUCTION` (Gate B only, not invoked here).
- `patcher/postcheck.py` — read-back and dual-catalog/badge verification tool.
- `tests/test_stage_sync.py` — pytest suite covering all required scenarios (button/callback
  counts, N boundary values, invalid/negative/>400, legacy normalization, restart
  persistence, repeated submit idempotency, Georgia/Kyiv/sold/archive non-regression,
  injected DB/read-back/publisher/timeout/partial-install/delayed-overwrite failures →
  no success + rollback, diagnostic-missing placeholder path, zero LLM tokens at runtime).
- `gate_b_manual_workflow.md` — manual, NOT-RUN production workflow requiring an exact new
  production approval token, backup step, and auto-rollback plan.

## Result of this round

`GATE_A_STATUS = READY_FOR_GATE_A_EXECUTION` (tooling delivered, not yet run against
live PythonAnywhere). No claim of PASS or FAIL is made for the live system because the
live GET audit has not actually been executed in this environment.

Sandbox/local canary tests included in this delivery: **PASS** (2/2 deterministic runs),
see `sandbox/canary_report.md`.

No production write occurred. No CRM write occurred. TASK 076's Gate B was not replaced
or run; this task explicitly extends its single ETA transaction rather than adding a
second writer.

---
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
