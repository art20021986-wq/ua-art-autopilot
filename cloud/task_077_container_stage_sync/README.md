# CRM-CONTAINER-STAGE-SYNC-004 v1.0 — release candidate

This package fixes the proven ETA/status split for current and future CRM
cards without changing production during Gate A.

## Candidate behavior

- Both ETA entry points are patched to one shared live function.
- TASK 076 `eta_engine.compute_manual_eta` remains the sole ETA computation
  engine; its earlier hold-open transaction controller is superseded and must
  not be wired concurrently.
- A short transaction commits `status + days_to_kyiv + eta_manual +
  updated_at + audit` before any publication starts.
- Fresh DB read-back precedes a six-target staged publication:
  primary and diagnostic/placeholder in both roots plus both shared catalogs.
- Any DB, publisher, install, delayed-overwrite or public verification failure
  restores the exact row, only this operation's audit IDs, and exact file
  bytes. The original `published` value is preserved.
- Legacy `sea_transit` is removed from the active menu and can only normalize
  forward to canonical `sea_loaded` (“На пароме”). Sold, Georgia, Kyiv and
  archive states never move backward.
- The renderer removes only an arrival/delivery sentence containing an
  independent date; every unaffected byte remains unchanged.
- `toggle_publish` emits “Машина видна…” only after publisher PASS.

## Files

- `patcher/eta_release_candidate.py` — transaction, staging, verification and
  compensating rollback, plus the inert-until-Gate-B live bridge.
- `patcher/live_patcher.py` — exact full-file/function-SHA patch bundle with
  eight concrete transforms, backup and auto-rollback.
- `tests/test_eta_release_candidate.py` — stdlib Gate A suite.
- `sandbox/release_candidate_report.md` — literal observed result.
- `evidence/gate_a_findings.md` — live diagnosis and final Gate A state.
- `gate_b_manual_workflow.md` — prepared, never automatically executed.
- `gate_b/remote.py` and `gate_b/controller.py` — owner-approved manual
  production workflow with durable backup, exact rollback and delayed checks.

Local controller result: **28 PASS / 0 FAIL**.
Repository Gate A: **PASS**, run
[`33240690447`](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/33240690447).
Production touched: **NO**.

The repository safe-workflow watchdog checks this Gate A and the other approved
non-production workflows every five minutes. A timeout/stale run is retried at
most three times; production/Gate B/deploy workflows are explicitly excluded.

Production scope follows the newest owner state: UA-0009 and UA-0010 receive
the 30-day atomic correction; UA-0011 is protected because its newer amendment
returns it to Korea and clears its container/ETA.
