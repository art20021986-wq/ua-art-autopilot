# Prepared concrete runtime bootstrap

`bootstrap.py` now provides actual CRM SQLite reads, exact-operation authorization,
public response comparison, startup reconciliation, bounded worker handoff and an
adapter to the existing pinned `card_lifecycle._transition`. Import has no effects.
`prepare_bootstrap.py` verifies four real candidate source hashes, compiles them
without importing the application, and produces `spec_rebuild10_bootstrap.py`.
The controller calls its `install_runtime(controller)` exactly once after handoff.

## Actual bindings

- `CrmRows`: opens existing SQLite with `mode=ro`, query-only and a read transaction;
  reads every complete current row, checks SQLite integrity and rejects duplicate
  UA numbers before reconciliation. It does not import `db.py`, monkeypatch global
  SQLite, ignore WAL using `immutable=1`, or infer public IDs from database IDs.
- `ExactPlan`: rereads the exact approved plan bytes and independently authenticates
  current controller/owner/writer authority on every operation. Its precomputed
  before/after HTML hashes and generator source pins must match the requested page.
  It checks the real full CRM row; only the existing lifecycle's `published`,
  `publish_pending` and operation-bounded UTC `updated_at` changes are accepted.
  Price, identity or other business changes require their own exact reviewed plan.
  This handles the actual lifecycle updating CRM **before** the ordinary generator.
- `PublicReadback`: calls only the supplied approved bounded HTTPS transport, rejects
  redirects, wrong hosts, stale exact page hashes, wrong VIN and noncanonical facts.
  Withdrawal needs actual 404/410 evidence for the exact UID primary and diagnostic
  paths. The canonical /video/ primary, diagnostic and catalogue surfaces are
  mandatory; the catalogue must contain the UID link on publish and exclude it
  on withdrawal. Arbitrary same-host 404 responses cannot satisfy this check.
- `LockedLifecycle`: binds already loaded pinned modules, compares critical loaded
  Python function bytecode with their exact source, retains the existing reentrant
  lock through execution and public readback, and reads the actual durable
  `ua_spec_lifecycle_archive` COMPLETED record plus its backup manifest. The legacy
  rollback/recovery path remains active. Its separate FULL-synchronous SQLite
  operation ledger prevents automatic second execution after a crash or unknown
  outcome. It does not assume `(True, message)` proves public visibility.
- `WorkerService`: startup/each tick reconciles a complete current CRM scan and then
  handles at most one queue job. The existing verified supervisor registers the
  callback once; this code does not start another thread, daemon or automation.
  `attach_public_sync` connects the durable specification-only outbox to that same
  tick; accepted facts automatically update already verified published cards.
  See SYNC.md for authority, backup, readback and crash-stop behavior.
  Unprovisioned sources preserve the queue and accepted facts.

## Remaining external authority

The bootstrap deliberately cannot create the controller's owner authorization,
old-process drain proof, live module-load proof, existing supervisor registration
or allowed network access. The data installer's `DATA_LOCAL_COMMITTED` receipt is
**insufficient** to start the new worker: it reports `runtime_loaded_verified=false`
and does not prove that old writers are stopped. Its status is not converted into
`old_workers_stopped=true` by this code. The real controller must provide a separately
authenticated runtime/handoff receipt and its verification capability.

`install_runtime` must run before `cars_ui.register` calls the configured worker;
no import-time fallback auto-configures these dependencies. UA-0017 and UA-0018 still
require owner actions. A current verified UA-0017 snapshot is required before 18.

The source transport providers and supplier rights remain explicitly provisioned;
selecting ten sources does not claim ten working live adapters.

## Evidence

22 local temporary-SQLite tests pass: real current read-only rows, duplicate IDs,
write denial, plan expiry/tampering/owner scope, real business-row race, exact page
manifest versus echo, valid and stale HTTP bodies, changed facts, mandatory handoff,
one supervisor registration, durable no-repeat after an interrupted lifecycle,
verified receipt replay after the CRM published flag changes, and zero unintended
publications. The lifecycle interruption/replay tests use a synthetic lock/executor;
the ledger and current-row checks are the actual adapter code. All test authority
and HTTP providers are explicitly synthetic. These tests do not certify a running
Telegram bot, actual supplier extraction, production writer drain or live Gate B.

Command: `python -m unittest discover -s cloud/spec_rebuild10/tests -p test_bootstrap.py`.

The current private entrypoint hash is recorded in the regenerated
`bootstrap-manifest.json`; version 2 additionally attaches automatic spec sync.
