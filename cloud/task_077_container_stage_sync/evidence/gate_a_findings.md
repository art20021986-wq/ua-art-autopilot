# TASK 079 — Gate A findings restated for the release candidate

MEMORY MARKERS (verbatim):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

This file restates, without re-executing any live request, the defect
evidence already captured by TASK 076/077 GET-only audits, which this
release candidate is designed to fix once Gate B is separately approved.

Source evidence files (unmodified by this task):
- `cloud/task_076_eta_sync/evidence/gate_a_live.json`
- `cloud/task_077_container_stage_sync/evidence/live_audit.json`

## Confirmed defects

1. **Two divergent write paths.** `konteyner.sprosit_dni`/`konteyner.prinyat`
   writes only `eta_manual` from a parsed N; `cars_ui.apply_value("eta_days")`
   performs `days_to_kyiv` and `eta_manual` as two separate transactions.
   Neither path is atomic with the other, and neither verifies publication
   before reporting success to the operator.

2. **Fire-and-forget rebuild.** `konteyner._peresobrat` is a detached
   `subprocess.Popen` call; the handler claims the page is updating without
   any verified result, which is the root cause of the operator being told
   "success" before the site actually reflects the change.

3. **Inconsistent existing state.** UA-0009 has `days_to_kyiv=13` while its
   `eta_manual=2026-09-28`; UA-0010 and UA-0011 have `days_to_kyiv=NULL` with
   the same `eta_manual=2026-09-28`. This is a direct, evidenced symptom of
   the non-atomic two-transaction pattern in `cars_ui.apply_value`.

4. **Stale published text.** UA-0009's public description contains an
   arrival/delivery sentence referencing an independent date, `9 вересня
   2026`, which no longer matches the current dynamic ETA of `2026-09-28`
   (30 days). This is the exact narrow case the sanitizer in
   `eta_release_candidate.sanitize_stale_arrival_sentence` targets — and only
   that kind of sentence, never unrelated service/auction/registration dates.

5. **No commit-before-publish guarantee.** Because rebuilds are fire-and-forget
   and publication is unverified, there is no proof today that a DB commit
   happens strictly before any renderer/filesystem/subprocess/HTTP/publisher
   call, which this release candidate's `apply_eta_change` orchestrator now
   enforces and the sandbox tests demonstrate via a spy publisher.

## Preserved current visible behavior (not to be regressed)

- UA-0009/0010/0011 currently render as 30 days / ETA `2026-09-28` on the
  public site. The release candidate's target-state test
  (`test_ua0009_0010_0011_target_state`) reproduces exactly this outcome in
  the sandbox model.

## What remains unproven until Gate B

- No claim is made that the release candidate has been executed against the
  real production database or file set. `ua0009_safe_to_publish` remains
  `NO` per canonical memory REC-0005/REC-0006/REC-0007 until independent
  verified evidence says otherwise.
