# UA-ART-CRM-MEDIA-SYNC-001 — checkpoint 27.09.2026

Status: DRAFT_CANDIDATE; production_written=false; full_acceptance=false.
Owner authorized media reconciliation and repair in this conversation.
Specification: `docs/UA-ART-CRM-MEDIA-SYNC-001.md`.

## Evidence

- `crm_readonly_20260927.json`: read-only SQLite transaction, stable downloader
  ledger during the photo comparison, safe filenames/counts only. 21 published
  rows, 2 archived, 19 active public cards. Not a database backup.
- `public_readonly_20260927.json`: ordinary public URLs, 19 HTTP 200 responses,
  parsed photo lists, video references and cache headers. All HTML hashes
  equal server files observed in the CRM probe.
- `video_source_readonly_20260927.json`: current source hashes/function names
  and safe video mapping results. The first UA-0001 video has no ledger binding.
- `comparison_20260927.json`: 4 photo mismatches; 604 expected / 606 displayed
  photos; 18 public video URLs, 17 ledger-bound; 18/19 video player structures
  checked, UA-0001 mapping unresolved. No original-byte or playback PASS.

The server has changed since yesterday: UA-0018 now has 59 photos and UA-0022
23, which match their present CRM lists. Do not restore yesterday's values.

## Confirmed causes and candidate changes

Actual `stranica.kadry_mashiny` scans all JPG files without hidden-photo
filtering and promotes a horizontal image. This explains UA-0017/0019 hidden
photos and UA-0012/0016 order differences. Actual
`master_card.video_fajly_mashiny` recursively scans filename prefixes; this
cannot enforce CRM membership/order. Downloader `skachat` already stages
`.part` and uses `os.replace`, but reuses mutable filenames and regenerates
posters. Atomic rename alone does not provide content-versioned assets.

Changes in existing candidate package:

- Deleted/hidden cover falls back to the first currently visible CRM photo;
  malformed cover names still fail, removed files are never reintroduced.
- Snapshot schema 4 includes the car's video ledger. Retry-only metadata
  does not change car revisions in the new tests.
- `crm_videos.py` selects only CRM video IDs in CRM order and validates
  player source/fallback/order. Unknown mapping is an explicit error.
- Preview dependency/test hashes updated for this draft; video module is
  included in the payload. It is not yet wired into final rendering.

74 tests PASS. This count is unit/isolated validation, not production acceptance.

## Blocking conditions / safe continuation

1. CPU dashboard: 8476.27 / 5000 seconds, tarpit, reset indicated around
   08:37 UTC / 15:37 Vietnam. Measure fresh usage; no heavy work at >=85%.
2. `state/AUTOPILOT_HALT.json` remains active; delivery transaction
   tx-36268504600-54c3be3cfc4dd0da is ROLLING_BACK. Respect registered recovery;
   do not clear markers, replay the installer, or weaken guards.
3. `stranica.py`, `master_card.py`, `ua_crm_public_sync.py` hashes drifted from
   `build_gallery_patch.SOURCES` due to the delivery-status release. The
   original pins are intentionally retained; do not launch this request yet.
   Re-read actual sources and preserve the installed delivery changes while
   rebasing the exact candidate. No new launcher/approval/nonce is created here.
4. Resolve UA-0001 first-video provenance; do not guess from its filename.
5. Wire strict video selection/validation into generators, implement complete
   immutable media/downloader manifests, empty-gallery rendering, durable
   event propagation and revision fencing. Run full shadow and rollback
   rehearsal, backup and Gate B before installation via main Actions.
6. Verify original hashes, derived-file provenance, public URLs, real mobile
   playback/cache, <=60s healthy-path updates, failure recovery and 24h observation.
7. The updated draft request is classified CRITICAL (`CRITICAL_TEXT:authorization`),
   while its existing preview controller expects STANDARD. Execution-contract
   validation fails with `ROUTE_CLASS_MISMATCH:STANDARD:CRITICAL`. This is a
   separate draft integration issue, not a passing deployment gate. Prepare a
   consistent fresh request/controller under the detected route after integration;
   do not weaken classification or reuse the old launch request.

No production source, database, media file, server HTML, task or protection was
modified by this media task. Read-only console used Python standard-library
parsing and a read-only SQLite connection. No live imports of site modules.
