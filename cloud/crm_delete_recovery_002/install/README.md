# Offline-tested installation lifecycle candidate

`package_install.py` validates a hash-bound staged release and prints its exact
dependency order. It imports no production code, opens no provider connection,
does not pause/restart CRM, and has no `--apply` or `--quiescent` CLI switch.
The fixture transaction explicitly rejects the actual `/home/Carix` root.
`remote_worker.py`, `lifecycle_controller.py`, `lifecycle_worker.py`, and
`watchdog.py` implement the local installation lifecycle. The remote worker
defaults to read-only inspection; mutation is confined to admitted workflow
phases. The legacy one-shot lifecycle CLI refuses mutation. Production
registration and admission are separate from offline candidate validation.
The output status is **OFFLINE_VALIDATED**, never production READY. No production
installation, provider mutation, process signal, or live Telegram action was
performed while preparing and testing this candidate.

## Current concrete production gates

The approved UA-ART-CRM-DELETE-RECOVERY-002 v1.0 section 6.5 requires a separate
installation command. The parent agent verified the owner's separate instruction
at 07:01:57 UTC on 2026-09-21 and preserved its instruction record. That prerequisite
is satisfied; it must not be requested again. The existing structured Gate B
authorization must bind the reviewed request/package and instruction.

At the latest parent-agent repository observation, remote main was
`79c6aaccbfdc2decf7bf39d26738a2c38bde91f4`. Its
`state/AUTOPILOT_HALT.json` records an unrelated `EMERGENCY_HALT` from
`SEO-DAILY-PODBOR-CANONICAL-20260921`, run `35552076762`, at 01:53 UTC on
2026-09-21, with a critical failure and rollback reserved false. This task does
not authorize clearing that halt. A new direct-console installer must not be
used to bypass it. Its fresh actual status must be checked before installation;
the historical observation here is evidence of a remaining gate, not a new
invented control or a claim about its future state.

The inspected `remote_lifecycle.py` and `ua0002_console_runner.py` are specifically
bound to the earlier UA-0002 retirement. The latter overrides provider admission
and adds a retirement-specific watchdog. They must not be copied, monkeypatched,
or relabelled as this code installer. Their hashes are recorded only as inspected
references in `observed_bindings.json`.

The environment-driven controllers and authenticated transport in `../deploy/`
connect the existing critical workflow to this component's backup, execute and
rollback phases. The workflow runs on `ubuntu-latest`; the hash-bound remote
worker observes actual production files/processes. Candidate source files do not
register or admit themselves: the real request, trusted package manifest, Gate A
evidence and structured owner authorization must pass the existing workflow.
No production claim, receipt or authorization has been fabricated here.

The local admission now verifies the actual persisted transaction and its claim:
OPEN for execute, PREPARING only for the explicit backup operation, and the
already-consumed ROLLING_BACK state for rollback. OPEN additionally verifies the
original strict backup receipt and ledger expiry. Default admission never treats
PREPARING as authorization to install. Recovery uses the existing control-plane
recovery loader and grants no new installation capability.

An acyclic `installation_policy_sha256` binds the task, scope, package/source
digests, package path, provider inventory, HTTP checks, time budget, control-plane
sources and outer controller SHA. The exact request contains this digest. The
existing structured owner approval binds the complete request through
`request_subject_sha256`, using the existing zero-sentinel rule for the approval
SHA. No new keys are added to the exact approval schema. The request also binds
the approval's path and SHA.
Dynamic repository root, main commit, request/run/transaction identities and
approval hashes form a separate envelope; those are checked against actual
authority without creating policy/approval/commit hash cycles. The outer trusted
controller and each remote executable have distinct source bindings.

Rollback separates pinned executable sources from fresh authority. The source
commit must match both the claim and autostart ledger and be an ancestor of the
current main commit. Exactly five durable documents—claim, transaction, request,
ledger and backup receipt—must match byte for byte between fresh authority and
the pinned source worktree. A current HEAD check is never silently waived.

After that integration is reviewed, actual execution still requires: the
unrelated HALT to be handled by its authorized process; binding of the received
installation instruction; a current immutable main/claim; a private staged package
and plan with exact source hashes; and fresh provider, process, HTTP and runtime
evidence. Historical observations and offline tests cannot satisfy these gates.

## Implemented local lifecycle

New backup and execute operations check the actual repository HALT before
importing control-plane code, bind current remote main and control-plane/workflow
sources, and call
`verify_execution_mode(..., required_mode='AUTOMATIC',
allow_halt_for_recovery=False)`. It never clears a halt. Fresh authenticated
provider inventories must match the bound plan; enabled schedules must have a
quiet window covering installation, watchdog recovery and a buffer.

Before any pause, the remote host must observe the exact CRM process and its
singleton FLOCK in the same process namespace, including PID/start ticks and
device/inode ownership. Provider `Running` alone is insufficient. An observed
console without the CRM PID cannot establish always-on placement; unsupported
placement refuses before disabling CRM. Only the exact context-bound temporary
worker trigger is excluded from the complete provider inventory comparison.

Before pausing supervisor 266084 it verifies an independent durable watchdog
READY receipt. The watchdog binds owner PID/start ticks/session, package, plan
and source hashes; it uses pidfds for exact process identity. Its bounded recovery
dispatch reconciles only this installation's already-owned journal. It never
starts a new installation. The recovery budget is 900 seconds; the real-lock
shutdown wait consumes at most 45 seconds of that bound.

The lifecycle journals pause intent before provider mutation, installs under
actual locks, reloads the exact WSGI release and checks bound public HTTP results,
then resumes CRM and checks the runtime receipt. Uncertain resume is retried as
resume/read-back, without reinstalling or reverting application data. Startup
proof includes the actual PID/start ticks, current adapter/config digests and
registered recovery job; it explicitly does not certify a live Telegram action.
Interrupted terminal-result persistence is repaired idempotently. Unconfirmed
recovery reports BLOCKED and makes no claim that CRM resumed.

The workflow-facing worker supports separate bounded phases. Backup pauses CRM,
creates one verified composite backup, and resumes the baseline. Execute pauses
again and uses that exact original digest; it refuses source or logical database
drift instead of taking a replacement snapshot. The composite manifest links the
SQLite/source backup manifest and exact WSGI preimage/mode. Transaction-specific
journal namespaces prevent one attempt from consuming another attempt's backup.
Rollback restores code only and refuses any already-durable deletion intent.
Successful installation reports code-restore readiness from actual backup,
file/WSGI and deletion-intent checks under the held lease; it does not claim that
an actual rollback was performed. The exact three additive table DDL statements
are queried from `sqlite_master` and reported as a canonical schema projection,
without inventing a stable after-hash for the live SQLite file.

The distinct outer task is `UA-ART-CRM-DELETE-RECOVERY-002-INSTALL`, with acceptance
scope `INSTALLATION_AND_RUNTIME_HTTP_VERIFY`. The package task remains
`UA-ART-CRM-DELETE-RECOVERY-002-v1.0`. The parent task remains
`PENDING_LIVE_TELEGRAM_ACCEPTANCE`; startup/HTTP proof does not certify the full
live deletion/recovery acceptance scenario.

## Staged manifest

`manifest.json` is bound by a separately supplied SHA-256. Required fields:

- `format`: `1`; `task`: `UA-ART-CRM-DELETE-RECOVERY-002-v1.0`.
- `root`: `/home/Carix`.
- `supervisor`: `{ "id": 266084, "command": "python3.10 /home/Carix/start_safe.py" }`.
- `application_schema_sha256`: digest of the reviewed application schema.
- `source_guards`: map of relative Python paths to current SHA-256; includes
  `db.py`, `run_all.py`, `start_safe.py`, and `publication_fence.py`.
- `files`: records with exactly `destination`, `before_sha256` (null only for a
  new file), `payload`, `payload_sha256`, `role`. Destinations are relative to
  `/home/Carix`. Payloads are relative to the staging directory. Roles are
  `helper`, `writer`, `entrypoint`; `cars_ui.py` is the sole entrypoint and last.
- `deletion_schema`: `{ "payload": "relative/path/deletion_state.py", "sha256": "…" }`.
  The three additive CREATE TABLE statements are statically extracted from the
  hash-bound module; it is not imported.
- `runtime_config`: `{ "destination": "ua_crm_deletion_state/runtime.json",
  "payload": "relative/path/runtime.json", "payload_sha256": "…",
  "before_sha256": null }`. Its exact seven-field runtime keyset and application
  schema digest are checked. Runtime semantic route/counter verification belongs
  to the runtime release tests, not this package checksum validator.
- `route_patch`: the five file-record fields, with destination exactly
  `/var/www/www_uaart_com_ua_wsgi.py` and role `route`. Its payload is compiled and
  hash checked by the package validator. It is required by the complete lifecycle
  and installed through the separately journalled WSGI worker.

Read-only validation:

```sh
python package_install.py --package /absolute/staging/folder --manifest-sha256 EXACT_MANIFEST_SHA256
```

Optional `--check-source-root /absolute/source/root` verifies the original source
and absence pins without creating files. It must point to a complete source
mirror or the actual root; a directory that lacks required baselines is rejected.

## Implemented and tested installation mechanics

The code transaction and local worker are tested with real files, SQLite WAL,
and `flock`:

1. Hold the **existing** `.start_safe.singleton.lock`, then the **existing**
   `.ua_art_publish_transaction.lock`; compare open and linked inodes. Busy locks,
   missing locks, replacement inodes, and unknown active Python commands refuse.
   After asynchronous provider disabling the worker waits up to 45 seconds on
   these actual locks, without signalling processes or accepting a caller flag.
2. Verify source and staging SHA-256 pins before creating the private journal.
3. Copy every affected/guarded source with checksum equality and read-back.
   Use SQLite `backup()` against one read transaction, including committed WAL
   data; require integrity PASS and equality of the logical application data.
   Record the stored SQLite snapshot SHA-256 separately. SQLite snapshot bytes
   are not falsely claimed to equal the raw WAL-mode main file bytes.
4. Write a durable backup manifest and progress journal. Revalidate the backup
   before installing anything. Refuse changes made after backup.
5. Add only the three reviewed deletion tables in one transaction; require the
   application schema and every existing table's data to remain identical.
6. Atomically replace helpers/core first, writers next. Write the exact new
   runtime config under a 0700 directory with mode 0600. Install the bound WSGI
   entrypoint after its helper modules, then replace `cars_ui.py` last. Verify
   every replaced file and database integrity/data after completion.
7. Code-only rollback prechecks **all** current code images, preserves newer
   operator edits, journals rollback intent, restores WSGI before removing any
   imported helper, then restores the old CRM entrypoint before its dependencies.
   Interrupted rollback resumes from the same journal. It never restores an old
   database. Additive schema/config stay for audit. Once a durable deletion
   intent exists, legacy-code rollback is refused: it would remove the guards
   needed to preserve deletion, so forward recovery must be reviewed instead.

The lock lease is genuine local exclusion, **not proof of provider quiescence**.
Before production use the new lifecycle must obtain fresh authenticated
inventories for supervisor 266084, monitor 270984, every scheduled job, and other
writers; establish an adequate quiet window; and check the actual process
namespace together with the held locks. An empty `/proc` result or a caller's
boolean assertion cannot establish this. The last reported schedule inventory
had enabled jobs at 21:28 and 19:00 and a disabled job at 08:02; those historical
times must not be reused as a fresh observation.

No media, catalogue page, car row, price, photo, or whole database restoration is
part of installation. The precise WSGI route patch and reload are a separately
journalled step after the required installation command.

All staged directories must have mode 0700 and files mode 0600. A package root
containing the manifest/payloads and future plan/context may contain the five
executable modules under `install/`; nested descendants are supported by the
watchdog's path binding. A plan/context from another directory cannot silently
borrow a package or recovery executable outside its bound root.

Run tests from the repository root:

```sh
python -m unittest discover -s cloud/crm_delete_recovery_002/install -p 'test_*.py' -v
```
