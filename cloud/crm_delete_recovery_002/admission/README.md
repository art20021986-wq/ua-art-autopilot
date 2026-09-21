# Independent production-route compatibility review

Status: **integration incomplete; production Gate B readiness is not established**.
This directory contains review evidence, not a request, an authorization, an
installer, or an alternative production route. No provider operation was made.
The user's approval of specification v1.0 does not supply the separate
installation command required by section 6.5.

The review inspected the automation sources and the uncommitted recovery package.
The parent task verified, through the GitHub connector, that the inspected
`execution_contract.py`, `control_plane.py`, `critical_adapter.py`, and
`uaart_critical.yml` have the same Git blob IDs at remote main
`79c6aaccbfdc2decf7bf39d26738a2c38bde91f4`, containing an unrelated active
`state/AUTOPILOT_HALT.json`. Their observed hashes and Git blob IDs are in
`review_evidence.json`; comparison against the eventual installation revision is
required before admission. The unrelated halt must remain intact and must be
resolved through its own authorized process.

## Concrete gaps

| Finding | Evidence and implication | Required integration |
|---|---|---|
| Launcher mismatch | `execution_contract.run_controller`, `run_backup`, and `run_rollback` invoke an isolated Python script with **no application arguments**. Operation identity is passed in `UAART_*` environment variables. `lifecycle_controller._bootstrap_cli_sources` requires `--plan` before `main` runs. A harmless no-argument invocation exits 1 with `Missing hash-bound lifecycle argument: --plan`. | Add a task-scoped outer controller that consumes and validates the existing immutable environment/request envelope. Do not point the request's controller path directly at the lifecycle CLI. |
| Different execution hosts | `uaart_critical.yml` runs the controller on `ubuntu-latest`. `InstallWorker` uses `/home/Carix`, `/var/www`, local `/proc`, and local production lock files. Provider API methods only inventory/pause/resume/reload; they do not transfer or execute the worker. | Implement and test the transport/staging/read-back boundary through the existing authorized controller route. A missing production checkout or a runner-local `/proc` cannot be treated as production evidence. |
| Controller identity mismatch | `RepositoryAdmission.check` requires the compiled claim's `trusted_package.controller_sha256` to equal the remote lifecycle source hash. A correctly declared outer controller necessarily has a different hash. | Bind the outer controller as controller and lifecycle/worker/watchdog as exact declared dependencies. Verify both identities transitively, without weakening the trusted package check. |
| Lifecycle policy is not authority-bound | The supplied plan hash protects file integrity, but the caller chooses that hash. The installation approval is checked only against `package_manifest_sha256`. Provider allowlists, HTTP checks, and authority fields are outside that manifest. `mark_compiled` stores Python-file hashes, not an arbitrary plan policy. | Bind immutable policy through the exact request/approved package, and validate runtime identity from the authoritative workflow. Avoid a hash cycle: the current plan already embeds request and approval hashes, so putting its whole hash back into those documents is not a valid design. Split static policy from the run-specific envelope. |
| Eligibility is not an OPEN transaction | `_production_transaction_context` validates claim eligibility, storage/health/Gate B, request identity, transaction-ID format, and ledger expiry. It returns a transaction path without loading the persisted transaction or requiring OPEN. The workflow separately performs this check with `transaction_watchdog.discover`. | Before any new installation mutation, bind and verify the exact persisted OPEN transaction, backup receipt, request/run/transaction identity, and current authoritative revision. PREPARING, absent, expired, closed, or another task's transaction must fail. |
| Backup and rollback contracts are absent | The execution contract requires distinct backup/rollback entrypoints and strict receipts. The lifecycle currently calls `backup_and_apply` during its execute phase and emits a lifecycle result, not these contract receipts. Workflow OPEN happens only after the separate backup receipt passes. | Supply independently callable backup and rollback controllers. Bind every operation to one verified remote backup manifest. Reconcile interruption between workflow jobs. Never fabricate a backup PASS from an unexecuted plan or restore an old CRM database. |
| Final receipt contract differs | A lifecycle result containing `COMPLETE` and `live_telegram_action_verified: false` is not the task orchestrator's full, identity-bound production receipt. The workflow revalidates and persists the latter. | Translate only proven outcomes into the existing exact receipt schemas. Preserve `live_telegram_action_verified: false` until actual Telegram acceptance. Installation verification must not claim completion of that acceptance. |
| Whole-source package fails AST admission | The existing execution contract rejects direct `exec`/`eval` calls in all declared test/dependency modules and requires a complete Python inventory under the controller directory. Six fixture test modules use `exec` to exercise extracted current production code. Those useful offline tests are not directly admissible as the whole production package. | Use an explicitly reviewed deployment package closure and compatible admission tests; keep detailed offline regression evidence separately. Do not weaken the shared AST policy or hide undeclared executable dependencies. |
| Required authority does not yet exist | No separate owner installation command has been supplied. No task-specific production request, manifest, approval binding, intake reservation, claim, OPEN transaction, or proven production-route receipt has been prepared by this review. | Complete the code integration and its isolated review first. Then obtain the separate exact-package installation command and use normal admission after the unrelated halt is legitimately resolved. Do not create an incident-console exception. |

## Source-only integration work remaining

The narrow implementation scope is a new task package, with normal
`controller.py`, `backup_controller.py`, `rollback_controller.py`, a bounded
transport module, and admission-compatible tests. Changes to the shared
workflow/control-plane policy are not justified by the findings above.

1. Implement the three environment-driven entrypoints using the existing
   `execution_contract.production_operation_environment` contract. Validate
   request bytes, operation, class, receipt target, run/transaction IDs, manifest,
   backup identity, and every executable source before any network mutation.
2. Define an acyclic static policy binding for release payloads, lifecycle
   sources, provider command inventory, public acceptance URLs, and source/schema
   pins. Derive run-specific fields from the admitted workflow and exact remote
   OPEN state. Recheck the authoritative halt before installation.
3. Separate verified backup preparation from applying that **same** backup-bound
   release. The lifecycle cannot silently produce a new backup unrelated to the
   receipt that opened the outer transaction. Preserve durable pause/recovery
   ownership across retries and process/runner loss.
4. Stage only hash-bound code and data in a private task directory, prove remote
   read-back, then invoke the remote lifecycle with a bounded watchdog. Carry
   production host observations back as data-only evidence. Existing UA-0002
   console overrides are not reusable authority.
5. Emit the exact backup, final, and rollback receipts consumed by the existing
   workflow. Keep rollback code-only and CAS guarded; once a deletion intent
   exists, an older unguarded runtime must not be restored. An unproven rollback
   must remain failed rather than claiming `crm_unchanged` or `live_verify` PASS.
6. Test the actual `validate_execution` and isolated launcher with the complete
   deployment package, then an isolated three-operation workflow simulation.
   Include missing/changed plan policy, wrong controller/dependency hash, active
   HALT, PREPARING/closed/foreign transaction, remote source drift, lost runner,
   pause/resume uncertainty, and wrong/stale receipt rejection.
7. Independently review the assembled route and record the authoritative source
   revision. Only that evidence can establish production-package readiness.

The current component regression results remain useful. They do not prove that
the existing production dispatcher can admit, transport, execute, recover, and
accept this package end to end.
