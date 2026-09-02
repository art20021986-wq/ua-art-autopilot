# TASK105 STANDARD Canary — Attempt 1 Root Cause

STATUS: ROOT_CAUSE_IDENTIFIED
TASK_ID: TASK105-STANDARD-PRODUCTION-CANARY
BLIND_RETRY: NO
PROTECTED_FILES_CHANGED: 0
CRM_WRITE: NO
VEHICLE_DATA_WRITE: NO
CLOUDFLARE_DNS_WRITE: NO

## What passed

- Owner authorization: PASS.
- Deterministic unit tests: 15/15 PASS.
- STANDARD sandbox classification matrix: 10/10 PASS.
- Three bounded production cases executed successfully.
- Immediate public verification: PASS for all three canary targets.
- Delayed public verification: PASS for all three canary targets.
- Homepage and catalog HTTP/live checks: PASS.
- CRM, homepage and catalog SHA-256 remained unchanged.

## First bad event

The remote installer created a valid backup manifest before the production cases. After the cases completed, it enriched the in-memory manifest with:

- `backup_root`;
- `protected_before`;
- `final_expected`;
- `cases`;
- `installed_at_utc`.

It wrote the enriched object to `task105_standard_canary_last_success.json`, but did not rewrite the backup directory's `manifest.json` with the same enriched object.

The postcheck correctly compared the durable backup manifest with the last-success manifest and stopped on `BACKUP_MANIFEST_READBACK`. The same invariant also prevented the original rollback function from proceeding.

## Root cause

`BACKUP_MANIFEST_ENRICHMENT_NOT_PERSISTED`.

This is a deterministic manifest-consistency defect, not an infrastructure timeout and not a reason for blind retry.

## Production state after the stop

Three dedicated canary files remained present because the rollback verifier refused to trust mismatched durable manifests. No existing site page, CRM record, vehicle data, Cloudflare setting or DNS setting was modified.

## Minimal correction

1. Keep the original core manifest immutable and verify its four core fields byte-for-byte.
2. Allow only a fixed enrichment allowlist.
3. Rewrite the full enriched manifest atomically before postcheck.
4. Bind all inherited restore/postcheck functions to the compatible validator.
5. Add a `cleanup` mode that restores attempt-1 state before the corrected canary begins.
6. After corrected live verification, execute a deliberate full rollback and verify public absence/fallback plus core-page health.
7. Emit `FINISHED` only after rollback and public rollback verification PASS.

## Regression protection

- Dedicated tests verify both core-only and enriched manifest contracts.
- Cleanup refuses CRM writes and protected-file drift.
- The same TASK105 and same STANDARD canary identity are retained.
- Final evidence is staged only from paths that actually exist; a missing optional receipt can no longer cause all evidence staging to be skipped.
