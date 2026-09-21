# Offline-tested installation lifecycle candidate

`package_install.py` validates a hash-bound staged release and prints its exact
dependency order. It imports no production code, opens no provider connection,
does not pause/restart CRM, and has no `--apply` or `--quiescent` CLI switch.
The fixture transaction explicitly rejects the actual `/home/Carix` root.
`lifecycle_controller.py`, `lifecycle_worker.py`, and `watchdog.py` implement the
local installation lifecycle. The lifecycle CLI also defaults to read-only
inspection; explicit execution requires existing authority and a separate owner
command. This component is not yet registered through the production workflow.
The output status is **OFFLINE_VALIDATED**, never production READY. No production
installation, provider mutation, process signal, or live Telegram action was
performed while preparing and testing this candidate.

## Current concrete production gates

The approved UA-ART-CRM-DELETE-RECOVERY-002 v1.0 section 6.5 requires a separate
installation command. Approval of the specification does not replace that
command.

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

The remaining preparation boundary is the existing critical workflow's
installation adapter and registration. Its `execution_contract.run_controller`
passes `UAART_*` environment fields without CLI arguments and runs on
`ubuntu-latest`; this candidate expects a bound `--plan` and local production
files/locks. A dedicated transport/operation adapter must bind the remote
component and implement the workflow's backup, execute and rollback operations
and receipt contract. Registering this task also requires the real request,
trusted package manifest, Gate A evidence and structured owner approval. None
has been fabricated here.

The admission review also requires persisted OPEN transaction-state verification,
approval binding of provider/HTTP/authority plan contents, and a source-binding
contract between the outer trusted controller and this remote lifecycle. The
current equality check against the lifecycle's own SHA cannot identify a distinct
outer adapter. These are preparation blockers, not values to fill with guessed
claims. The candidate must not be launched as a direct-console workaround.

After that integration is reviewed, actual execution still requires: the
unrelated HALT to be handled by its authorized process; the separate section 6.5
installation command; a current immutable main/claim; a private staged package
and plan with exact source hashes; and fresh provider, process, HTTP and runtime
evidence. Historical observations and offline tests cannot satisfy these gates.

## Implemented local lifecycle

The candidate checks the actual repository HALT before importing control-plane
code, binds the current remote main and control-plane/workflow sources, and calls
`verify_execution_mode(..., required_mode='AUTOMATIC',
allow_halt_for_recovery=False)`. It never clears a halt. Fresh authenticated
provider inventories must match the bound plan; enabled schedules must have a
quiet window covering installation, watchdog recovery and a buffer.

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
containing the manifest/payloads and future plan/context may contain the four
executable modules under `install/`; nested descendants are supported by the
watchdog's path binding. A plan/context from another directory cannot silently
borrow a package or recovery executable outside its bound root.

Run tests from the repository root:

```sh
python -m unittest discover -s cloud/crm_delete_recovery_002/install -p 'test_*.py' -v
```
