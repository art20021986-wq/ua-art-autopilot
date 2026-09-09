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

## Verification

Run from the repository root:

```sh
python -m unittest discover -s cloud/spec_rebuild10/tests -v
```

Tests use synthetic local databases and injected transports/receipts. They do not
prove live source extraction, actual server process shutdown or site publication.
`evidence/private-copy-preparation.json` reports32 actual snapshot page-copy
checks, not32 deployed pages. Local Python3.12 execution and Python3.10 syntax
compatibility are separate from target-server runtime acceptance.

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
2. Complete the actual data installer: verified ownership handoff, durable backup
   and journal for32 HTML files and new database, conditional UA0016 year update,
   unchanged full rows for protected drafts17/18, recovery after interruption and
   conditional rollback. The old17-module code installer alone is insufficient.
3. Bind the new runtime factory and worker to the verified existing supervisor,
   current-row reader and authorized lifecycle publisher/readback verifier. No
   route is fabricated by this module. Validate add/edit/hide/delete/re-publish
   against the actual target candidate, including its standard shell generator.
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
