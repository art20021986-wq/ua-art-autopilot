# Gate A findings — CRM-CONTAINER-STAGE-SYNC-004 v1.0

## Live GET-only evidence

The already executed sanitized audits remain canonical:

- `cloud/task_076_eta_sync/evidence/gate_a_live.json`: root cause confirmed;
- `cloud/task_077_container_stage_sync/evidence/live_audit.json`:
  `PASS_AUDIT_DEFECT_REPRODUCED`;
- PythonAnywhere methods: GET only;
- production, CRM, site and media writes: 0;
- `PRAGMA quick_check=ok`.

Confirmed live defect: `konteyner.prinyat` writes only `eta_manual` and
launches a fire-and-forget rebuild; `cars_ui.apply_value("eta_days")` writes
ETA and days in separate transactions. UA-0009/0010/0011 therefore have
inconsistent DB pairs even though the current dynamic /video pages render 30
days / 2026-09-28. UA-0009 also contains a stale independent arrival sentence.

## Corrected candidate evidence

The first TASK 079 candidate was rejected by the controller (33/34 under a
compatibility runner) and was not promoted. The corrected candidate now has an
observed stdlib result of **28 PASS / 0 FAIL** and concrete SHA/function-anchored
transforms for the eight audited live call sites.

Repository Gate A run
[`33240690447`](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/33240690447)
completed successfully for candidate commit
`9ca57523bf82691b3964ea473f94219985ef341d`:

- stdlib suite: **28 PASS / 0 FAIL**;
- exact live function transforms: **8**;
- patched live modules compiled from the current GET-only snapshot: **5**;
- local-copy DB/site canary: **PASS**;
- production writes: **0**.

`GATE_A_RESULT: PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`

Gate B has not run and remains blocked until the owner issues the exact separate
production command recorded in `gate_b_manual_workflow.md`.
