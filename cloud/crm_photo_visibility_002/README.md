# Technical source photos stay out of public galleries

Owner request: remove the technical specification screenshot from UA-0023 and
keep future photos submitted for OCR/data entry out of the vehicle gallery.

The permanent correction stops `ai_filter.save` from appending input photographs
to `photos`; inbox linkage and existing video behavior remain. Both public gallery
and cover selectors respect `hidden_photos` through the synchronization ledger.
Dedicated vehicle-photo editors remain available.

`public_cleanup.py` removes only confirmed CRM-hidden frames from UA-0017, UA-0019 and UA-0023,
keeps lightbox indexes and photo captions aligned, changes its cover to the first
vehicle photograph and adjusts each gallery count (UA-0023: 38 to 37). It preserves all other
catalog cards. The cleanup uses authenticated public HTML snapshots and exact
before/after hashes; existing page permissions are preserved.

The installer pins the actually observed reviewed source version, verifies its
exact plan again during backup, preserves CRM and pending requests, holds existing
writer locks, pauses/resumes the bot and verifies exact public bytes. Rollback is
rehearsed, including interrupted writes and a failure before any file writes.
A failed pre-write check never restores stale bytes over someone else's edit.

Status: first production attempt 36353547114 stopped before any application write because the concurrent favicon/share change updated both renderers. The no-write abort was reconciled by PR175. Fresh authenticated read-only console snapshot at 2026-09-27T22:17:57Z pins the actual source, preserves the icon/share changes and reviews 11 exact public-page removals. The source functions targeted by this patch are unchanged by the icon work. Snapshot SHA-256: abe3f9c2cd45b45e59f208b5cc74f0f4dff936c5caefd03603845213b1bff99a. All 54 tests pass. Fresh production plan, storage evidence and owner authorization are prepared; publication is not complete.
