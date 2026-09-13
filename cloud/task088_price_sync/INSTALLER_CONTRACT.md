# Stage 3 source, price HTML and outbox installation candidate

**Not installed. No CRM restart or autopilot activation has been performed.**

`install_package.py` supplies a callable installation engine, not a self-authorizing
command. A trusted execution adapter must obtain the real canonical request,
claim, OPEN transaction, approved manifest, Gate B evidence and owner authorization
from their authoritative records. Passing invented JSON documents is not an
authorization workflow. The engine verifies exact artifact bytes, their binding
and current state; it cannot authenticate an arbitrary caller's provenance.

## Current source and file scope

Writable source targets: `cars_ui.py`, `yadro.py`, `stranica.py`,
`catalog_design_guard.py`, `publish_transaction_guard.py`. Each candidate is
produced by its current-source SHA-bound patcher.

Installed modules: `uaart_market_prices.py`, `uaart_price_sync_outbox.py`,
`uaart_price_sync_runtime.py`, `uaart_price_sync_binding.py`, `owner_policy.py`,
`price_publication.py`.

The only initial public HTML changes are price fragments in the 18 currently
published cards in **both** `video/` and `site/`, plus those two catalogs: 38
files. `build_candidates` uses the strict initial HTML migrator; it does not
call a live generator or republish diagnostics, photos or specification pages.

`catalog_design_golden.html` is **read-only**. It and the six other
dependencies are pinned, backed up and verified unchanged before and after
installation. The final catalog guard inserts the new prices into its existing
golden template on later normal render calls.

## Source hook

The CRM hook keeps the Stage 2 price and audit checks, adds the outbox event before
the same connection commits, and performs independent readback. Published cars
require stable Telegram chat/message/update/actor/card/field identity. Repeated
messages do not repeat audit writes; old deliveries cannot overwrite a later
price. Both explicit buttons, text/AI price routes, voice CAS and guarded voice
undo are covered. Nullable Georgia restoration is an internal guarded operation.

Initial vehicle publication stays manual. The existing 15-second stage job and
unrelated handlers remain unchanged. The final registration wrapper explicitly
bootstraps `/home/Carix/.uaart_price_sync_anchor.json` before registering the price
worker. That anchor must be derived from actual completed installation evidence;
the code does not supply an invented control bridge or owner chat.

## Installer safety boundary

- Immutable plan hash; exact before/after manifest, dependency hashes, current
  schema and all CRM/audit row hashes; exact published IDs/count and price hash.
- Fresh Gate B/quota/writer evidence; canonical claim and unexpired transaction;
  canonical Stage 2 receipt bound to the current `cars_ui.py` preimage.
- Existing publication `flock` and SQLite `BEGIN IMMEDIATE` held across backup,
  source/schema/HTML switch and verification. All writers must honor the same
  fence; an uncovered external writer blocks installation.
- Verified immutable private source/HTML/dependency backups and SQLite online
  backup before mutation. Account quota and actual filesystem free space must
  cover backup, candidates and rollback; OS disk size is not account quota.
- Atomic individual file replacements, file/directory fsync, current-preimage
  CAS and readback. This is a coordinated bundle with rollback, **not** a claim
  that multiple filesystem paths can switch in one atomic OS operation.
- Schema creation is confined to the reviewed outbox/recovery/notice tables.
  CRM cars and audit rows must remain unchanged. DDL rolls back with the caller's
  transaction on failure.
- Rollback only restores an exact candidate written by this transaction. Foreign
  versions are preserved and reported. Failed restoration is reported as
  incomplete reconciliation; it is never labeled successful rollback.
- A committed source/schema bundle with a missing receipt is uncertain and must
  be reconciled. The engine does not automatically undo committed changes or
  replay an interrupted installation.

Output `install_receipt.json` has status
`INSTALLED_PENDING_LIVE_ACCEPTANCE`, real installed hashes and backup proof,
`stage3_complete:false`, `bot_restarted:false`. It is installation evidence only.
The verified private config/anchor, controlled CRM activation, public readback,
Telegram acceptance and stage completion receipts remain subsequent operations.

## Read-only server preflight

Flatten the six runtime modules and these eight tools into the already approved
private directory `/home/Carix/autopilot_inbox/cloud/task088_price_sync_current`:

`preflight.py`, `install_package.py`, `patch_cars_ui.py`, `patch_yadro.py`,
`patch_stranica.py`, `patch_catalog_design_guard.py`, `patch_guard.py`,
`initial_html_prices.py`.

The reviewed `preflight_bundle.json` must contain:

- `contract`: `TASK088-PRICE-SYNC-READONLY-PREFLIGHT-1`;
- `package_sha256`: exactly the six modules and eight tools;
- `source_sha256`: exactly the five writable live-source preimages;
- `dependency_sha256`: `db.py`, `cars_schema.py`, `start_safe.py`,
  `master_card.py`, `publikaciya.py`, `ua_stage_catalog_sync.py`,
  `catalog_design_golden.html`;
- `expected_stage_counts`: current Korea/sea/Georgia/Kyiv counts;
- `stage2_receipt`: the actual canonical Stage 2 receipt contents;
- `quota_evidence`: authenticated Carix account usage/limit in bytes, source
  `PYTHONANYWHERE_AUTHENTICATED_ACCOUNT`, aware ISO `observed_at` at most 30 minutes old.

Run in that staging directory using a new observation ID and its actual reviewed
bundle SHA:

```sh
python3.10 preflight.py --output-id preflight-UNIQUE-OBSERVATION-ID --expected-bundle-sha256 ACTUAL_64_HEX_BUNDLE_SHA
```

Only a new `preflight_outputs/<id>/` tree is written; reuse is rejected. Candidate
files and two SQLite copies stay private with mode 0600 inside mode-0700
directories. No DB rows or full source content are printed. The report records
hashes, counts, exact price-preservation results and blockers. The SQLite copies
must never be put in GitHub or a public attachment.

A candidate can pass local/source/HTML/schema verification while overall status
remains `BLOCKED` because the canonical control bridge/Gate B/activation has not
run. This is intentional. The script never creates a success receipt for those
missing operations.

## Verification performed locally

- **18/18 CRM-hook tests PASS**, using AST-extracted exact current functions and
  isolated SQLite databases; no bot/source module import.
- **15/15 installer safety tests PASS**, using explicit `TEST` plans/temp roots:
  online-backup readback, atomic rollback, competing-version preservation, stale
  or false evidence, quota, schema/price drift, missing binding, syntax failure
  symlink refusal and preservation of an existing transaction's historical evidence.
- Server-preflight code compiles and its readonly SQLite online-backup method
  was exercised locally. Real 38-page server validation is a separate recorded
  run; this document does not claim it has occurred.
