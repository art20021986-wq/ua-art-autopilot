# Rollback Plan (Task 092)

## Principle

No production write occurs in this task round, so there is nothing to roll back yet. This document is the rollback procedure that will govern any future canary→production step, which requires a separate owner command per task instructions.

## Rollback triggers (auto-rollback conditions per task spec)

- Counter mismatch (total != sum of stage buckets, or total != published unique count)
- Missing card (any of the 13 expected cars absent from a surface)
- Missing cover image or zero-size cover
- ETA mismatch between catalog and card
- build_id mismatch between homepage/catalog/cards
- Any JS error during smoke test
- Any 404/500 during smoke test
- Failed visual smoke test on any required viewport

## Rollback procedure (to be executed only after an approved production step exists)

1. Immediately stop serving the new build (feature flag / symlink swap back to previous known-good build_id).
2. Restore the previous production HTML/CSS/JS and canonical data snapshot from the backup captured in `PRE_RECOVERY_MANIFEST_TEMPLATE.md` step 2.
3. Purge only the specific changed asset paths from cache (targeted purge), never a full wildcard purge, and only after separate owner approval.
4. Confirm rollback via the same smoke/validator suite used for the failed build.
5. Record the rollback event, the trigger reason, and before/after build_id in the task report.

## Constraint carried over from the task

No rollback may ever discard UA-0011, UA-0012, UA-0013, any photo, any VIN, any description, or any newly added content, even if that means the rollback cannot be a simple full revert — in that case, a partial/manual reconciliation must be proposed to the owner instead of an automatic full revert.
