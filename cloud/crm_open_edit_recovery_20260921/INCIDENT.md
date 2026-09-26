# CRM card opening recovery — 21 September 2026

Status: **NOT INSTALLED — live opening/editing recovery NOT VERIFIED**.

The owner reports very slow CRM and inability to open vehicle cards for editing,
and authorizes urgent correction and protection against recurrence. This work
continues the already authorized recovery; no new installation permission is
required. Existing production admission and backup requirements remain in force.

## Current evidence

- Main remains `79c6aaccbfdc2decf7bf39d26738a2c38bde91f4`.
- PR116 remains draft/unmerged at `c0932c81c5f0ffc51e7b57308d1a427ba6c73946`.
  Its recorded 342 offline tests cover deletion/list recovery, not successful
  live opening/editing or complete CRM performance.
- Current `cars_ui.py` and `db.py` were read through the authenticated provider
  file editor and match the SHA256 values in `live-probe.json` and PR116's
  earlier source binding. The full sources are private working inputs and are
  deliberately excluded from this public package.
- At 08:47:07 UTC a bounded server diagnostic ran successfully. SQLite was
  opened using `mode=ro` and `query_only`; `quick_check=ok`, 21 cars,
  `journal_mode=delete`. The complete diagnostic read took 0.6056 seconds.
  This is one read-only sample, not a production callback benchmark.
- The sampled 120000-byte log tail had no matches for database locking,
  Telegram message length/HTML errors, BadRequest, TimedOut, or media-opening
  timeouts. This does not exclude errors elsewhere or a later recurrence.
- The log did contain repeated `PublishError:
  TASK090_CATALOG_CONTRACT:SHELL_FINGERPRINT_MISMATCH` from
  `_ua004_stage_reconcile_job -> ua_stage_catalog_sync.reconcile ->
  publish_transaction_guard._validate_catalog`. Runs at 08:34–08:36 occurred
  at approximately 15-second intervals. Attempt counts reached 3/3 and reset
  to 1/3 when signatures changed. The sample does not prove an endless loop
  under an unchanged signature. The catalog validator has not been weakened.
- The initially open Tasks page was stale: it showed exhausted CPU allowance
  at 06:28 UTC. A fresh page showed the daily allowance reset. CRM was then
  briefly `Starting` and later `Running`. No restart, disable, or kill was
  performed by this work. Running does not prove working Telegram callbacks.
- A live Telegram acceptance question returned no answer. No Telegram messages
  were sent and no customer/vehicle values were edited.

## Concrete candidate and independent review

`build_ui_hotfix.py` creates a source-pinned candidate containing only changes
to `open_card`, `edit_menu`, `edit_ask`, and their new helpers. It does not install
anything. The other source AST nodes remain unchanged.

The candidate preserves editing controls after display errors, escapes and
limits field previews, handles missing records, and moves media delivery out
of the opening callback with one active task plus one latest request per user.
It also clears the previous active vehicle before any await and activates the
requested vehicle only after successful display. This fixes an independently
reproduced stale-card context risk on a failed editor transition.

19/19 isolated regressions passed. Independent review passed after the context
fix; actual media functions were inspected and use asynchronous Telegram sends.
These results do not identify the cause of every current delay. Synchronous
SQLite, catalog and specification reads remain; PR116 list/deletion recovery
is separate. No permanent or full recovery is claimed.

## Installation blocker

The existing SEO incident `SEO-DAILY-PODBOR-CANONICAL-20260921`, run
`35552076762`, remains under EMERGENCY_HALT. Its transaction remains PREPARING,
`opened_at=null`, and backup hashes are null. The workflow failed while waiting
for a remote backup receipt. A timeout is not evidence that remote execution
never occurred.

Review found no generic approved forward-install route for this CRM patch
while that incident remains unresolved. The existing TASK120/TASK121 recovery
exceptions are bound to their own operations and cannot be reused. The code
and status of HALT/claims/transactions were not modified, and no workflow was
launched or rerun. No fresh installation backup exists for this candidate.

## Exact continuation

1. Reconcile the specific SEO incident through its incident procedure using
   remote schedule/process, backup/manifest/receipt and target before-image
   evidence. Preserve the original incident records. Do not erase HALT or
   declare the backup successful to admit this patch.
2. Establish fresh source/schema and process/lock visibility, then obtain a
   verified SQLite-aware backup and the applicable production admission.
3. Apply the admitted minimal package through the established channel with
   source readback and bounded service recovery. Account explicitly for the
   separate PR116 list recovery instead of treating this UI patch as its fix.
4. Verify real Telegram list, card, editor and return flow. Check that existing
   UA/GE values and media remain intact. Close the incident only with that
   evidence; do not convert the offline test count into live PASS.

Server changes in this work were limited to the new diagnostic file
`/home/Carix/uploads/crm_probe_20260921_0846.py` and its JSON output. Business
source, CRM records, website pages, task configuration and existing locks were
not changed. Diagnostics never imported the CRM application or its DB module.

## Validation reproduction

Tests require a private copy of the exact current `cars_ui.py` at
`../current/cars_ui.py` relative to this package. Do not commit that full source.
Run `python -W error::RuntimeWarning test_ui_hotfix.py -v` from the package.
The source SHA is checked; mismatches are a stop condition, not a skipped test.
