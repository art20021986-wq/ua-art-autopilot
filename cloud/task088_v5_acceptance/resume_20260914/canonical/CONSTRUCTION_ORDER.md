# Local construction order after the real Preview evidence is ready

This is preparation for the already authorized release. It does not authorize a
release, create a PASS, or request renewed owner approval. Keep all candidate
private sources/DBs outside the repository. The scripts below do not replace the
actual independent observations or existing canonical workflow.

## Existing commands, in dependency order

1. On the authenticated server run the reviewed `observe_install_inputs.py`
   with the exact `install_package.py` hash and the freshly observed account
   quota JSON. Save its actual hash/count JSON without exposing server sources.
   If quota is absent, its `OBSERVED_QUOTA_PENDING` result is not a build input.
2. Locally run existing `build_preflight_bundle.py` against that observation,
   immutable Stage 2 receipt and real routing evidence. Preserve returned
   archive/bundle hashes. Stage only in a fresh private server directory and
   run the reviewed `preflight.py`; preserve its actual report/candidate hashes.
3. Freeze reviewed code and run existing `build_release.py` only as needed to
   reproduce the flat source closure. Re-run required software/source checks
   after any source change; don't use the historical 443 count as a target.
4. Complete the real full Preview report and raw evidence on this candidate;
   obtain independent current writers/quota/routing evidence. Prepare the
   actual proposed v2 delegation from observed identities/paths/control scope.
   A delegation candidate is not yet installed authority.
5. Run `derive_candidate_parts.py` in its default dry-run mode. It emits only
   proposed-file hashes/counts. If needed, use `--output-directory` naming a NEW
   private local directory to preserve the parts. The helper never writes
   `tasks/`, `state/`, `/home/Carix`, GitHub or the server.
6. The trusted executor completes the actual manifest with explicitly reviewed
   protected scope, deployment directory/evidence paths, and a fresh actual
   nonce. Produce an actual Gate for that exact manifest, then materialize the
   existing owner authorization and bind the final request/activation. Follow
   the hash dependency order in READINESS.md. The parts are not full executable
   request/manifest/activation files and deliberately omit authority fields.
7. In an isolated full candidate checkout run the real `verify-mode`, workflow
   policy, request/Preview and `autostart_intake --validate-only` checks on the
   actual final artifacts. Do not invoke test fixture constructors to produce
   real evidence. Check timestamps at the current clock, never a test clock.
8. Register the verified candidate/main according to the existing exact route.
   Only after fresh final checks add the separate marker-only commit; the
   canonical workflow creates nonce reservation, ledger, claim and transaction.
   Do not create those records to make a local preflight appear runnable.
9. `prepare_install_plan.py` becomes applicable only when real canonical
   claim/transaction evidence exists. Its required evidence set is request,
   claim, transaction, Gate, Stage 2, quota, writers, manifest, owner and full
   Preview, plus routing for the existing homepage policy. Its output stays
   private and immutable and still does not execute installation.
10. Follow real PREPARING backup, OPEN execution/verification and canonical
    reconciliation. Then install the actual v2 binding/config/anchor, reader,
    activate identified processes and finish live Stage 3/4 acceptance.

## Actual input index for derive_candidate_parts.py

The caller creates a small JSON index only after the actual inputs exist. No
filled sample or placeholder input file is distributed with this helper.

Required top-level fields:

- `contract`: `TASK088-ACTUAL-CONSTRUCTION-INPUTS-1`;
- `task_id`: the actual fresh `TASK088-GE-PRICE-SITE-STAGE3-*` identity;
- `baseline_main_sha`: `0c85a6561d80c4d8789b3a482ae41cdaf9d0f667`;
- `inputs`: exactly `preflight`, `preview`, `quota`, `writers`, `routing`,
  `delegation`, `software`. Each reference is exactly `{path, sha256}` pointing
  to the existing real JSON and its independently recorded raw-byte SHA-256.

The helper reads Stage 2 and old mode/runtime/activation from the local checkout
and requires their immutable known hashes. It checks the actual software and
Preview source inventories against current source files, validates real routing
with the reviewed engine and requires the flat release files to match their
source map. It validates fresh Preview/preflight/quota/writers and exact
candidate/database/schema/inventory/published-set relationships. It never
copies candidate source files or includes the delegation contents in output.

Command: invoke `python3 -I -B` on `derive_candidate_parts.py` with `--inputs`
followed by the actual index's absolute path. Add `--output-directory` followed
by a new private local directory only when the dry-run result is reviewable.

The output status `LOCAL_CANDIDATE_PARTS_DERIVED_NOT_AUTHORIZED` proves only the
document derivation and integrity checks performed by this helper. An input's
PASS flag and hash alone do not prove that its observations happened; retain
and independently review the raw evidence. It creates no final Gate or approval
and cannot prove server freshness or writer exclusion by itself.

## Output pieces

- `install_blueprint.parts.json`: fields derived from the real private report;
- `runtime_manifest.parts.json`: candidate full runtime manifest from immutable
  baseline, changing only the reviewed three pins;
- `runtime_registration.parts.json`: deterministic derived runtime bindings;
- `request_execution.parts.json`: exact flat release controller/test/file pins
  and proposed receipt paths (not receipts), still lacking final evidence scope;
- `manifest_fields.parts.json`: actual candidate/delegation hashes and operations;
- `construction_receipt.json`: input hashes, scope and explicit unfinished work.

These `.parts.json` files must not be renamed into canonical request/approval/
activation files and published without completing and validating their actual
document contracts. No `claim.json`, `transaction.json`, `gate.json`,
`owner_approval.json`, launch marker or asserted live acceptance is emitted.
