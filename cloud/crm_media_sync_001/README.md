# UA-ART-CRM-MEDIA-SYNC-001 — checkpoint 27.09.2026

Status: COMPOSED_DRAFT_CANDIDATE; production_written=false; full_acceptance=false.
Owner authorized media reconciliation and repair in this conversation.
Specification: `docs/UA-ART-CRM-MEDIA-SYNC-001.md`.

## Observed evidence (timestamps are not interchangeable)

- `crm_readonly_20260927.json`, 04:36:41 UTC: read-only SQLite transaction,
  stable downloader ledger, safe filenames/counts only. 21 published rows,
  2 archived, 19 active public cards. Not a database backup.
- `public_readonly_20260927.json`: 19 ordinary public HTTP 200 responses.
  All observed public HTML hashes equal the corresponding server files.
- `comparison_20260927.json`: 604 expected visible photos / 606 displayed;
  hidden photos UA-0017/040.jpg and UA-0019/001.jpg are shown, and first-photo
  order differs on UA-0012/UA-0016. 18 video URLs, 17 ledger-bound; the first
  UA-0001 video has no binding. No Telegram byte-identity or playback PASS.
- Later stage-recovery observation at 05:07:18 UTC: CRM now has 20 active rows,
  server catalog 19; UA-0021 was reactivated. Final acceptance must use a fresh
  inventory, not the historic 19-card or 604-photo count.
- UA-0018 has 59 and UA-0022 23 photos in the media audit. Do not restore older
  values. CRM changes made after a snapshot must survive release/rollback.

## Confirmed causes and implemented candidate

Photo rendering scanned JPG directories, ignored CRM hiding, and promoted a
horizontal photo. Video rendering scanned filename prefixes and old archives.
The downloader reused ordinal filenames when the list changed. Its existing
`.part` + `os.replace` was atomic but still changed bytes at cached public URLs.
Its bounded fixed-order queue could delay later cars behind a large album.

The candidate in `cloud/crm_site_consistency_001` now:

- Selects photos/videos by CRM IDs, order, visibility and downloader bindings.
  Deleted or hidden covers use the first current visible photo. An empty
  gallery renders a neutral background, never a retained car photo.
- Keeps each file ID's binding stable through reorder/removal/addition. New
  IDs receive separate filenames; old assets remain available for rollback.
- Publishes content-hashed immutable originals and posters; checks local
  source/target signatures and digests, avoids repeated large-file hashing,
  rejects incomplete HTTP responses and low-space immutable copies.
- Includes actual specification sidecars, photos, videos and ledger state in
  revision schema 5, preserving the delivery_status contract of the worker.
- Validates final photo/video membership and order before HTML is written.
  Download completion queues the durable transactional publisher; it never
  reports that the public site is verified merely because downloading ended.
- Persists retry state, rotates the bounded download queue across cards,
  avoids a silent 100-photo truncation and isolates a bad card from others.
- Preserves existing diagnostics rendering, active-catalog filtering, stage
  updates, catalog-error cooldown and one-click request completion logic.

`compose_release.py` composes the reviewed one-click publication candidate
(which already includes stage/performance fixes). It validates exact live
source hashes and all four intermediate publication output hashes. UI and
request-store outputs are retained unchanged; overlapping publisher/worker
outputs receive the media changes. The frozen `release_builders/` copies are
byte-identical to main 792ac863659d29ead23b20fac87455f7fff4206b; PROVENANCE.json
records their origin. They are inside the pinned execution-contract closure,
with no import of unpinned external builders. Do not install overlapping
independent packages over one another.

## Validation and limitations

- 99 media tests PASS from a clean 31-file pinned Python closure.
- 68 current publication/stage/performance/status regressions PASS separately.
- Fresh CRITICAL preview execution-contract compile PASS. The old historical
  request was restored unchanged; no launcher/approval/nonce was created.
- Five actual private runtime source transformations compile. The active
  catalog function and one-click retry function survive composition unchanged.
  See `composition_validation_20260927.json` and
  `local_validation_20260927_followup.json`.
- The complete seven-file source build was not repeated locally because this
  workspace does not contain the private full cars_ui.py source. The full
  isolated renderer, installation and rollback rehearsal have NOT run.
- Existing legacy ledger bindings are NOT proof of Telegram byte identity.
  The immutable index explicitly records telegram_original_verified=false.
  First-download provenance migration, UA-0001 recovery and original-byte
  comparison are outstanding acceptance work. Do not label them verified.
- Storage sizing/retention, real browser playback/cache and <=60s healthy-path
  latency after media readiness remain unverified. Old originals are retained;
  there is no automatic garbage collection in this candidate.

## Release blockers and safe continuation

1. Existing HALT / ROLLING_BACK delivery transaction
   tx-36268504600-54c3be3cfc4dd0da must be reconciled through its registered
   recovery. Follow cloud/crm_release_recovery_20260927/README.md. Do not clear
   markers, weaken pins, replay the old installer or repurpose TASK120 recovery.
2. Last shared CPU dashboard observation: 8754.46 / 5000 seconds, tarpit.
   Recheck after 08:37:11 UTC; quota reset alone is not permission to deploy.
   CLAUDE.md requires heavy work deferred at >=85%.
3. Re-read current runtime sources and inventory; resolve UA-0001 provenance;
   run the composed exact-source shadow and bounded backup/install/rollback
   rehearsal, including the private request ledger and media index.
4. Complete Gate B and use main Actions for installation. Preserve pending
   operator edits and confirmed original assets. Confirm the bot loaded the
   installed code; do not merely check that its task says Running.
5. Verify ordinary public URLs, originals/derivatives, all CRM media operations,
   browser playback/cache, update latency, recovery and 24-hour observation.

No production source, database, media file, server HTML, bot task or protection
was modified by this media task. No new delayed deployment was configured.
The existing delivery continuation belongs to the shared recovery workflow;
this checkpoint does not promise background installation.
