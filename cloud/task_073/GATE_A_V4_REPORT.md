# TASK 073 — CRM-UNIFIED-CATALOG-001 v1.0 — GATE A V4 REPORT (ROUND 5)

AUTOPILOT VERIFIED CANONICAL SHARED MEMORY:
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope of this delivery

This round builds the release-candidate V4 tooling only. No PythonAnywhere
credentials are available inside this build/test environment, so the real
secret-backed Gate A run has not executed here. Production, CRM and
crm.db were not touched, read, or written by this delivery.

## What was built

- `patcher_v4.py` — AST-located, SHA-anchored point transforms for the
  exact functions named in ROUND 5: `konteyner.gde_mashina`,
  `konteyner._ekran`, `cars_ui.stage_menu`, `cars_ui.toggle_publish`,
  `_ua_seo068_normalize` (stranica.py/master_card.py/yadro.py), and
  `publikaciya.opublikovat`/`publikaciya._otkat`. Every transform checks
  a full-file SHA256 anchor and/or a per-function SHA256 anchor before
  editing, performs a bounded substitution (never a blind global
  replace), and compiles the result.
- `gate_a_v4.py` — real GET-only fetch of the six live files via the
  PythonAnywhere Files API, full-SHA verification, in-memory transform,
  compile, and a sanitized JSON evidence artifact. Fails closed
  (`BLOCKED_NO_LIVE_CREDENTIALS`) when `PYTHONANYWHERE_API_TOKEN` /
  `PYTHONANYWHERE_USERNAME` are absent, as they are in this build sandbox.
- `gate_b_installer_v4.py` — remote-only installer with per-file backup,
  atomic write, read-back verification, exactly one real call to the
  patched `opublikovat("UA-0011", proba=False)`, and automatic full
  rollback on any failure at any step (shadow/install/rollback CLI modes).
- `gate_b_controller_v4.py` — manual-only orchestrator gated by the exact
  approval token `CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`. Uploads the
  reviewed installer/patcher/postcheck to the safe remote inbox, GET
  read-back verifies byte equality, runs remote shadow then install via
  the PythonAnywhere Consoles API, restarts the exact unique
  `python3.10 /home/Carix/start_safe.py` always_on task, runs postcheck,
  and performs an explicit remote rollback + restart if postcheck fails.
- `gate_b_postcheck_v4.py` — exact-URL, no-redirect, HTTP-200, body/href
  verification of primary/diagnostics/catalog for UA-0011, run both
  immediately and again after a >=60 second delay.
- Full pytest suite covering the patcher transforms (positive and
  SHA-drift-blocks-negative cases), Gate A credential/drift fail-closed
  behavior, and installer shadow-pass / install-rollback-on-failure
  behavior using self-contained fixtures (not live production content).

## Known, explicitly-documented limitation

`publikaciya.opublikovat` and `_otkat` are replaced wholesale after an
exact full-function SHA match (per ROUND 5 instruction), using helper
names confirmed live in the task evidence (`_master`, `proverit`,
`_ua9_sobrat_katalog`, `_zapisat_atomarno`) plus a small number of
assumed helper names for building the primary page and target paths
(`_postroit_stranicu_video`, `_postroit_stranicu_site`,
`_postroit_diagnostiku_ili_placeholder`, `_put_video`, `_put_site`,
`_put_video_diag`, `_put_katalog_video`, `_put_katalog_site`,
`_procitat_esli_est`, `_proverit_zaschischennye_kartochki`) that were not
literally quoted in the evidence. The SHA anchor guarantees the patch is
only ever applied to the exact known live function body; if the assumed
helper names do not exist in the real module, the real Gate B shadow run
will raise `NameError`/`AttributeError` at execution time (not at
compile time) and the bounded rollback will restore the exact preimage.
This is a fail-closed outcome, not a false success, and it must be
reconciled by Codex against the literal live `publikaciya.py` body
before Gate B is attempted.

## Result

`TASK_073_GATE_A_V4: READY_TO_RUN_REAL_GATE_A_V4`

This report does not claim `PASS_READY_FOR_APPROVED_GATE_B`. That status
can only be produced by actually executing `gate_a_v4.py` with real
`PYTHONANYWHERE_API_TOKEN`/`PYTHONANYWHERE_USERNAME` secrets against the
live host, which is Codex's responsibility per the task's operating
model. `SAFE_TO_START_PRODUCTION_GATE_B` remains `NO` until that real
Gate A run reports PASS and is independently audited.

Production, CRM and PythonAnywhere were not touched by this delivery.
