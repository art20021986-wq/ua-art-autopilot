# TASK088: owner answers → staged implementation

This is a branch-only execution foundation, not a deployment or receipt. No production success percentage is inferred from local unit tests.

## Verified baseline, 13 September 2026

- Main inspected at `0c85a6561d80c4d8789b3a482ae41cdaf9d0f667`.
- [Stage 2 canonical receipt](https://github.com/art20021986-wq/ua-art-autopilot/blob/0c85a6561d80c4d8789b3a482ae41cdaf9d0f667/state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json): FINISHED/PASS, closed 05:56:14Z; independent DB acceptance completed. Do not redeploy Stage 2.
- [Main maintenance](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34747832918): 180 tests, 173 pass and 7 fail in workflow contract tests. A local policy test pass does not clear these failures.
- [Existing Stage 3 preview PR 108](https://github.com/art20021986-wq/ua-art-autopilot/pull/108) is a preview, not a full production implementation.
- Earlier local `s3_install.py` / `s3_preview_publish.py` target one control card, not all cards plus catalog. They lack full writer isolation and compare-and-swap rollback. Do not execute them unchanged.
- Authenticated PythonAnywhere directory listing observed no `task088_stage3_install.json` or `task088_stage3_result.json`. This is not a recursive proof of absence of all server-side receipts.

## Next production package: Stage 3

1. Inspect and hash current `yadro.py`, `stranica.py`, `publikaciya.py` and the active rendering path. Never patch an unverified historical source snapshot.
2. Render BOTH independent USD prices on vehicle cards AND in catalog. Owner confirmed on 13 September: Ukrainian price INCLUDES customs clearance in Ukraine; Georgian price EXCLUDES customs clearance in Georgia. Use the explicit captions in `price_captions.py`. Preserve Ukrainian prices without conversion. Do not infer delivery/certification inclusion or add an all-inclusive/no-extra-charges promise from this answer.
3. Preserve diagnostics, extended specifications, media, descriptions, language behavior, ordering and catalog counts. No DB field migration in this stage.
4. Use a NEW stage-specific identity, request, claim, transaction and final receipt; retain Stage 2 as a prerequisite, never its identity as the new stage's identity.
5. Stage only in a separate branch. Verify exact allowed diff, all relevant tests, backup hash and restore rehearsal, writer exclusion, health checks and Gate B before any production write.
6. Rollback must compare current artifact against the version installed by this transaction; refuse to overwrite a later writer's change.
7. Inspect a canary rendering without publication first; then use the authorized deployment path. Do not patch generated HTML outside its canonical generator as a shortcut.

## Stage 4: final protection and autopilot activation

The original four-stage scope defines Stage 4 as final protection and autopilot activation. Automatic CRM-to-site synchronization is a required integration/acceptance condition across Stages 3–4, not a replacement for final protection and activation. This is unrelated to the existing logistics module for Korea/ferry/Georgia/Kyiv.

- Trigger only after successful DB commit. Use a durable, versioned event/outbox; observe both independent price fields.
- Publish through the one authorized writer with idempotency and resource locks; prevent an older event overwriting a newer price.
- Enforce the owner's 60-second target end-to-end from commit to PUBLIC card and catalog readback. GitHub scheduled runs are not evidence of that guarantee.
- On a connection/publish failure: immediately stop the affected task, preserve evidence, notify only the owner. Do not blindly retry.
- Resume automatically only when root cause resolution and fresh checks are proven. If an operation may already have applied, reconcile by readback before creating any new attempt.
- Allow independent work only after dependency and resource-isolation checks. Never treat an unknown dependency/lock state as safe.
- Verify both directions: modifying Georgia must not change Ukraine and modifying Ukraine must not change Georgia. Confirm non-price content remains unchanged and prices agree between CRM/card/catalog.
- A real final receipt, failure-path test, and safe rollback evidence are required. This branch is not that receipt.
- Final activation requires successful safety/integration gates and the owner's separate production command. No activation or HALT change is performed by this package.

## Autopilot policy integration blockers

The pure-policy module in this directory can be unit tested without a server. It is NOT wired into the active orchestrator, watchdog or CRM bot.

Integration still requires: durable task/attempt state, evidence-producing health checks, canonical workflow bindings, resolved workflow-contract failures, resource-lock/dependency integration, a configured owner-only Telegram sender and delivery checks. Telegram credentials must stay in their normal configured environment and must never enter this repository.

The daily ChatGPT health-check schedule was changed to 10:00 Asia/Ho_Chi_Minh, effective 14 September 2026. That scheduling change does not establish Telegram delivery.

Repository privacy/main protection remain unapplied; verify effect on existing Actions/deployment access before changing visibility. Never weaken existing gates to make CI green.
