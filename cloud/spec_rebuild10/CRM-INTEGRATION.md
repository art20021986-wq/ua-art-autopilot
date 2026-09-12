# CRM integration — UA-ART-SPEC-REBUILD-10-001 v1.0

Status: **candidate prepared; not installed; runtime bindings absent; no production Gate B PASS**.

## Implemented

`crm_bridge.py` connects CRM events to the new `SpecStore`. A stable allocated
`auto_number` is required; the database row number is never treated as the public
UA number. Identity uses VIN/frame, make/model/year, fuel, engine, transmission,
trim and market. Price, media and logistics changes do not enqueue a duplicate
identity. A changed model/VIN/year creates a new revision; old facts are retained
in their old revision and cannot silently describe a different vehicle.

Saving a CRM row only tracks identity/enqueues collection. In particular,
`cars.published = 1` is not accepted as evidence of an existing web page. Initial
publication requires an explicit owner action, exact verified readiness scope,
accepted visible facts, and a separately configured lifecycle executor. No
default executor exists. The public state is marked verified only after the
external readback verifier accepts the current identity, revision and fact
digest. No automatic first publication of UA-0017 or UA-0018 is implemented.

Hide/sold and delete are recorded only after verified lifecycle completion.
Delete tombstones the UID and cancels queued work without erasing historical
facts. Unknown execution/readback outcomes are reported for reconciliation and
are never automatically retried by the bridge.
The terminal store change is a transactional compare-and-swap of the ticket's
identity revision and fact digest. An identity changed during readback cannot be
deleted/hidden by an older receipt. Action and plan IDs must match the ticket.

## Concrete source wiring

The preparer accepts only the exact four SHA-256 pins in
`prepare_crm_bridge.PINS`, taken from the previously prepared final17-v3 code.
It compiles output source but never imports it. Generated private modules are
not copied into Git and are not installed by this command.

| Existing call site | Prepared change |
|---|---|
| `db.create_card`, `update_card_field`, `set_card_review` | After successful existing commit, send the freshly read row to the new store |
| Final `cars_ui.toggle_publish`, `delete_ok`, `mark_sold_ok` | Use the configured, verified lifecycle route and actual readback |
| `cars_ui.register` legacy worker start | Start only the explicitly configured new worker; no default or second source worker |
| Legacy `car_spec:*` callback messages | Show new status; do not launch the old collector or old manual publisher |
| Legacy specification edit-message handler | Clear stale old editor state; do not consume a later ordinary CRM field value |
| Existing `master_card` / `publikaciya` calls to `ua_additional_spec.inject_public_spec` | Already delegate through `spec_publication`, whose fact loader and renderer now use the new store |
| `spec_publication.load_facts`, `inject`, `render_block`, `validate_page` | Read new canonical facts, require current CRM identity match, render/validate with the new guarded renderer |
| Existing atomic `guard_write` | Retains the prior atomic route and calls the replaced canonical loader/validator dynamically |
| `ua_additional_spec.public_contract_errors` | Validate the new exact block and compare the one displayed VIN with CRM |

The normal card keyboard already removed the mandatory “Дополнительная
спецификация” button in the pinned candidate. It stays removed. The original
ordinary card render is retained, with a new automatic specification status.

## Runtime dependencies still required

The reviewed bootstrap uses `configure_runtime_factory` with these components:

1. `CrmBridge(SpecStore(new_database_path))`.
2. A readiness verifier validating real current Gate B, writer handoff, owner
   role/action, exact plan, identity, revision and fact digest. The bridge
   consumes this authority; it does not generate it.
3. An idempotent lifecycle executor through the approved route, with existing
   backup/rollback and queue safeguards. Its return must include a receipt.
4. An actual public readback verifier. Test dictionaries are not this verifier.
5. A single new worker starter, after confirmed termination/handoff of the old
   processes. No change to HALT or external-writer verification is performed.
6. A read-only current CRM-row reader by unique UA UID.
7. For full-card changes, a verifier of the exact authorized HTML before/after
   hashes, current full CRM-row hash, shell fingerprint, fact digest and plan.

Post-commit hooks cannot be atomic with the existing CRM transaction and a
second SQLite database. Startup/periodic `reconcile_saved_rows` must repair
missed events before readiness approval. It must use a validated complete CRM
snapshot; an incomplete scan never implies deletion.
The post-commit event carries only the stable UID into processing; the current
CRM row is reread rather than replaying a delayed old row. Duplicate UIDs found
in a scan are rejected before either conflicting row is imported.

`SpecStore` connections are thread-affine. The new bootstrap factory creates and
closes one store/bridge inside each outer callback thread. Nested composer calls
reuse the same operation context. The prepared UI runs the lifecycle bridge via
`asyncio.to_thread`; SQLite's thread check stays enabled. The source worker must
own its own store connection through the same factory or its worker entrypoint.

**Full-card edits have a separate guarded route:** the specification-only
renderer still rejects unrelated changes. When the atomic guard encounters an
ordinary full-card edit, it may use the exact change manifest only inside an
active approved publication ticket. An injected verifier must authenticate the
manifest's plan and exact before/after page hashes, current full CRM-row hash,
identity revision, fact digest and preserved shell fingerprint. The new pure
renderer then checks those bindings, canonical specification, one VIN and shell
assets. Missing, stale or mismatched manifests stop the write. The guard has not
been globally relaxed. A real production verifier/manifest producer still needs
to be supplied by the reviewed route.

The old `spec_publication.reconcile_published` entrypoint explicitly returns
`LEGACY_RECONCILER_DISABLED_REBUILD10`. It cannot publish an old worker's facts
after canonical reads have moved to the new store.

The old specification administration screen now provides status only. New
manual field/visibility controls are available as store APIs, but their separate
CRM operator UI is not wired here. Existing manual values and hidden flags must
be imported by the migration before deployment.

## Evidence in this stage

- **18/18 tests PASS** using the actual new bridge and temporary actual SQLite
  `SpecStore`: idempotent save, identity revision, media/price stability, editor
  cancellation, required facts/owner/Gate B, failed and accepted synthetic
  readback, fact-change race, hide/delete history, and unconfigured runtime.
- Additional tests cover per-thread factory connections and an actual temporary
  SQLite + HTML cycle: manual publication, price edit through an exact synthetic
  change manifest, hide, republish, delete, and preserved fact history. The
  executor/authority in this test is explicitly synthetic and performs local
  fixture writes; it is not the PythonAnywhere production executor.
- A concurrent second SQLite connection changing the vehicle identity inside a
  deletion readback verifier is rejected by the terminal compare-and-swap; the
  new identity and its queued job remain active.
- The exact four pinned private input modules produced four compilable source
  candidates at `private-runtime/rebuild10-crm-candidate-v2`.
- These are local integration and source-preparation checks. They do not prove
  Telegram dispatch, running server bootstrap, network extraction, actual page
  publication, external-writer drainage or production Gate B.

Owner sequence remains: verify the existing 16 cards, then the owner publishes
UA-0017, verify its real link, then the owner publishes UA-0018.
