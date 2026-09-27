# Technical source photos stay out of public galleries

Owner request: remove the technical specification screenshot from UA-0023 and
keep future photos submitted for OCR/data entry out of the vehicle gallery.

This release stops `ai_filter.save` from appending input photographs to `photos`;
the inbox linkage and existing video behavior remain. Both public gallery and
cover selectors respect `hidden_photos` through the existing synchronization
ledger. Dedicated vehicle-photo editors remain available.

The preview checks exact current source hashes, builds and compiles candidates,
and verifies UA-0023 has 38 files with exactly 001.jpg excluded (37 public photos).
It produces a reviewable diff. The separately authorized critical source install
requires that exact plan, backs up source and CRM, holds writer locks, pauses and
resumes the existing bot, and verifies unchanged CRM, pages and pending requests.
It has a tested rollback. Publication is a separate acceptance step.

Status: prepared locally; production installation and public verification pending.
