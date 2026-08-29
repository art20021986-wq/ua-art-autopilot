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

`GATE_A_RESULT: CONTROLLER_LOCAL_PASS_PENDING_GITHUB_GATE_A`

Production writes remain zero. This file must be upgraded to
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` only after the repository Gate A
workflow executes this exact source state successfully.

