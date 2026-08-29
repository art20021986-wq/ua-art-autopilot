# Gate B — manual production workflow (NOT RUN, requires owner-issued new token)

This workflow is documentation only. It has not been executed. It will not be
executed by any automated worker. A human controller performs it only after
the owner issues a **new, distinct** production go-ahead token specific to
this task (not the TASK-approval phrase already used to authorize sandbox
work).

## Preconditions before Gate B may start

1. Gate A has been executed for real and produced
   `GATE_A_RESULT: PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` in
   `evidence/gate_a_findings.md`.
2. Owner has issued a distinct new production token, e.g. of the form:
   `PRODUCTION-APPROVE CRM-CONTAINER-STAGE-SYNC-004 GATE-B <date>`.
3. TASK 076's Gate B lineage has been re-confirmed as the single ETA writer
   that this task extends; no second writer will be introduced.

## Steps (manual, sequential, human-triggered)

1. **Backup**: full copy of `crm.db` (+ WAL), all card directories, and the
   two catalog files, timestamped, stored outside the live path.
2. **Staged bounded apply**:
   - Patch active renderer(s) per `patcher/stage_sync_patch.py` transformations,
     re-anchored against the exact SHA-confirmed live text from Gate A.
   - Wire the extended transaction from
     `patcher/eta_transaction_controller.py` into the single active ETA write
     path (extend, do not duplicate).
   - Run `patcher/installer.py --mode PRODUCTION --production-token <token>
     --backup-path <path> --confirm-rollback-plan` (currently refuses to
     proceed by design — see code comments — until a human removes the
     placeholder refusal and reviews the real target files).
3. **Verification** (must all PASS before any success claim):
   - Read-back for UA-0012: `status=sea_loaded`, `days_to_kyiv=30`,
     `eta_manual=2026-09-28`.
   - UA-0009 unaffected in ETA fields; status confirmed `sea_loaded`.
   - Zero occurrences of standalone `sea_transit` callback in any active menu.
   - Exactly one `sea_loaded` button on screen; `sold_transit` unchanged.
   - `/video` and `/site` canary both PASS for UA-0012 and one control card.
   - Badge/category on public site match `На пароме` / `more`.
4. **Legacy migration** (only after step 3 fully PASSes and only with a
   second explicit owner confirmation): run
   `migrate_legacy_sea_transit(conn, allow=True)` as its own bounded
   transaction with the same backup/rollback discipline.
5. **Auto-rollback trigger**: any failure in step 3 or 4 restores from the
   step-1 backup automatically; no partial state is left live; one final
   failure message is produced; `published` reverts to preimage.
6. **Sign-off**: record the real Gate B run outcome, backup path, and
   verification transcript into `cloud/task_077_container_stage_sync/evidence/`
   as a new dated file. Update `cloud/latest_status.md` and
   `cloud/owner_reply.md` accordingly in a follow-up task round.

## Hard stop conditions (abort immediately, no success message)

- Missing or mismatched new production token.
- Gate A result is FAIL or missing.
- Any DB write, read-back, publisher, queue, or verify step fails.
- Any attempt to alter Georgia/Kyiv/sold/archive stage backward.
- Any second ETA writer detected/introduced.
