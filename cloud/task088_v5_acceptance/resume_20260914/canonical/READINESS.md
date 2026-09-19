# PR 114: canonical Stage 3 readiness, read-only evidence

Observed through the connected GitHub app on 14 September 2026. This document
describes the exact reviewed code and repository state, not a new Preview Gate,
server observation, owner approval, installation or production receipt.

## Observed repository state

- Repository: `art20021986-wq/ua-art-autopilot`.
- Main: `0c85a6561d80c4d8789b3a482ae41cdaf9d0f667`.
- PR 114 head: `e146c2ea8c28033050b49ccbebb33aa5276c8788`.
- Both recursive Git trees were complete (`truncated=false`): 2090 main entries,
  2265 head entries. Neither contained any canonical `state/` or `tasks/` file
  named for `TASK088-GE-PRICE-SITE-STAGE3-*` or `TASK088-PRICE-V5-STAGE3`.
- `state/AUTOPILOT_HALT.json` was absent from the complete main tree. This is
  repository evidence at that commit, not perpetual authorization.
- All nine main production transactions were terminal: six FINISHED and three
  ROLLED_BACK. There was no OPEN/PREPARING/ROLLING_BACK transaction in that set.
- Stage 2 receipt `state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json` is
  FINISHED/PASS, closed `2026-09-13T05:56:14Z`, `stage3_allowed=true`,
  `stage1_prerequisite=PASS`, `independent_price_fields=PASS`,
  `original_values_restored=true`.
- Its raw SHA-256 is
  `d0b731b93a73da0d041a1af6e987f0e6634823001a2461bc882c927a588faae7`.
  Its installed `cars_ui.py` preimage is
  `4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde`.
  Never reinstall Stage 1/2 or reuse their task/claim/transaction identity.

Main's AUTOMATIC mode still references the old
`TASK088-STORAGE-OVERRIDE-20260911` registration. The v5 code permits a new
registration but does not create one. Merging the candidate workflow/control
changes alone leaves old runtime pins and must fail `verify-mode`; a passing
software test is not runtime activation.

Fresh software/browser/server work in adjacent directories is owned by the
corresponding execution agents. This report makes no new assertion about their
progress, server processes, current credential presence, or full Preview PASS.

## Inputs required before a real Stage 3 launch

Choose a fresh identity `T = TASK088-GE-PRICE-SITE-STAGE3-<unique-suffix>` from the
approved task. Exact code rules are in `controller.required`, `install_package._validate`,
`control_plane._verify_price_v5_authority` and `autostart_intake.validate_launch`.

| Artifact | Required content / source |
| --- | --- |
| `tasks/requests/T.json` | `control_plane_version=TASK107-R2`, CRITICAL, production true, read_only false, exact changed paths, actual health endpoints, fresh storage probe, execution and critical bindings |
| `tasks/manifests/T.json` | CRITICAL adapter contract, exact source/HTML/schema operations with preimage/after hashes, protected paths, full backup/rollback/live verification requirements, stage3_complete false, installation-only acceptance scope |
| Gate, normally `tasks/gates/T.json` | Actual PASS, tests PASS, production_write false, zero unexpected changes, protected snapshot, manifest hash, raw Preview path/hash, writer-fence hash, backup/rollback readiness, evaluated_at |
| Full Preview | `TASK088-FINAL-V5-PREVIEW-GATE-1`, exact candidate files/DB/schema/system-inventory/published codes, all 24 checks PASS, source_files_sha256, real observation time and linked raw evidence |
| `tasks/approvals/T.production.json` | Existing owner authorization materialized onto this real request/manifest/Gate, exact owner/mode epoch, unique nonce and authorization ID, valid dates; no invented approval |
| quota / writers / routing | Actual authenticated account quota, all existing writers accounted for and VERIFIED, no uncovered writers, actual provider mappings and source-routing proof |
| private preflight | Fresh report, exact candidates, candidate/source/dependency/system inventory hashes, schema-only comparison, independent DB readback |
| delegation v2 | Real reviewed dynamic identity policy, installed-code pins, actual operator/bot/writer/control scope; declaration alone does not prove installation |

`request.execution` references the flat reviewed package
`cloud/task088_v5_install/release/`: controller, backup controller, rollback
controller and exact hashes, two package test files, complete dependency/file
hash closure, and receipts `state/receipts/T.json`, `T-BACKUP.json`,
`T-ROLLBACK.json`. The source map is `release/release_sources.json`.

`manifest.deployment_plan` has contract
`TASK088-CANONICAL-STAGE3-ADAPTER-1`; its install blueprint has contract
`UA-ART-GE-PRICE-STAGE3-INSTALL-5`. Include actual preflight directory/report
hash, exact remote package hashes, owner-matching nonce, and evidence paths
`gate_b`, `quota`, `writers`, `preview_gate`, plus `routing` for the existing
homepage policy. Operations are exactly `production/<candidate-file>` plus
`production/crm.db/schema` with `content_kind=SQLITE_SCHEMA`.

The adapter's evidence called `gate_b` is the original PASS Gate file bound by
`request.critical.gate_a_path/sha256`. It is not the separate
`GATE_B_AUTHORIZED` result returned by `critical_adapter.authorize_gate_b`.

## Hash order and runtime registration

1. Freeze and independently verify reviewed code and exact flat release files.
2. Obtain actual server observation/quota/routing; build and run the existing
   private read-only preflight. Verify exact candidate bytes and source closure.
3. Finalize real delegation v2 and the source/runtime candidate. Finalize full
   Preview on this candidate and preserve all raw evidence.
4. Build actual manifest from the preflight/Preview/writer scope, including
   `install_files_sha256`, `price_event_delegation_sha256`, and
   `runtime_registration`. Hash its exact canonical bytes.
5. Produce the actual evaluated Gate with the resulting manifest hash and raw
   Preview/writer evidence references. The construction helper does not produce
   observations or grant PASS.
6. Assemble request with exact manifest/Gate/controller paths and hashes. For
   the owner authorization subject, only `critical.owner_approval_sha256` is
   temporarily zeroed during digest calculation. Materialize the real existing
   owner authorization, then bind its exact hash into the final request. No
   zero-hash or unfinished request may be persisted as an executable request.
7. Bind activation artifacts to final request, manifest, owner, Gate and Preview
   hashes. Preserve historical mode policy and snapshots byte-for-byte.
8. Validate the completed candidate tree with the real mode, workflow, request,
   Preview and autostart validators before any main change or launch.

The v5 runtime registration files are:

- `state/runtime_activations/TASK088-PRICE-V5-STAGE3.previous-mode.json`;
- `state/runtime_activations/TASK088-PRICE-V5-STAGE3.previous-manifest.json`;
- updated `state/AUTOPILOT_RUNTIME_MANIFEST.json`;
- `state/runtime_activations/TASK088-PRICE-V5-STAGE3.json`;
- `state/EXECUTION_MODE.json`, changing only the three allowed runtime-reference
  fields (`runtime_manifest_sha256`, `runtime_activation_path`,
  `runtime_activation_sha256`).

The previous mode raw SHA is
`11af7c738faa902412d35f0755a0a829df49ec939d32960abf343203f93bb715`;
the previous runtime manifest SHA is
`2b3b75c686a41f4f6a48b2f9e2d57da12574c2b498505150899b66645d7cd2c5`.
Only three runtime code pins change:

- `uaart_critical.yml` to `4523f30fd01fa9e1b578be9e18593101270564cf1f51849df02e887c808fb80e`;
- `uaart_maintenance.yml` to `04e0b6636789d5fe67da3ac3f31ab713603fb71066dd72b0f0f44fcd12346fa5`;
- `automation/control_plane.py` to the exact reviewed candidate hash.

`runtime_registration` also pins the actual `verify_preview.py`, software
`gate.py`, and source `install_package.py`. Its previous snapshots and closed
Stage 1/2 receipts must match the immutable hashes enforced by control_plane.

## Launch and final execution boundary

The actual launch must be a **separate single-parent commit adding exactly one
new regular `tasks/launch/AUTO-*.json` file**. Do not combine it with PR merge,
runtime registration, request or evidence changes. The existing workflow
rejects replayed attempts and any mixed marker commit.

Launch fields: schema `UA-ART-AUTOSTART-LAUNCH-1`, action `RUN_EXACT_TASK`, task,
request path/hash, mode epoch, unique nonce, owner/production authorization
flags, created/expires. Validity is at most two hours; expiry and nonce bind to
the real owner authorization. The helper creates no launch marker.

The workflow owns creation and reconciliation of:

- `state/claims/T.<request_sha>.<run_id>.json`;
- `state/transactions/T.<request_sha>.<run_id>.json`;
- autostart nonce reservation and consumed ledger.

Do not pre-create or fabricate these. Backup runs in PREPARING; installation
and independent verification run in OPEN. Preview/Gate/quota must remain no
older than 30 minutes and writer evidence no older than five minutes. The
installer rechecks authority and writers after the full backup before mutation.
Changing timestamps without performing fresh checks is forbidden.

The successful installation controller explicitly leaves Stage 3/4 incomplete,
autopilot inactive, CRM not restarted, public/Telegram acceptance NOT_RUN.
Its FINISHED result is installation-scope only. Continue actual post-deploy,
private v2 binding/reader setup and real Stage 4 acceptance afterwards.

## Continuous reader requirements and actual capability boundary

GitHub chat access and PythonAnywhere API access do not provide an unattended
server GitHub reader credential. Existing server history recorded the expected
token path absent; this read-only repository review did not recheck that server.
Use only the already approved private credential route; never read/export
secrets or put them into repository artifacts.

Reader config fields: contract/environment/root/repository/ref/task_id,
delegation_sha256/source, max_age_ms/poll_interval_ms, canonical_file_pins,
price_artifacts, token_file/state_path/freshness_path/cache_dir. The actual
reader limits evidence to **30 seconds** and polling to half that maximum.

The binding config pins the separate reader config via `control_reader` outside
the delegation to avoid hash cycles. The anchor pins the finished binding
config and is written last. All private directories/files use the approved
owner-only permissions and are outside public website paths.

`canonical_file_pins` must contain the complete chain read by the real
`verify-mode`: all active workflows, control sources, current and historical
registrations/manifests/modes/approvals/receipts, required historical preflight
dependencies and new protection source closure. Minimal mode-only fixtures in
tests are not production configuration. HALT absence is derived from a complete
fresh authenticated Git tree; no local absence or rewritten stamp substitutes.

After real installation/configuration, the reviewed reader command is:

`python3.10 /home/Carix/uaart_price_control_reader.py --config <actual-private-config> --config-sha256 <actual-sha> --loop`

Angle-bracket values in this explanatory command are not a generated config.
Verify reader and existing CRM supervisors Running, same config/code pins in
the consumer, actual fresh observation, both-process restart recovery and real
operation/Telegram acceptance. A configured module or running process alone
does not close Stage 4.

## Existing helpers and proposed local construction aid

- `observe_install_inputs.py`: read-only authenticated server hash/count snapshot.
- `build_preflight_bundle.py`: existing content-addressed read-only package;
  refuses missing/stale observation and wrong Stage 2 preimage.
- `build_release.py`: exact flat public source closure; creates no authority.
- `prepare_install_plan.py`: immutable private plan only **after** real
  claim/transaction/evidence exist; cannot solve pre-launch construction.
- `derive_candidate_parts.py` here: local dry-run derivation of non-executable
  blueprint/runtime/request-execution parts from supplied actual inputs. It
  creates no Gate, approval, claim, transaction, launch marker or private source
  copy. Its successful output is not an authorization or acceptance result.

Run the derive helper only when all actual files referenced by its input index
exist and match their independently recorded SHA-256. The helper contains no
example PASS evidence and no fabricated production-input fixtures.

Source URLs: [head](https://github.com/art20021986-wq/ua-art-autopilot/tree/e146c2ea8c28033050b49ccbebb33aa5276c8788),
[main](https://github.com/art20021986-wq/ua-art-autopilot/tree/0c85a6561d80c4d8789b3a482ae41cdaf9d0f667),
[installation contract](https://github.com/art20021986-wq/ua-art-autopilot/blob/e146c2ea8c28033050b49ccbebb33aa5276c8788/cloud/task088_price_sync/INSTALLER_CONTRACT.md).
