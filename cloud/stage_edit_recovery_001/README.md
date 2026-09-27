# Stage edit recovery

Status: candidate verified locally, **not installed**. Production acceptance is pending.

The operator changed UA-0021 from an archived/hidden projection to `sea_loaded`.
The CRM saved it correctly, but the server catalog still excluded it. Read-only
diagnostics on 2026-09-27 reproduced `CATALOG_PUBLISHED_SET_MISMATCH`. The bot log
at 04:51:50 UTC also recorded a full publication rollback for UA-0021 with
`CATALOG_ROW_SET_MISMATCH`.

## Cause and correction

`publikaciya._ua9_sobrat_katalog` returned the original published row list,
including an archived car, while the catalog renderer and transaction validator
projected only active stages. Consequently the strict row-set check rejected
every full publication while that archived row remained. Filter the shared list
before rendering, collecting photos, and returning its inventory. Keep the
transaction check, backups and rollback intact.

The stage-only synchronizer can edit existing articles but cannot insert a
reactivated or new car. Route saved stage edits and scheduled wake-ups to the
existing durable publication worker, which owns full publication, retries,
concurrent-edit detection and public freshness verification. A Telegram reply
acknowledges queuing; it does not claim public completion. Drafts retain their
unpublished state and use the selected stage when subsequently published.

Route all stage callbacks through the existing early handler. Adapt the four
valid storage codes carried by old Telegram messages inside that route. The
strict public status policy remains unchanged: the four current stages are
Korea, ferry, Georgia and Kyiv; removed/unknown values retain their hidden
projection. No CRM data migration is part of this candidate.

## Reproduce

Run from the repository root:

```bash
python -B -m unittest discover -s cloud/stage_edit_recovery_001 -p 'test_*.py' -v
python -B -m unittest discover -s cloud/delivery_status_001 -p test_delivery_status.py
```

Result: 18 recovery regressions and 7 existing status-policy tests pass.
Fixtures are function source extracted from SHA-verified installed modules,
without CRM records, credentials, media or full private runtime files.
The regression reproduces the original transaction failure and exercises its
fixed path with external rendering and file effects mocked. It also covers all
16 active stage transitions, reactivation, draft preservation, future cards,
legacy routing, more than three durable retries and a concurrent newer edit.
These are not a full live rendering rehearsal or proof of public acceptance.

Build from a private snapshot of the exact installed sources into a new private
directory:

```bash
python -B cloud/stage_edit_recovery_001/build_candidate.py \
  --source PRIVATE_SOURCE_DIRECTORY --output NEW_PRIVATE_CANDIDATE_DIRECTORY
```

The builder rejects changed sources or dependencies and compiles both outputs.
It writes only candidate `cars_ui.py` and `publikaciya.py`; it has no installation
or database-write operation. The expected hashes are in `CHECKPOINT.json`.

## Before production

1. Reconcile transaction `tx-36268504600-54c3be3cfc4dd0da` through an explicitly
   registered, evidence-bound recovery. It remains `ROLLING_BACK` with
   `EMERGENCY_HALT`: automatic rollback was reserved but never invoked because
   the pinned recovery checkout omitted its ledger-bound nonce. The existing
   TASK120-only recovery does not cover this transaction. Follow the approved
   runtime update process to correct and rehearse nonce copying. Preserve
   original approvals, request, nonce, ledger, backup and failure history.
2. Recheck CPU after the provider reset at 2026-09-27 08:37:11 UTC. Observed usage
   was 8576.84 / 5000 seconds at approximately 04:54 UTC. Heavy operations remain
   deferred under the repository's resource rule. Reset alone does not resolve
   the recovery blocker.
3. Read fresh runtime hashes and CRM rows, create a new bounded plan, and rehearse
   the complete two-file installation with backup, rollback, publication/worker
   locks and bot pause/resume. Preserve operator edits since this observation.
   Include these regressions in that plan's test command. Do not replay the
   original delivery installation or overwrite its durable sync baseline.
4. Install through main GitHub Actions with all existing gates. No launch marker
   or production request is supplied by this candidate-only change.
5. Verify the worker publishes the pending UA-0021 revision; compare the exact
   active CRM inventory and stages against both server roots and ordinary and
   cache-busted `https://www.uaart.com.ua/video/katalog.html` responses. Verify
   card freshness, home counters and bot health; record a durable final receipt.
   At this observation CRM had 20 active rows, while the server catalog had 19;
   never reuse yesterday's fixed count of 19 as the acceptance target.

Coordinate with the separate CRM/media consistency candidate before installing
either one: both may touch the same source files. Any changed hash requires a
fresh combined review and rehearsal, not relaxation of the source checks.
