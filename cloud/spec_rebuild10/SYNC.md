# Automatic synchronization after accepted facts

`sync.py` closes the worker-to-public-page gap. The generated bootstrap attaches
`SpecSync` to the same `WorkerService` supervisor tick. A completed bounded
collection is followed by a scan for changed accepted facts and at most one
specification-only HTML synchronization. A source error stops that tick before
HTML synchronization; an unresolved sync outbox prevents further worker ticks.

Only a card with both a current CRM `published=1` row and a previously verified
publication snapshot for the same store identity/revision can enter the outbox.
The initial 16-card installation must supply actual readback receipts first.
Drafts UA-0017/UA-0018 remain excluded until their separate manual publication
has completed and been verified. Sync does not call the first-publication route,
change CRM fields, rebuild the catalogue or remove cards.

Under the existing reentrant publication lock, sync reads both `video` and `site`
primary pages, verifies the old canonical block against its accepted publication
snapshot, composes only the new specification region, and binds exact before/after
hashes, current full CRM row, fact digest/revision and unchanged diagnostics and
catalogues into a plan. `controller.authenticate_automatic_spec_sync(plan, phase)`
must authenticate that exact operation under the approved automatic update policy
and current writer ownership; the module does not manufacture this authority.
Normal forward replacements use the existing guarded atomic writer. Real bounded
HTTPS readback of the canonical primary, diagnostic and catalogue must match local
bytes and show the card link before the new publication snapshot is committed.

The separate FULL-synchronous SQLite outbox deduplicates an accepted generation.
It refuses unrelated databases, hardlinks and inode swaps. Each operation persists
its exact plan plus private page backups before changing HTML. On a recoverable
failure it preflights every intended postimage and backup before restoring any
page; the rollback only restores its own exact hashes under separately checked
rollback authority. Replace-then-error is tracked as a write intent. A foreign
edit is never overwritten. Accepted store facts remain available for review.

A STARTED outbox after process death, a failed rollback or an unknown receipt
commit stops execution for reconciliation; there is no automatic second write.
If the publication receipt may already have committed, valid new pages are kept
so HTML is not rolled back behind that receipt. This module does not claim to
provide the server controller's crash-recovery authorization or drain proof.

20 targeted tests pass with actual temporary SQLite databases, actual new store,
renderer, both HTML files, durable backup/outbox, and injected synthetic controller,
lock/forward-writer and HTTP providers. They cover automatic worker integration,
one update only, draft exclusion, identity and business races, partial write and
post-commit failures, full rollback preflight, foreign edits, source/receipt state,
old HTML preservation, and database type/inode protections. They do not constitute
live supplier, controller handoff or production Gate B evidence.
