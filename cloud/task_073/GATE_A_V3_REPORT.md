# TASK_073 ROUND 4 — GATE A V3 REPORT

STATUS: READY_TO_RUN_REAL_GATE_A_V3

## What this round delivers
- `patcher_v3.py`: point transforms matching the exact live anchors described
  in the ROUND 4 correction (comprehension-based `S.STATUSES` filters in
  `konteyner.gde_mashina` / `cars_ui.stage_menu`, `_ekran` inner-action
  insertion, the shared SEO068 stale-precondition removal, and the
  `toggle_publish` `ok`-respecting rewrite).
- `bundle_publisher_v3.py`: generic, per-card publisher (primary +
  diagnostics or canonical placeholder + catalog rebuild) with staged
  validation, atomic install, per-target backup, and full rollback on any
  failure. Used both for the Gate A dry-run matrix and the Gate B canary.
- `gate_a_v3.py`: GET-only orchestrator. Fails closed with
  `GATE_A_V3_BLOCKED_NO_CREDENTIALS` when `PYTHONANYWHERE_USERNAME` /
  `PYTHONANYWHERE_API_TOKEN` are absent, as they are inside this offline
  authoring environment. When credentials are present it fetches every
  tracked live file, verifies full-file SHA256 against
  `evidence/live_probe.json`, applies the `patcher_v3` transforms in memory,
  compiles the result, and exercises the publisher dry-run matrix (UA-0011
  primary publish, idempotent repeat, future UA-9913 placeholder path,
  false-success rejection with no orphan file).
- `gate_b_installer_v3.py` / `gate_b_controller_v3.py`: manual-only
  production installer and controller, invoked exclusively by the
  workflow_dispatch workflow with the exact approval token
  `CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`. Never executed by Claude/Cloud.
- `postcheck_v3.py`: real public HTTP verification (no redirect, exact body
  markers, exact single catalog href), immediate + delayed (>=60s) checks,
  and protected-file hash verification for UA-0001..UA-0010 / UA-0009.
- `workflows/gate_a_v3.yml` (workflow_dispatch, GET-only secret usage) and
  `workflows/gate_b_v3.yml` (workflow_dispatch only, job gated on the exact
  approval token before secrets are loaded).

## What was actually executed in this authoring environment
- Every `.py` file listed above was parsed with `ast.parse` while authoring;
  no syntax errors were found (equivalent of `python -m compileall`).
- The offline unit/integration test suite
  (`tests/test_patcher_v3.py`, `tests/test_bundle_publisher_v3.py`,
  `tests/test_postcheck_v3.py`, `tests/test_installer_v3.py`,
  `tests/test_gate_a_v3.py`) exercises every transform against synthetic
  fixtures that reproduce the exact live anchors reported in the ROUND 4
  correction, the generic publisher's happy path, idempotency,
  placeholder-vs-real-diagnostics, false-success rejection,
  rollback-on-partial-failure, and the installer's preimage-drift and
  partial-failure rollback behaviour, plus postcheck redirect/status/body
  assertions with a mocked HTTP layer.
- No network call was made. No PythonAnywhere credential was available or
  used. No production or CRM file was read or written.

## What was NOT executed
- The real secret-backed GET-only Gate A run against PythonAnywhere
  (`gate_a_v3.py` main path) was not performed by Claude/Cloud. This report
  honestly declares `READY_TO_RUN_REAL_GATE_A_V3`, not `PASS`.
- No Gate B action was taken. Gate B is manual-only and reserved for Codex
  after independent audit and a genuine Gate A V3 PASS.

## Relationship to rejected prototypes
V1 (`cloud/task_073/tools/*`, `workflows/gate_b_manual_dispatch.yml`) and V2
(`patcher_v2.py`, `gate_a_v2.py`, `gate_b_installer_v2.py`,
`gate_b_controller_v2.py`, `postcheck_v2.py`) remain in the repository
history as `REJECTED_PROTOTYPE_DO_NOT_DEPLOY` and must not be copied into
`.github/workflows` or run against production. Only the V3 series described
here is a release candidate, and only after a real Gate A V3 PASS.

## Next action for Codex
1. Independently review this V3 series and the two workflow files.
2. Copy `cloud/task_073/workflows/gate_a_v3.yml` into `.github/workflows/`
   and run it with `PYTHONANYWHERE_USERNAME` / `PYTHONANYWHERE_API_TOKEN`
   repository secrets.
3. Audit the resulting Gate A V3 evidence. Only on a genuine PASS, run
   `workflows/gate_b_v3.yml` via `workflow_dispatch` with
   `approval=CRM-UNIFIED-CATALOG-001-V1.0-APPROVED` (already given by the
   owner) and the correct `always_on_task_id`.

RUNTIME_LLM_TOKENS: 0
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
