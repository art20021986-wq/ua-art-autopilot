# Durable specification storage: implementation contract

Task: `UA-ART-SPEC-REBUILD-10-001 v1.0`.

`store.py` is a new local SQLite component, Python 3.10+, standard library only.
It creates its own database at a caller-selected path; it must never be pointed
at the existing CRM database. It contains no network calls, live CRM imports,
HTML writes, process controls, or deployment mechanism.

## API

| Call | Result and behavior |
|---|---|
| `SpecStore(path, max_attempts=3)` | Open/create the separate store. DELETE rollback journal, full synchronization, foreign keys. WAL is not assumed safe on the target shared filesystem. Per-job attempts remain durable; reopening with a different default does not change existing job budgets. |
| `upsert_vehicle(uid, identity, published=False)` | Return `{uid, revision, identity_hash, queued}`. Supply a complete identity, not a partial update. A changed identity increments the revision, cancels older active work, and creates one new job. Repeated saves and changes only to price, photos, descriptions, or delivery fields do not create work. The published argument records observed CRM state; pass the existing state when saving an existing car. No car is physically published. |
| `get_vehicle(uid)` | Return current identity, revision, hash, published/tombstoned flags. Deleted IDs remain inspectable. |
| `claim_job(worker_id, lease_seconds=60, now=None)` | Atomically return one job, or `None`. Returned dict includes `id`, alias `job_id`, `uid`, `revision`, `identity_hash`, normalized `identity`, `lease_token`, attempts and deadline. Lease range 1–900 seconds. |
| `fail_job(id, token, error, retry_after=30, now=None)` | Bounded retry, then `exhausted`. Does not delete accepted facts or snapshots. |
| `request_refresh(uid, reason, request_id)` | Explicitly rearm succeeded/exhausted work once per stable operator request. Refuse pending or leased work. Store the previous terminal job state and request durably. Repeated request IDs do not reset attempts again; a changed reason or identity with the same ID rejects. Never call automatically from a save hook. |
| `approve_candidates(id, token, facts, now=None)` | Validate current unexpired lease, merge only verified nonconflicting source facts, and finish collection. Return accepted/review/rejected counts. This is factual acceptance, not permission to publish. |
| `import_legacy(uid, facts, receipt_id)` | Import historical data idempotently and return imported/review/rejected counts. A receipt cannot be reused for changed content or a new identity revision. Historical source/status fields remain intact; `legacy_import.fresh_verification` is always false. |
| `get_facts(uid, include_hidden=False)` | Only the current identity revision. Omit hidden facts by default. Historical revisions remain stored but cannot leak into a changed car. |
| `get_candidates(uid)` | Current revision's accepted, review, and rejected observations, with reasons and original input. |
| `set_manual_fact(uid, fact)` | Explicit owner change. Set `manual=True`, `verification='manual'`; preserve hidden status unless explicitly changed. Owner authorization is enforced by the caller. |
| `set_hidden(uid, key, hidden)` | Explicit owner visibility change. Fact remains stored. |
| `set_published(uid, published)` | Record observed publish/unpublish state only; retain all facts. |
| `delete_vehicle(uid)` | Tombstone ID and cancel jobs. Late results are rejected. Does not reuse IDs or erase historical evidence. Actual CRM/site deletion remains the existing route's responsibility. |
| `get_jobs(uid=None)` | Inspect durable job states. No implicit retry of exhausted work. |
| `facts_digest(uid)` | SHA-256 of the exact current visible fact payload, including its metadata. |
| `mark_publication_verified(uid, revision, receipt)` | Record a verified external publication snapshot and observed published=True atomically. Requires the current identity and exact facts digest. Never performs publication itself. |
| `mark_lifecycle_verified(uid, action, revision, identity_hash, facts_digest, receipt)` | Atomically record authenticated hide/sold/delete readback only if the exact identity and facts remain current after external readback. Preserve facts, cancel jobs only on confirmed delete, reject stale results and reused receipts. The bridge authenticates the receipt and checks its plan ID against the owner ticket first. |
| `get_publication_snapshot(uid)` | Last externally verified snapshot for the current identity revision, or `None`. It is separate from the newest factual candidates and canonical values. |
| `close()` / context manager | Close the connection. |

Identity includes VIN, make/brand/manufacturer, model, year/model year, market,
engine/fuel/gearbox, generation, trim/variant, chassis and other enumerated
identifying attributes. Normalization handles whitespace, VIN casing and numeric
year formatting. Identity keys and aliases are listed in `IDENTITY_FIELDS`;
callers should use one stable schema rather than alternate between aliases.

## Fact shape and conflict rules

Canonical fact fields:

```json
{
  "key": "length_mm",
  "value": 4900,
  "unit": "mm",
  "source_url": "https://example.org/catalog/synthetic-car",
  "verification": "verified",
  "manual": false,
  "hidden": false
}
```

The example is synthetic. Other metadata is retained without alteration.
Legacy aliases are `field_key`, `field_value`, `is_manual`, `is_visible`, and
`verification_status`. Source-domain JSON, original dates and original source
labels are preserved. A historical `VERIFIED_10SRC` label is not interpreted as
fresh ten-source verification.

Trusted direct callers can supply an explicit `verified`, `confirmed`, or
`official` verification value (or boolean true), a source URL, and no conflict.
The source resolver's exact `MODEL_VERIFIED` and `VEHICLE_VERIFIED` statuses are
accepted only with a `policy_acceptance` object bound to the current UID,
revision, identity hash, nonempty source IDs, and the exact original fact digest.
The binding must declare policy `UA-ART-SPEC-REBUILD-10-001:v1` and decision
`ACCEPTED`. `evidence_sha256` hashes the raw fact excluding only
`policy_acceptance`, using UTF-8 JSON, sorted keys, `ensure_ascii=False`, compact
separators and `allow_nan=False`. Only a successfully accepted fact receives
internal `verification='verified'`; its precise original status is retained.
`DOCUMENT_CANDIDATE`, `IDENTITY_ONLY`, historical `VERIFIED_10SRC` and other
unsupported status values cannot bypass review by also asserting
`verification='verified'`.
Automatic candidates cannot claim manual authority or newly hide owner data.
The collector must additionally verify the approved source policy, actual
vehicle matching, original source evidence, and access rights before calling
the store. This module does not prove those external facts from a string label.

Conflicting sources in the same batch are all held for review; ordering cannot
make the first source win. A different value never overwrites an existing value
automatically, including an owner override. Same-value additional evidence is
stored separately while retaining the original source and owner flags.
Missing values and explicit placeholders cannot erase facts. A zero dimension,
door count, displacement, power and other enumerated physical characteristics
is rejected; a legitimate zero, such as tailpipe emissions, is retained.
Rejected legacy inputs remain in candidate history for inspection.

## Publication receipt

The integration layer must authenticate a real route/readback before calling
`mark_publication_verified`. Required receipt fields:

```json
{
  "receipt_id": "unique-real-readback-id",
  "route_id": "verified-route-id",
  "uid": "CURRENT-UID",
  "revision": 1,
  "identity_hash": "current identity SHA-256",
  "facts_digest": "current visible facts SHA-256",
  "status": "PASS",
  "specification_visible": true,
  "single_vin": true,
  "shell_preserved": true,
  "verified_at": "actual timestamp",
  "page_url": "https://actual-published-page"
}
```

This is a format example, not a real receipt. The database validates its binding
and required checks; it cannot authenticate the route or prove a web page exists.
Receipt IDs are idempotent and cannot be reused with different content. A replay
of a previous receipt cannot reverse a later unpublish. New collection results
cannot change a previously verified publication snapshot. Identity changes
isolate older snapshots instead of presenting them as evidence for a new car.

Non-publish receipts require `uid`, `action` (`hide`, `sold`, or `delete`),
`revision`, `identity_hash`, `facts_digest`, `status='PASS'`, `receipt_id`,
`route_id`, `verified_at`, and `plan_id`. After the bridge authenticates the
actual readback, `mark_lifecycle_verified` rechecks identity and visible facts
inside `BEGIN IMMEDIATE` before mutating state. A different revision or changed
facts cannot be hidden or tombstoned by an older operation. Idempotent receipt
replay performs no new mutation and cannot reverse a subsequent republish.

## Durability and integration limits

Each vehicle/revision has one durable job. `BEGIN IMMEDIATE` serializes claims
across processes using this database. Lease expiration invalidates old tokens,
allows bounded retry, and recovers automatically after a process restart.
Finishing or failing work requires the current token and identity. Deletion and
identity changes invalidate queued or leased older work.

This lock protects the new store only. It does not stop legacy WSGI processes,
protect existing HTML writers, satisfy `EXTERNAL_WRITER_VERIFICATION_REQUIRED`,
or make a cross-database/HTML deployment atomic. Those remain responsibilities
of the approved installation and publication route.

DELETE rollback journaling avoids an unverified WAL/shared-memory dependency on
PythonAnywhere shared storage. Production acceptance must still check the real
filesystem's SQLite locking/durability behavior; local tests do not prove it.

There is no real CRM event wiring or deployed worker in this module. It does not
automatically publish drafts UA-0017/UA-0018. It does not retry exhausted jobs
indefinitely or create an external automation. After an approved source becomes
available, an authorized caller can use `request_refresh` with a unique
idempotency key; each explicit request has the original bounded attempt budget.
A periodic refresh policy is not enabled; repeat owner saves remain idempotent.

Tests use synthetic identities, disposable local databases, and `example.org`.
They exercise duplicate events, independent connection claims, restart/lease
recovery, bounded failures, late completion, identity isolation, tombstones,
manual/hidden preservation, historical import, conflicts, zero placeholders,
and separation of current data from verified publication snapshots. These
tests are not a production Gate B or proof that any public card changed.
