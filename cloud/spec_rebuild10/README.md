# UA-ART-SPEC-REBUILD-10-001 v1.0

The owner approved a new implementation and the ten named sources on 9 September
2026. This branch contains the new module, private-copy verification evidence and
integration preparation. It does not install or enable code on the live CRM/site.
The historical restoration branch/PR79 remains reference evidence.

## What works in this candidate

- `store.py`: a separate durable specification database, revisions, bounded job
  leases, idempotent refresh, manual/hidden priority, tombstones and independent
  externally verified publication snapshots. DELETE journalling is the default;
  opening an unrelated CRM database is refused before mutation.
- `sources.py` / `sources.json`: exactly the ten approved suppliers, exact variant
  matching, controlled provenance, conflict review, vPIC identity parser and a
  trusted normalized import format for the other nine. See `SOURCES.md` for the
  actual provisioning boundary; site availability is not adapter acceptance.
- `worker.py`: real queue → injected collector → parse → resolve → durable fact
  acceptance, with stale-result and duplicate-work protections. It never
  publishes cards. `WORKER.md` describes the explicit supervisor integration.
- `render.py`: native visible additional-specification link and expanded section,
  one visible VIN, escaped facts, approved citation URLs and guarded composition
  retaining the known shell. Historic provenance is not presented as new source
  verification. The spec-only composition path preserves all other bytes.
- `crm_bridge.py`: saved-card hooks and owner lifecycle tickets; current identities,
  fact digests, row hashes and externally verified readback are checked before
  recording publication. No default production route or automatic daemon exists.
- `prepare_crm_bridge.py`: pinned transformation of four private CRM modules,
  switching old collector startup and public specification readers to explicit
  new bindings. It writes a separate candidate directory and never imports the
  private live runtime. See `CRM-INTEGRATION.md` for required configuration.
- `prepare_snapshot.py`: pinned read-only snapshot migration. Its private output
  contains 18 tracked identities (16 published + protected drafts17/18), all557
  historical facts (550 visible,7 hidden), and32 candidate pages. The first CRM
  save is checked not to invalidate the migrated facts. UA0016's owner-approved
  year2017 is applied to the candidate; live CRM remains unchanged.

- `data_install.py`: executable data transaction for32 pages, the new store and
  the approved UA0016 year cell, using the already-held real writer lease.
  Durable backup/journal, conditional rollback, terminal readback and unknown-
  outcome handling are implemented. See `DATA-INSTALL.md`.
- `bootstrap.py`: concrete read-only CRM provider, independently authenticated
  exact lifecycle plan, current card/diagnostic/catalogue readback and existing
  supervisor registration. No placeholder callback grants real authority.
- `source_provisioning.py`: pinned reviewed capture/normalization binding for
  approved sources. A reviewed Kia2023 LPI model candidate is included; exact
  vehicle mapping and source access remain separate.
- `stage_verify.py`: relocatable actual-private-copy install/readback/rollback
  harness. Its authority is explicitly synthetic and its writes are confined
  to a new throwaway directory; input files and live application stay unchanged.

- `sync.py`: automatically queues accepted fact changes for already verified
  public cards, updates only the specification region and checks actual card,
  diagnostic and catalogue readback. Durable backup/outbox stops unknown outcomes;
  it never publishes drafts17/18. See `SYNC.md`.

## Verification

Target-server verification on **Python3.10.12** completed at **15:20:26 UTC,
9 September2026**: **197/197 tests PASS**,28 private runtime Python sources
compiled without import, and an actual32-page/18-row copy install/readback/rollback
PASS.557 facts preserved,550 visible,7 hidden; all32 pages have one VIN and the
native visible link, with unchanged bytes outside approved regions. See
`evidence/target-stage-r2.json`. The first target run exposed a Python3.10 SQLite
authorizer incompatibility; its13 failures are retained and the fix is covered
by regression tests. Live production has not been changed.

Run from the repository root:

```sh
python -m unittest discover -s cloud/spec_rebuild10/tests -v
```

Tests use synthetic local databases and injected transports/receipts. They do not
prove live source extraction, actual server process shutdown or site publication.
`evidence/private-copy-preparation.json` reports32 actual snapshot page-copy
checks, not32 deployed pages. Runtime, data and source tests are also synthetic. Read the dated target-server
receipt in `evidence` for the exact runtime and scope; do not infer deployment
from a test executed on the same host.

The snapshot compiler requires the exact private source snapshot and previously
reviewed restoration payload. Missing or changed inputs fail closed; do not
replace input pins merely to make a different snapshot pass. Its output contains
private data and must stay outside public GitHub. A fresh production plan must
revalidate current source files and all18 CRM rows within the verified writer
window; the earlier copy is not a globally atomic live snapshot.

## Remaining deployment work

1. Establish the exact target market from vehicle/source documents (all18 captured
   CRM rows lack that field), then provision and validate each source connection against an exact historical
   document/API schema, permitted access/storage/display, correct market/model
   year/fuel/gearbox, and independently checked control facts. None of ten has a
   fresh live PASS in this change. Paid subscriptions require a separate purchase
   decision; selection approval does not buy a licence.
2. Connect the completed data transaction to actual verified ownership handoff.
   Its real-copy install/rollback is checked; actual holder-death recovery still
   needs an authenticated recovery controller. The old17-module code admission
   does not admit this new runtime package; see `RUNTIME-PACKAGE.md`.
3. Supply the completed runtime providers with the real verified supervisor and
   controller authority, install the versioned runtime package and verify loaded
   code. The candidate does not fabricate that controller or installation proof.
4. Close pre-install GateB against the exact plan, package, backup/rollback and
   route. Obtain the separate exact-plan command if required by that route. Only
   then stop/drain the old writers, obtain fresh proof and install transactionally.
5. Read the actual16 public cards back and verify source/store/render alignment,
   one VIN and shell preservation. Tell the owner to click17 only when it is
   genuinely ready; verify17's real receipt before the owner clicks18.

Full GateB is pending. HALT and EXTERNAL_WRITER_VERIFICATION_REQUIRED remain in
force. Do not create a duplicate production request, rerun TASK120 or treat the
private Preview as a publication receipt. No autonomous production task is added
by this branch. The acceptance conditions are in `GATE-B.md`.
