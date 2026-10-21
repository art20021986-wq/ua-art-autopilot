# CRM deletion Telegram candidate

This is an uninstalled candidate. No production files or database have been changed.

`build_bot_patch.py` binds the original `cars_ui.py` to SHA-256
`d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837`.
It replaces the two original destructive callbacks, preserves their registration
routes, and appends a registration wrapper. No private baseline source is stored
in this directory. `apply_to_candidate(bytes)` may compose with the list patch
after the caller validates the original baseline; it additionally binds the
exact original delete-handler block to its own SHA-256.

The adapter uses the actual `deletion_core.coordinator.Coordinator`. Staff is
checked before displaying the confirmation and before admission; the coordinator
rechecks its runtime authorization. Confirmation binds the exact row snapshot,
ID, code, canonical VIN and actor. The UI follows the existing VIN-last-four
policy. Old numeric confirmation buttons cannot delete a row.

Callbacks acknowledge and return immediately. PTB application tasks run blocking
DB/publication/HTTP operations in `asyncio.to_thread`. A recurring job starts one
second after application startup and resumes durable unfinished operations.
Active deletion and queue scanning share one async lock. Failures pause the
affected operation in this process; repeating the original confirmation retries
it, and a new process rechecks durable unfinished jobs. A queue scan error pauses
automatic scanning until process restart and is logged. There is no new process,
system service, startup migration, media deletion, or silent fallback to legacy
row-only deletion.

Completion messages require the coordinator's successful completion receipt and
durable COMPLETE read-back. Duplicate clicks reuse the same operation. A repeat
after COMPLETE explicitly reports a historical completion receipt; it does not
claim a fresh probe or rewrite newer catalog content. Restart-result messages
go only to the exact initiating Telegram actor stored in the durable job, after
checking that this actor is still registered CRM staff.

## Required integration gate

The final app must have a reviewed, source-bound `ua_delete_runtime.py` beside
`cars_ui.py` implementing `create_coordinator(db=db)`. That factory must supply
the actual publication fence, authorized staff check, approved application
schema hash, existing private backup folder, complete routes, precise counter
transform, independent remaining-membership/counter verification, bounded HTTP
observations, and existing `db.connect()`. Factory construction must have no
migration/publication effects. Installing the additive schema and every writer
guard is a separate release prerequisite.

The integrated release supplies the facade from
`ua_crm_deletion_core.runtime.create_coordinator`. When the factory or PTB job
queue is unavailable, CRM remains registered and deletion fails closed with an
explicit message. This candidate alone must not be reported as installed or as
full deletion recovery PASS.

After factory validation and actual repeating-job registration, the backend
writes a private atomic REGISTERED startup receipt. Successful queue scans write
RUNNING only with actual application/updater running flags. Receipts bind PID,
process start ticks, runtime-config SHA and this adapter's source SHA, and
explicitly set `live_telegram_action_verified` to false. Receipt failure during
registration removes the job and leaves the deletion backend inactive. Receipt
refresh failure is logged and cannot manufacture live readiness.

Tests execute the exact injected handlers with the real coordinator, real
SQLite and a temporary filesystem. Only Telegram transport and HTTP observations
are simulated. Run from the repository root:

    python -m unittest discover -s cloud/crm_delete_recovery_002/bot_patch -p 'test_*.py' -v
