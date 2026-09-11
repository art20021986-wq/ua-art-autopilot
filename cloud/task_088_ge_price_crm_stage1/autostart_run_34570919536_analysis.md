## Autostart run 34570919536

Status: root cause confirmed.

Exact failed run:
- workflow: `UA ART Global Production Autostart`
- run id: `34570919536`
- job: `intake`
- failed step: `Require exact main automatic runtime`

Observed cause:
- the triggering main push was merge commit `24287ac9ca1f01d9f5c6a617834d96e47a5fe63a`;
- PR #91 added three files in one merge:
  - `tasks/UA-ART-GE-UA-MARKET-PRICE-001-v3.1.md`
  - `tasks/requests/TASK088-GE-PRICE-CRM-STAGE1.json`
  - `tasks/launch/AUTO-TASK088-GE-PRICE-CRM-STAGE1-20260911T055651Z.json`
- the runtime guard in `.github/workflows/uaart_autostart.yml` requires the triggering main commit to add exactly one file, and that one file must be `tasks/launch/AUTO-*.json`.

Why execute/persist were skipped:
- `intake` failed before `automation/autostart_intake.py` consumption;
- downstream `execute`/`persist` did not run because `intake` is a hard gate.

TASK088 contract fix prepared here:
- preserved the existing non-production request `tasks/requests/TASK088-GE-PRICE-CRM-STAGE1.json`;
- issued a fresh non-production launch marker `tasks/launch/AUTO-TASK088-GE-PRICE-CRM-STAGE1-20260911T064559Z.json`;
- `production_allowed` stays `false`.

Required replay shape for intake PASS:
- the fresh `AUTO-TASK088-GE-PRICE-CRM-STAGE1-20260911T064559Z.json` marker must be the only added file in the triggering main commit.

Validation:
- JSON syntax for request and launch marker: PASS
- sha256(request) = `ef95c515b035b99c16ef2ad08266d684c736b5a0945105ce6dd7a6bdb6c72bca`
- local exact-intake replay in `/tmp/task088_autostart_replay`: PASS
- `verify-mode --require AUTOMATIC`: PASS after replaying main-equivalent non-halted state
- `automation/autostart_intake.py ... --validate-only`: PASS
