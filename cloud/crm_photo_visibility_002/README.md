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

Status: authenticated R6 preview PASS for UA-0017/0019/0023. R7 refreshes exact sources and public snapshots after the overlapping desktop-gallery installation, retaining its controls. 54 tests PASS; source hashes pin the reviewed desktop release. No photo correction installed yet.
