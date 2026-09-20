# Legacy deletion state candidate

Status: **LOCAL CANDIDATE; NOT INSTALLED; NOT STAGE B PASS.** No production
write was performed by this subtask. Current-source evidence was observed
in read-only probes `35524475591` and `35525152538`. The core intentionally
does not import the uninstalled V5 runtime or change the `cars` schema.

## Atomic state and caller contract

`deletion_state.py` has no import-time I/O. The installer must review the
actual current application schema, triggers, foreign keys and `db.py`
connection locking, take the approved backup, and supply the approved digest
from `application_schema_sha256(conn)`. Calling that inspection function is
not approval. `install_additive_schema(tx, approved_application_schema_sha256=...)`
creates only three additive tables, explicitly in the caller's transaction.
Existing tables with different definitions cause a refusal.

Lock order is existing shared publication fence, then caller-supplied
connection, then `ImmediateTransaction(conn, require_fence)`, which executes
`BEGIN IMMEDIATE`. The caller must explicitly `tx.commit()` while still
holding the same fence. Exiting the transaction context without that commit
rolls back, including on interruption. Never commit/rollback the underlying
connection behind the transaction object, catch a mutation failure and then
commit, or put unrelated work inside its transaction. `foreign_keys=ON` must
already be set. Fresh read-only probe `35525152538` confirmed the active
legacy connection: `Soedinenie.execute('BEGIN IMMEDIATE')` acquires the
process `ZAMOK`, then `.crm_db.lock`; commit/rollback releases both. The
intended adapter therefore enters the shared publication fence first,
calls `db.connect()`, then starts the short `ImmediateTransaction`.
This source inspection is not live-schema migration acceptance.

The core currently refuses **all triggers on cars** and **inbound foreign
keys with cascading/SET NULL/SET DEFAULT delete actions**, even if a schema
digest has been supplied. Such actions need a separately reviewed narrow
implementation to preserve unrelated rows. A RESTRICT/NO ACTION foreign key
can still correctly refuse a deletion until the associated target records
are handled by a reviewed coordinator.

## Public API

```python
store = DeletionStore(
    approved_application_schema_sha256=reviewed_schema_digest,
    verify_retirement=trusted_live_retirement_verifier,
)

with existing_publication_fence():
    with ImmediateTransaction(conn, require_existing_fence) as tx:
        token = store.confirm(tx, car_id=actual_database_id, actor_id=staff_id)
        tx.commit()

# Button data: car_delok:<token> (42 bytes; the token is 32 hex characters).
# Keep existing staff ACL. Bare legacy car_delok:<numeric_id> is not accepted.
with existing_publication_fence():
    with ImmediateTransaction(conn, require_existing_fence) as tx:
        intent = store.admit(tx, token=token, actor_id=staff_id,
                             plan=exact_plan, backup_sha256=backup_digest)
        tx.commit()

# Exact site/media retirement and HTTP observations are coordinator work.
# Re-enter the fence and short transaction for each durable completion step.
with existing_publication_fence():
    with ImmediateTransaction(conn, require_existing_fence) as tx:
        store.finalize_row(tx, operation_id=intent['operation_id'], proof=proof)
        tx.commit()

# After a further live read-back, mark complete. Only then may UI say deleted.
with existing_publication_fence():
    with ImmediateTransaction(conn, require_existing_fence) as tx:
        store.complete(tx, operation_id=intent['operation_id'], proof=fresh_proof)
        tx.commit()
```

`confirm` persists the actor, actual ID, exact code, normalized VIN and full
typed SQLite row. `admit` atomically saves the original row, deletion intent,
outbox job and expected post-admission row, and sets only `published=0` in
the car row. Repeated clicks, including two confirmations made before the
first admission, return the existing operation. A changed price, photo
field, code, VIN or other row value refuses the old confirmation.

`finalize_row` compares every current value to the expected post-admission
row in the same write transaction, requires bound verified retirement
evidence, deletes only that identity, and records `ROW_DELETED` together
with its job. It preserves operator edits by refusing changed rows; it does
not roll the whole database back or insert an old car snapshot.

`pending(tx)` returns original durable jobs to resume. A missing row may
resume only an already committed intent AND job. A legacy deletion that
already lost its row and never created an intent requires the separately
authorized incident repair; it cannot fabricate a routine deletion job.

`require_writable(tx, car_id=..., car_code=..., vin=...)` rejects any existing
deletion intent matching ID, code or nonempty normalized VIN, including
completed intents. The writer must independently re-read the live row and
publication state under the same fence immediately before its effect.

## Schema for read-only writer guards

`ua_delete_intents` is the permanent deletion reservation:

| Column | Meaning |
|---|---|
| `operation_id` | Original 64-hex operation key |
| `car_id`, `car_code`, `vin` | Actual ID, exact `UA-0002` code, normalized VIN |
| `actor_id` | Staff identity resolved and authorized by the caller |
| `snapshot`, `snapshot_sha256` | Complete original typed row before mutation |
| `expected_snapshot`, `expected_snapshot_sha256` | Same row with only `published=0` |
| `plan`, `plan_sha256` | Bound exact retirement inventory |
| `backup_sha256` | Verified backup manifest reference supplied by coordinator |
| `state` | `REQUESTED`, `ROW_DELETED`, `COMPLETE`; every state blocks writers |
| `proof`, `proof_sha256` | Latest bound verification evidence |

`ua_delete_jobs(operation_id,state)` has one row per intent, with states
`PENDING`, `ROW_DELETED`, `COMPLETE`. Neither table is a child of `cars`.
`ua_delete_confirmations(token,actor_id,car_id,car_code,vin,snapshot,snapshot_sha256,operation_id)`
keeps callback identity independent of the current row. Tokens cannot be
transferred to another actor. Identity/code reuse remains blocked after
completion; a future resale needs a separately reviewed new-identity rule.

## Retirement binding

Plan keys are exactly `mode`, `car_code`, `public_targets`, `list_surfaces`,
`media_targets`. Target lists are sorted unique exact strings, produced by
the trusted current-route resolver, never prefix globs. `PUBLIC_OR_RESIDUAL`
requires public and list surfaces. `NEVER_PUBLISHED` requires `published=0`,
no public targets and explicit list surfaces to inspect. A false current
publication flag alone does not prove that an announcement was never public.
The coordinator must scan and attest that distinction before admission.

Proof binds `operation_id`, `car_id`, `car_code`, `vin`, `snapshot_sha256`,
`expected_snapshot_sha256`, `plan_sha256`; it must repeat every exact target
list and report `all_absent=True`, `counters_match=True`. These booleans are
**not sufficient proof**: the injected trusted `verify_retirement(intent,proof)`
must return exactly `True` after independently checking the current local
after-images, complete aliases/routes, HTTP evidence, counters, and media.
It is called before row deletion and again before completion. The verifier
MUST NOT perform network I/O inside the SQLite transaction/publication lock.
Collect HTTP observations outside those locks first, then bind the fresh
evidence to still-current exact after-images under the fence. The evidence
must include the request/response checks and bounded freshness chosen by the
reviewed coordinator; a boolean supplied by an arbitrary callback is not a
valid production verifier.

## Remaining blockers before activation

1. Live schema/trigger/FK review, approved digest and backup receipt. Active
   `db.py` locking was inspected; the complete connected transaction adapter
   still needs a regression test. No production schema was changed.
2. Trusted exact target inventory, publication-history classification,
   media quarantine/coordinator and fresh retirement verifier. The tests use
   an explicit fake verifier and therefore do not establish live HTTP PASS.
3. Replace the active bot callback with token confirmation, preserve staff
   ACL and the existing `^car_delok:` registration, reject old numeric
   confirmation callbacks, and register resume work. Both patched request
   and confirmation handlers are necessary before enabling this route.
4. Integrate reservation checks at every legacy delayed writer and restore
   path; filter unpublished/tombstoned rows in all shared-page generators.
   An additive SQL trigger defense against stale old code could be reviewed
   separately; this candidate does not silently install one.
5. Check target-specific related CRM records and media inventory. The core
   never deletes media table rows, files, audit history or other cars.
6. Independent integration review, release-bound installer, runtime check,
   live end-to-end tests and truthful final UI notification.

A fully identical row removed/recreated before admission cannot be
distinguished from its original incarnation by legacy row fields alone.
New-creation paths must consult reservations, and old numeric callbacks
must be disabled. If IDs can be recycled before any intent exists, a durable
creation-generation binding is an additional live-schema design decision.

## Final public-write guard candidate

`public_write_guard.py` holds the supplied existing publication fence through
the caller's effect. It reads the current CRM and permanent intents, rejects
deleted or no-longer-published direct pages and canonical/hash/diagnostic
aliases, rejects their links/vehicle markers in shared HTML, and also blocks
stale rollback payloads. Other current cars remain writable. Canonical path
checks precede the backup-path exemption; percent-encoded HTML links are
decoded before identity comparison. A decorative `stage/UA-0002.webp` asset
is not mistaken for an advertisement.

This guard is not automatically registered. Dynamic or escaped JavaScript
membership needs the trusted renderer's exact proposed-membership check;
literal HTML parsing alone cannot prove arbitrary scripts. Caller identity
and creation guards still use the stronger ID/code/VIN core reservation.

**Do not blindly wrap the current spec writer.** Probe `35525152538` shows
`ua_spec84_runtime._writer_guard` acquiring its `WRITER_LOCKS` with raw
`flock`, then the spec lock. Calling the separate reentrant publication-fence
registry inside that raw lease could self-deadlock on the same inode. The
exact safe filenames/order in `WRITER_LOCKS` still need to be bound, and the
guard must be integrated at the outer ownership boundary. This is a concrete
remaining installation blocker, not permission to skip spec protection.

Known source-bound legacy commit points are `publish_transaction_guard._atomic`
and snapshot restore, `publikaciya._zapisat_atomarno` and rollback,
`stranica.zapisat`/`main`/legacy restore, `yadro.zapisat_atomarno`, and
`ua_spec84_runtime._writer_guard`/`_atomic_existing`/post-enrichment commits.
The callback, exact-route retirement adapter, media coordinator, and restart
registration must be connected before these helpers form a complete release.

## Safe preservation set

Only `deletion_state.py`, `public_write_guard.py`, their two test files,
this README and `VALIDATION.json` are intended for a publishable candidate.
They contain newly authored code and synthetic fixtures. Full private
production sources, CRM data and the earlier file-only tombstone experiment
are excluded. The transactional core is the sole proposed state authority.

## Local verification

`python -m unittest -v test_deletion_state.py test_public_write_guard.py`:
**35/35 PASS** — 25 transactional-core tests and 10 public-write-guard tests.
Tests cover
interrupted admission/commit and row finalization, failure between intent
and outbox insertion, duplicate callbacks, actor binding, reused numeric ID,
operator price edits, proof binding/freshness, missing-row resume with and
without original durable jobs, never-published handling with mandatory
nonempty list-surface evidence coverage, preservation of
unrelated rows, code/ID/VIN reservation, schema drift, fence absence, unsafe
triggers and foreign key cascades. Writer regressions cover stale direct and
shared rollback payloads, missing/hidden current rows, nested aliases,
symlink/traversal bypasses, encoded links, missing schema, and preservation of
an unrelated vehicle's write. This is isolated component validation only.
