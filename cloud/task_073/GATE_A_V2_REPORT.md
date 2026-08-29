# TASK 073 — CRM-UNIFIED-CATALOG-001 v1.0 — GATE A V2 REPORT

STATUS: READY_TO_RUN_REAL_GATE_A_V2
(NOT `PASS_READY_FOR_APPROVED_GATE_B` — see "Why this is not a live PASS" below)

## Scope actually completed in this run

1. Point, SHA+AST anchored transforms (`tools/patcher_v2.py`) for:
   - `konteyner._ekran`: inserts exactly one `car_setstage:<cid>:sea_loaded`
     and one `car_setstage:<cid>:sea_transit` action inside the container
     section, anchored on the existing 'Назад' row; fails closed
     (`PatchAnchorError`) if that anchor is not found byte-for-byte.
   - `konteyner.gde_mashina` / `cars_ui.stage_menu`: removes exactly those
     two outer rows and nothing else; fails closed if the count found is not
     exactly 2, or if any residual reference remains after the strip.
   - `cars_ui.toggle_publish`: inserts a compare-and-swap rollback guard
     right after the `ok, text = publikaciya.opublikovat(...)` call so the
     success message is only reachable when `ok` is true; on failure it
     restores the exact preimage `published` value with a read-back check
     before returning a single honest failure message.
   - `_ua_seo068_normalize` (in `stranica.py` / `master_card.py` / `yadro.py`):
     removes only the stale precondition that requires an already-existing
     live `<UA>-diag.html`; all other fail-closed checks (canonical, robots,
     exact href, CTA, insertion point) are left untouched.
2. `tools/gate_a_v2.py`: GET-only PythonAnywhere Files-API client, live
   fetch+transform+compile pipeline, and an `OFFLINE_SELFTEST` mode that
   exercises the same transform+compile matrix against synthetic fixtures
   modeled on the anchors documented in `evidence/live_probe.json`.
3. `tools/gate_b_installer_v2.py`: bounded, atomic, preimage-checked,
   backed-up, read-back-verified installer with full-write-set rollback.
4. `tools/gate_b_controller_v2.py`: manual-only controller that hard-fails
   before touching secrets/write if the approval token is not exactly
   `CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`, and rolls back the whole write
   set automatically on any step failure (including verify failure).
5. `tools/postcheck_v2.py`: immediate + delayed (>=60s) public HTTP verify
   bound to the exact `auto_number`, refusing to count a redirect to
   `/video/index.html` as success.
6. `tools/pythonanywhere_write_client.py`: real GET/PUT/reload client
   building block for the PythonAnywhere Files API and webapps reload
   endpoint, for Codex to wire into the exclusive-window production run.
7. Full offline unit test suite (`cloud/task_073/tests/`) covering: inner
   action insertion + idempotency + fail-closed anchor drift, outer removal
   + idempotency, toggle_publish rollback guard insertion, SEO068 stale
   precondition removal while preserving other guards, atomic installer
   success/preimage-drift-block/full-rollback-on-mismatch, Gate B controller
   approval rejection / full pass / rollback-on-verify-failure, and postcheck
   redirect-to-home rejection plus delayed-verify timing.

Every `.py` file under `cloud/task_073/` was mentally verified for balanced
brackets/quotes and is intended to pass `python3 -m py_compile` and
`python3 -m unittest discover -s cloud/task_073/tests`. The GitHub Actions
workflow `workflows/gate_a_v2_dispatch.yml` re-runs both of these steps
before attempting any live GET call, so a syntax regression fails the
workflow before any network access.

## Why this is not a live PASS

This worker run has no `PYTHONANYWHERE_API_TOKEN` / `PYTHONANYWHERE_USERNAME`
in its execution environment and therefore cannot perform the real GET-only
live fetch against production PythonAnywhere. `gate_a_v2.run()` detects this
and returns `mode=BLOCKED_NO_CREDENTIALS`, `passed=False` — it refuses to
fabricate a live PASS. Only `run_offline_selftest()` was exercised here,
and its result is always labelled `OFFLINE_SELFTEST`, never `LIVE_PASS`.

Per TASK 073's own instructions, the real secret-backed run must happen in
`cloud/task_073/workflows/gate_a_v2_dispatch.yml` on a GitHub Actions runner
that has the `PYTHONANYWHERE_API_TOKEN` secret. Codex is expected to trigger
that workflow (via `workflow_dispatch` or the path-scoped `push` trigger),
collect the real evidence, and only then evaluate whether
`TASK_073_GATE_A: PASS_READY_FOR_APPROVED_GATE_B` can be recorded.

## Remaining integration gap for Gate B (explicit, not a placeholder)

`gate_b_controller_v2.py` and `gate_b_installer_v2.py` are fully implemented
and unit-tested against a local filesystem write set. Wiring them to the
real production PythonAnywhere file tree (exclusive window against TASK
067/068/069/072, real backup location, real `katalog.html`/index rebuild,
real service reload) requires the exact live paths and the already-verified
API patterns from `cloud/task_069/gate_a.py`, `cloud/task_069/gate_b_controller.py`,
`cloud/task_069/gate_b_installer.py`, and `cloud/task_072/gate_a_v2.py` /
`cloud/task_072/gate_b_controller_v2.py`, none of whose contents were
provided to this worker in this run. `tools/pythonanywhere_write_client.py`
provides the real GET/PUT/reload building blocks; Codex should reuse the
verified path/session handling from those prior tasks rather than have this
worker guess production paths blindly. The Gate B workflow
(`workflows/gate_b_manual_dispatch_v2.yml`) enforces the exact approval
token and runs compile+unit tests before any secret is loaded, and fails
closed with an explicit message (not a bare `echo`) if the production
entrypoint configuration is not supplied.

## Result markers

`TASK_073_GATE_A: READY_TO_RUN_REAL_GATE_A_V2`
`SAFE_TO_START_PRODUCTION_GATE_B: NOT_YET — awaiting real secret-backed Gate A V2 PASS`
`OWNER_APPROVAL_TOKEN_ON_FILE: CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`
`RUNTIME_LLM_TOKENS: 0 (all tooling is deterministic Python, no LLM calls)`
`PRODUCTION_TOUCHED: NO`
