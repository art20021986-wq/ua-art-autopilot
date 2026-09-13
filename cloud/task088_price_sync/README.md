# TASK088: durable price-publication outbox candidate

Status: **LOCAL CANDIDATE — NOT INSTALLED, NOT A PUBLISHER**. No production,
CRM, Telegram, PythonAnywhere or repository runtime is changed by importing it.

The outbox closes the “price committed, publication intent lost” gap. The
`outbox.py` library takes the **same SQLite connection and transaction** used
for the CRM price/audit update. It never opens a connection, commits, rolls
back, starts a worker, makes network requests or imports live CRM modules.

## Implemented and checked locally

- Explicit transactional creation of one dedicated table; no `cars` migration.
  An unexpected existing outbox schema is rejected. `executescript` is not used.
- Price update, audit rows and publication intent can commit or roll back as a
  unit; another connection cannot see the intent before commit.
- Stable mutation keys deduplicate repeats and reject payload conflicts.
  Replaying an old mutation after a newer revision is rejected, so the caller
  rolls back the attempted stale price write.
- Per-car revision follows SQLite's serialized write/commit order. Timestamps
  are evidence, never ordering keys. Rolled-back revisions are not published.
- A newer revision supersedes only pending work. Claimed or stopped work is
  retained and blocks that car until a separate verified reconciliation.
- Exclusive durable claims have unique nonces. No timeout automatically releases
  a claim, no stopped event retries itself, and stale nonces cannot acknowledge.
- Before and after publication, the current claim must still be the latest
  revision. Stopped attempts cannot become published after a later good readback.

`record_verified_publication` is a **storage boundary**, not receipt validation.
Supplying a syntactically valid hash does not prove publication. The trusted
adapter is responsible for constructing and verifying real evidence first.

## Mandatory integration boundaries

1. Install the dedicated table only under the normal backup/rollback and Gate B
   process. Call `install(conn)` inside an explicit `BEGIN IMMEDIATE`, inspect
   its result, then let the installer commit. Never run schema DDL on import or
   inside the Telegram callback. Rollback must preserve committed prices and
   all pending intents; do not delete the outbox to simulate success.
2. Wire the actual Stage 2 price handler, including every other allowed price
   writer, using the same CRM connection. Preserve both price fields, Ukraine
   price history and audit semantics. Read both amounts from the updated row,
   then `enqueue(...)` immediately before that connection's commit. Any error
   must abort the whole price/audit transaction and produce no false success.
3. Supply a stable mutation identity from the Telegram update/CRM operation;
   hash its unambiguous, versioned encoding to `event_key`. A fresh random ID on
   every delivery cannot deduplicate the same mutation. Before replaying an
   operation, reconcile its event and current CRM state. Treat conflict/stale
   event exceptions as failures, never ignore them and commit the price anyway.
4. Only already-published cars enter this automatic update route. Preserve the
   owner's manual **Разместить** action for initial vehicle publication. Map
   internal `car_id` to the verified current public UA identifier; never assume
   their numeric components are interchangeable.
5. The worker must use the reviewed current renderer and a shared catalog
   publication lock covering **all writers**, not just a per-car lock. The
   outbox cannot fence filesystem writes or another process by itself. Build
   card/catalog output off to the side; verify prices and non-price invariants;
   re-read committed CRM and outbox revision before switching public output.
   Publishing one old complete-catalog snapshot must never erase another edit.
6. After writes, parse the public card AND catalog and read committed CRM. Bind
   evidence to the exact operation, car, both prices and revision; apply
   `price_publication.publication_decision`. Only verified matching observations
   permit recording a published receipt. HTTP 200 alone is insufficient. The
   60-second SLA starts at CRM commit, so the adapter must bind an actual
   commit-time observation (the pre-commit `created_ms` is only a conservative
   enqueue timestamp). Late verified publication still requires failure/SLA
   notification policy; it is not an on-time success.
7. On any uncertain/failed attempt, stop and persist its sanitized reason. Keep
   the new committed CRM price. Send the first incident alert to the owner's
   verified private CRM-bot chat, then include unresolved status in the daily
   10:00 Vietnam report. Telegram transport/deduplication and durable delivery
   acknowledgements are **not implemented here**.
8. Never automatically reset `CLAIMED` or `STOPPED`. A crash, stale claim or
   partially changed public site requires actual reconciliation and existing
   recovery gates. A dedicated recovery transition with verified evidence is
   still required; the absence of such a transition is deliberate fail-closed
   behavior, not a completed recovery implementation.

## Local verification

From the repository/workspace root:

```sh
python -B -m unittest discover -s cloud/task088_price_sync -p 'test_*.py' -v
```

Verified: **15/15 tests passed**. Tests use isolated temporary SQLite files and
real independent connections for commit visibility and competing claims. They
cover atomic CRM/audit/event rollback, duplicate/conflicting/stale edits,
revision supersession, durable STOP, nonce fencing, explicit transaction
ownership and unknown-schema rejection. No test contacts the live system.

Remaining proof before installation: current source/schema compatibility,
stable mutation identity, hook placement, preservation checks on real renderer
fixtures, locked atomic card/catalog deployment and rollback, durable worker
and notifications, public readback within 60 seconds, and stage acceptance.
