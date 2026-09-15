# FINAL v5 Stage 3 installation contract

This is reviewed preparation and an installation engine, **not installed or activated**.
No Stage 1 or Stage 2 controller is called. The actual closed Stage 2 receipt must
prove Stage 1 prerequisite, Stage 2 PASS and the exact current `cars_ui.py` preimage.

## Immutable scope

Contract: `UA-ART-GE-PRICE-STAGE3-INSTALL-5`.
Task identity: a fresh `TASK088-GE-PRICE-SITE-STAGE3-<unique-suffix>` with a real
canonical request, RUNNING claim and unexpired OPEN transaction. Historical
Stage 1/2 requests, nonces, receipts and HALT controls are never rewritten.

Writable existing Python sources: `cars_ui.py`, `yadro.py`, `stranica.py`,
`catalog_design_guard.py`, `publish_transaction_guard.py`.

New modules: `uaart_market_prices.py`, `uaart_price_sync_outbox.py`,
`uaart_price_sync_runtime.py`, `uaart_price_sync_binding.py`,
`uaart_price_sync_confirmation.py`, `owner_policy.py`, `price_publication.py`.

The published vehicle set is read from CRM and pinned by exact IDs/codes/hash,
without a fixed count of 18. HTML scope includes every published vehicle in both
`video/` and `site/`, both `katalog.html` files and both `index.html` files. Home
surfaces without actual vehicle previews retain their full original bytes;
no car's price is presented as a price of a whole vehicle stage.

All files under `video/` and `site/`, plus every root `.py`, `.html`, `.css` and
`.js` file, form the complete protected system inventory. Unrelated assets,
images and specification files must remain unchanged. Symlinks, unreadable
subtrees and inventory drift stop preparation or installation. All source and
HTML patchers remain exact-preimage bound.

## Required real evidence

`request`, `claim`, `transaction`, `gate_b`, `stage2`, `quota`, `writers`,
`manifest`, `owner_approval`, `preview_gate` are raw authoritative documents,
pinned by exact SHA-256 in the plan. A trusted execution adapter must retrieve
and authenticate their provenance. JSON supplied to the engine is not itself an
authorization workflow.

The actual full Preview report uses `TASK088-FINAL-V5-PREVIEW-GATE-1`, binds the
candidate manifest, current schema, CRM/audit hashes, protected system inventory
and exact published codes, and passes every name in `PREVIEW_CHECKS`. Gate B
must bind the exact raw Preview report hash. A generic Gate PASS cannot hide a
missing mobile, language, homepage, protection or other required check.

Owner authorization remains the existing canonical production format, bound to
the fresh task/request/manifest/Gate. The owner's FINAL v5 authorization already
permits automatic Stage 3 publication after full Preview PASS; the adapter must
materialize those real technical bindings without asking again merely to fill
hashes. The engine never invents them.

## Backup, switch and recovery

Before source/schema/HTML mutation, hold the existing publication flock and a
SQLite `BEGIN IMMEDIATE` transaction, re-read exact live preimages and schema,
and verify the complete inventory and all existing writer fences.

Create a unique private backup directory for this real transaction. Back up all
scoped website files/assets/root source files with streamed independent hash
readback, plus a SQLite online backup verified against the original CRM/audit
snapshot. Preserve originals and modes in the immutable backup manifest. Database
and source backup permissions are 0600; directories are 0700. Account quota
must cover the actual full backup/candidates/rollback plus filesystem space.
An OS disk size cannot substitute for authenticated account quota.

Fresh authority and writer evidence is rechecked after the potentially long full
backup, before mutation. The schema installer only adds reviewed v1/v5 outbox,
recovery, notice, intent, immutable audit and confirmation objects. It must not
commit the caller's transaction or modify existing cars/audit. The complete
candidate schema must equal the schema produced in the isolated Preview DB.

Each file replacement uses preimage CAS, atomic replace, fsync and readback.
This is a coordinated bundle, not one atomic multi-file OS switch. Verify the
whole system inventory, schema and CRM/audit before commit, then independently
read the committed DB/schema from a separate connection. Recheck protected files.

Before commit, failures roll back schema and restore only files still equal to
this transaction's exact candidate. Newer foreign versions are preserved and
reported as conflicts. Failed restorations require reconciliation; old backup
or historical evidence is never replaced. After a committed bundle, failure or
missing receipt means uncertain state requiring reconciliation. The engine
never silently restores an old DB or erases newer operator changes.

## Output and activation boundary

Successful installation yields `INSTALLED_PENDING_LIVE_ACCEPTANCE`, actual
installed hashes, full-backup hash, independent readback PASS, and
`stage3_complete:false`, `bot_restarted:false`, `live_public_acceptance:NOT_RUN`.
This is **not** Stage 3 or Stage 4 completion.

Subsequent actual operations must: reconcile the receipt with the canonical
claim, construct the private v2 binding anchor from real installation/delegation
evidence, restart only the positively identified CRM process, perform full
post-deploy public checks, run the real Stage 4 operation/restart/Telegram tests,
and close the relevant canonical gates. The Stage 2 installation route does not
perform these new Stage 3/4 operations and must never be reused to imply success.

## Preparation tools

See `cloud/task088_v5_install/README.md` for the exact read-only observation,
package build, private preflight and immutable plan commands. These tools never
write live sources, publish pages, restart CRM, create Gate B or manufacture a
claim/owner approval. Candidate/source files can contain embedded credentials
and must stay private; do not commit the candidate tree or backup DB.
