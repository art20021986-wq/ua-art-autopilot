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

Status: production run 36355030909 FINISHED / PASS. All four source files and 11 public pages were installed and exactly verified. Canonical public index/catalog returned HTTP 200; catalog and UA-0017/UA-0019/UA-0023 matched the exact approved published bytes. UA-0023 now has 37 visible photos and cover 002.jpg; UA-0017 has 39, UA-0019 has 31. CRM and unrelated public files were preserved; bot 266084 resumed enabled and running. All 54 tests passed. Final receipt: state/receipts/CRM-PHOTO-VISIBILITY-INSTALL-20260928.json. Existing originals remain available as technical sources; future OCR intake does not append them to photos.

The first production attempt 36353547114 stopped before application writes because concurrent icon/share metadata changed the renderers. PR175 reconciled that no-write abort. PR182 rebased the exact correction on an authenticated read-only server snapshot at 2026-09-27T22:17:57Z and retained the current icon/share changes. The approved remote package was executed through the authenticated hosting console after the normal backup/open gates; the original Actions controller accepted its bound receipts and independently verified publication. No workflow, runtime, approval, ledger or nonce protections were changed.
