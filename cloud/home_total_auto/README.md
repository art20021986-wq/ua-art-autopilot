# Homepage total counter

UA-ART-HOME-TOTAL-AUTO-001 v1.0. Owner approved this specific change in chat on 2026-09-10.

**Code prepared and locally tested; NOT INSTALLED.** Written by Codex; no Claude worker execution is claimed.

The homepage total stays at 16 after the owner published 18 vehicles. The old TASK093 script counts only `[data-ua-card]` nodes with recognized stage attributes. TASK090 also emits nested `data-ua-card` nodes with `data-category` instead. Missing/unrecognized stages are skipped; a failed fetch leaves the old HTML total. The web tool returned a 16-car catalogue under the www `/video/` route. Current non-www production HTML, the exact 18-car dataset, route mapping and triggering cause still require server verification.

## Prepared change

- `home_total.py` counts unique catalogue cards independently of stages and patches only the total CTA, RU/UK attributes and updater. It retains existing stage-writing logic and prevents the legacy script from overwriting the owned total. CLI defaults to a read-only plan; apply requires preimage hashes and the verified existing publication lock, with backup and atomic readback.
- `home_total.js` fetches the catalogue linked by the CTA on the same origin, removes stage filters, counts IDs in supported card formats, preserves the value on invalid responses, and refreshes after bfcache restoration. No stage mutations, polling or LLM calls.
- `publisher_hook.py` produces a separate candidate from freshly obtained, hash-verified publisher source. It adds homepage snapshots and updates totals after catalogue validation inside the existing transaction. Restoring old backup manifests cannot delete homepages outside their original scope.

The branch changes no existing website/CRM renderer, registry, workflow, HALT file, vehicle data, VIN, specification, price or media. Only repository task reports are updated in addition to the new package.

## Local verification

```bash
python3 -m unittest discover -s cloud/home_total_auto -p 'test_*.py' -v
node --check cloud/home_total_auto/home_total.js
node cloud/home_total_auto/test_home_total.cjs
```

PASS: 11 Python tests, JavaScript syntax, and behavioral JavaScript tests with explicitly mocked DOM objects. Cases cover 18→19→18, unique IDs, unknown stages, missing markup, zero/truncated catalogues, RU/UK, stale writes, backup/readback, idempotence, old/new snapshot safety and unchanged non-total HTML. No real-browser or production integration test has run.

## Remaining deployment work

Deployment is already owner-authorized after successful checks. The blocker is technical access, not another task approval.

1. Obtain the actual served homepage/catalogue and active publisher through the authorized PythonAnywhere connection. Verify CTA routes and published IDs, including UA-0017/UA-0018. Do not force 18 when the chosen source contains 16.
2. Verify the active publication lock and publication/unpublication callbacks. The historical TASK083 publisher hash differs from TASK120's expected live hash. **Do not overwrite the live publisher with the historical file.** Run `publisher_hook.py` on fresh live bytes; unknown anchors are rejected, and a successful candidate still needs transaction/callback verification.
3. Stage the helper, JS, reviewed minimal publisher diff and homepage candidate using the existing authorised deployment mechanism. Verify publishing and unpublishing on an isolated copy; the helper must receive the validated published set and run within existing snapshot/rollback protection.
4. Back up and deploy only verified source files/homepage copies under the active lock. Never invoke broad TASK093/TASK100 installers or old jobs. Keep the current HALT intact.
5. Verify the live total against the linked catalogue in RU/UK and a real browser. Record a receipt before reporting completion.

This session has no PythonAnywhere connector or API credential. `state/AUTOPILOT_HALT.json` records `EMERGENCY_HALT` after TASK120; the existing recovery workflow is specific to that task. No task launch, deployment, restart or HALT removal was performed.

## Export status

The local branch is `fix/home-total-auto-20260910`. Its push was rejected by automatic approval review: exporting code to the public `art20021986-wq/ua-art-autopilot` destination requires explicit owner authorization for this branch/destination. No alternative push route was attempted. The owner subsequently explicitly approved sending this branch to this public destination. Export is now authorized; server installation remains pending.
