# Specification worker: concrete bounded service

Task: `UA-ART-SPEC-REBUILD-10-001 v1.0`.

`worker.py` connects the actual `SpecStore` queue to the actual source parsers,
source evidence resolver, and accepted-fact storage. It processes at most one
job per explicit `run_once()` call. It does not import the live CRM, open a
network connection by default, start a daemon on import, change HALT, write HTML,
publish a car or create an external automation.

## Working flow

1. An existing CRM save hook calls `SpecStore.upsert_vehicle` through `CrmBridge`.
   This creates one idempotent job for the current vehicle identity revision.
2. `SpecWorker.run_once()` atomically claims one job and its token/lease.
3. Only explicitly provisioned collector bindings are called. Each receives
   the exact vehicle identity, revision/hash and remaining bounded timeout.
4. Actual vPIC JSON goes through `parse_vpic`; reviewed supplier documents go
   through `parse_normalized_import` with an out-of-band document authorization
   and supplier access/storage/display rights.
5. `resolve_facts` applies exact identity, origin independence, conflict and
   vehicle-equipment rules. Accepted facts receive a policy receipt bound to
   the exact payload SHA-256, UID, revision, identity hash and source IDs.
6. `SpecStore.approve_candidates` verifies that binding and the current lease.
   It stores confirmed facts and durable review/rejection observations. It
   retains previous conflicting values, manual overrides and hidden flags.
   It does not perform publication.

CRM field aliases are mapped explicitly (`brand` → `make`, `transmission` →
`gearbox`). Conflicting aliases fail. Market/model aliases and missing values
are never guessed. Engine displacement and trim must match when the target
identity supplies them. Historical facts are not relabelled as freshly verified.

## API

```python
from cloud.spec_rebuild10.worker import SpecWorker, vpic_collector

# transport is the separately provisioned bounded HTTPS adapter, not a default.
worker = SpecWorker(store, {"vpic": vpic_collector(transport)})
report = worker.run_once()
```

`vpic_collector` is a concrete adapter: it validates a 17-character VIN, builds
the official `DecodeVinValuesExtended` request with optional known model year,
calls the bounded source transport and feeds its JSON response into the vPIC
parser. A Japanese frame number returns `NO_MATCH`; it is not sent as a fake VIN.
Successful vPIC identity decoding alone never produces a confirmed technical
specification or fitted-equipment claim.

The other nine collectors use `CollectorBinding(source_id, collect, access)`.
The trusted collector returns a `CollectedDocument` containing the reviewed
normalized payload and `ImportAuthorization`. There is no speculative supplier
HTML parser or undocumented contracted-API schema. See [SOURCES.md](SOURCES.md).

`bind_worker(store, collectors, installation_receipt=..., verify_installation=...)`
is the explicit installation handoff boundary. It requires an authenticating
verifier and a receipt identifying `spec_rebuild10`, stopped old workers and
exclusive ownership. It only returns the worker instance. The existing verified
server supervisor remains responsible for invoking `run_once` and its timing.
No receipt or verifier for the live server is supplied by this package, and
declaring PASS inside the receipt cannot authenticate itself.

## Limits, errors and races

- Default run budget: 90 seconds; maximum configurable budget: 120 seconds.
  Default lease: 120 seconds; lease must exceed the run budget by at least five
  seconds. Each collector receives at most 15 seconds and 1,000,000 bytes.
- An injected collector/transport must enforce its timeout and streaming size
  limit. A synchronous function cannot forcibly terminate arbitrary injected
  Python code. The worker checks elapsed time and lease again before committing;
  an overrun cannot submit a late result.
- First collector failure stops further collection. The entire in-memory batch
  remains uncommitted, existing facts stay intact, and the store records one
  bounded retry (or exhaustion at its durable attempt limit).
- A delete, identity revision change or expired lease discards the result.
  A second worker cannot claim the same currently leased job. Exhausted work
  is never silently retried forever.
- With no provisioned collector, the worker returns
  `BLOCKED_NO_PROVISIONED_COLLECTORS` **without consuming a queue attempt**.
  Nine suppliers remain `NOT_PROVISIONED`; vPIC is `TRANSPORT_NOT_CONFIGURED`.
- `NO_MATCH` is an honest completed source observation, not a fact or a transient
  fetch error. A successful subset may fill facts while the other source states
  remain unavailable/unprovisioned. No result is labelled ten-source PASS.
- Parsed control documents are reported as
  `DOCUMENT_PARSED_NOT_FULL_ADAPTER_ACCEPTANCE`. Offline/injected evidence cannot
  certify live coverage, supplier availability, or the source-acceptance gate.
- Supplier exception bodies/credentials are not included in ordinary worker
  reports or retry messages. The worker uses fixed failure codes.

When a previously unavailable supplier is later provisioned, the caller may
explicitly request a bounded refresh:

```python
store.request_refresh(uid, reason="Supplier provisioned", request_id="unique-change-id")
report = worker.run_once()
```

The operation is idempotent, preserves previous facts and refuses to replace
ready/retrying/leased work. It is never invoked by the worker itself, by an
identical owner save or by an infinite automatic retry loop.

## Evidence from this implementation

23 local integration tests pass against real temporary SQLite stores, the real
queue and real source parsers/policy. They cover full accepted-fact flow, two
worker connections, duplicate runs, retry exhaustion, lease recovery, delete and
identity races, time budgets, manual/hidden/conflicting fact retention, explicit
source refresh, vPIC transport/parser integration and zero publication actions.

Run: `python -m unittest discover -s cloud/spec_rebuild10/tests -p test_worker.py`

These tests use synthetic documents, local databases and injected transports.
They prove the prepared service works locally. They do not prove live supplier
rights, installation, legacy process termination, public-card visibility or
Gate B. Publication of UA-0017 and then UA-0018 remains the owner's separate
manual action after the approved route and page readbacks are ready.
