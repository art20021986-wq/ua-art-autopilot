# Production-route integration and admission status

The installation adapter is prepared as source and verified offline: **86/86**
deployment tests pass, including actual producer-to-consumer receipt checks. Production
Gate B and runtime admission remain open; this is not an installation receipt.
No production mutation was made by this review or its tests.

The owner separately instructed “Установио.” on 2026-09-21 at 07:01:57 UTC for
PR 116. The parent task verified the original conversation and preserved the
exact external evidence in `../evidence/OWNER_INSTALL_INSTRUCTION_20260921.json`.
Section 6.5's separate installation command is therefore **received**. It must not
be requested again. Structured admission still requires the established exact
request, Gate A, manifest, current authority and transaction checks.

The parent task verified that the inspected `execution_contract.py`,
`control_plane.py`, `critical_adapter.py`, and `uaart_critical.yml` have the same
Git blob IDs at remote main `79c6aaccbfdc2decf7bf39d26738a2c38bde91f4`.
`review_evidence.json` records those bindings and the initial findings. The
unrelated SEO `AUTOPILOT_HALT` is preserved; this package supplies no exception
for it and does not clear it.

## Implemented integration

- `deploy/controller.py`, `backup_controller.py`, and `rollback_controller.py`
  accept the existing dispatcher’s environment-only protocol. The actual
  `validate_execution` accepts their complete declared Python closure. The actual
  isolated launcher requires no lifecycle CLI arguments and refuses an active
  halt before staging.
- `materialize_deploy.py` copies exact runtime and build recipe sources into
  `deploy/`, recording canonical-source and destination hashes in `source_map.json`.
  Detailed source-extraction tests remain offline evidence. Two QA files used
  only for hashes are inert `.py.txt` data; they are never imported or executed.
- `deploy/release_bundle.py` retrieves only explicit hash-bound original sources,
  builds candidate code in a private temporary directory with the actual recipe,
  and requires the expected inner package hash. Full production source is not
  committed. Execute and rollback reconstruct the same candidate from the
  immutable original code backup; they never download or restore the CRM database.
- `deploy/transport.py` uses a fixed source-bound always-on trigger, private
  staging, upload/read-back equality, bounded polling, and authenticated API
  pacing. It has no incident-console or schedule fallback. A terminal receipt is
  paired with its exact context hash; uncertainty preserves the owner/watchdog.
  Real remote-worker receipt bytes, including blocked outcomes, are tested through
  the transport parser.
- The remote phase runner obtains a fresh public-origin authority checkout,
  checks the exact task transaction, observes provider inventory, establishes an
  independent watchdog, and owns each bounded pause. Backup resumes CRM;
  execute uses that same backup and refuses source/data drift. Rollback changes
  only code under CAS and refuses removing deletion guards after an intent.
- Static lifecycle policy is bound through the request and critical manifest.
  The existing exact owner-approval schema binds the complete request through
  `request_subject_sha256`; no shared approval/control-plane policy was relaxed.
- Pinned rollback code is kept separate from fresh current authority. Tests
  create a real Git worktree, reproduce the existing workflow’s five durable
  overlays, and verify both equality and rejection of a changed transaction.
- Successful receipts finish only `UA-ART-CRM-DELETE-RECOVERY-002-INSTALL`, with
  scope `INSTALLATION_AND_RUNTIME_HTTP_VERIFY`. The parent remains
  `PENDING_LIVE_TELEGRAM_ACCEPTANCE`; no fixture claims a Telegram action.

The provider documents native `API_TOKEN` availability in new tasks. The parent
observed only its presence, never its value. Credentials are not uploaded,
written into the package, or embedded in task commands. Missing credentials
refuse before pause. Reference: [official API documentation](https://help.pythonanywhere.com/pages/API/).

## Remaining admission and platform checks

1. The final assembled package passed **342/342** tests, zero failures or skips,
   with equality of all 32 canonical runtime/recipe snapshots. The bound results
   are in `../evidence/offline_validation.json` and `../evidence/build_receipt.json`.
   Production admission and the remaining platform checks below are separate.
2. Resolve the unrelated halt through its existing authorized process. A new
   installer must not use an incident override to bypass that state.
3. Establish fresh provider capacity and exact inventory. The UI permits adding
   a task but does not prove remaining always-on quota. Creation failure before
   pause is safe and tested; capacity has not been asserted.
4. Verify process namespace and lock reachability from the actual proposed
   always-on worker. The authenticated UI showed CRM Running while a read-only
   console observed zero exact CRM processes at 07:09 UTC. That console result
   does not establish the placement of a future worker. The strict process/lock
   checks remain intact and may safely block installation.
5. Bind fresh source/schema/storage/health and public HTTP observations, then use
   the existing immutable request and launch intake with the received owner
   instruction. An additive SQLite migration needs explicitly scoped schema
   digests and actual schema verification; a SQL-text hash must never be labelled
   a raw `crm.db` after-image.
6. Perform real installation/runtime/HTTP read-back and subsequently the parent
   Telegram acceptance. Offline regression success is not evidence of either.

## Reviewable draft inputs

`build_installation_draft.py` reads a local release manifest and private source
mirror, then writes hashes, observed provider commands, exact public checks, and
prospective policy. It writes no request under `tasks/`, no authority under
`state/`, and no approval. Its output is **DRAFT_NOT_AUTHORIZED**, records the
owner command as received, and identifies the remaining admission checks.

```sh
python -I -B cloud/crm_delete_recovery_002/admission/materialize_deploy.py
python -I -B cloud/crm_delete_recovery_002/admission/build_installation_draft.py --sources /private/source-mirror --manifest /private/release/manifest.json --output cloud/crm_delete_recovery_002/admission/installation_input.draft.json
```

Provider observations and HTTP fixture hashes in the draft are review inputs;
they must be checked freshly before any admitted pause. The actual request must
use the existing approval schema and must not turn this draft into authority by
renaming it.
