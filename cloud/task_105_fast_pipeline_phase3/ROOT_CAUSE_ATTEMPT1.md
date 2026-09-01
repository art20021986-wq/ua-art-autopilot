# TASK105 FAST Production Canary — Attempt 1 Root Cause

STATUS: ROOT_CAUSE_IDENTIFIED
PRODUCTION_STATE: ROLLED_BACK LOCALLY
PROTECTED_FILES_CHANGED: 0
CRM_WRITE: NO
AI_CALLS: 0

## First bad event

The dedicated target did not exist on disk before the canary. A GET to its public URL returned HTTP 200 with the exact homepage body because the current UA ART routing falls back to `/video/index.html` for an unknown path.

The first verifier incorrectly interpreted every HTTP 200 baseline as an existing target file. It therefore reported `PUBLIC_LOCAL_ABSENCE_MISMATCH`, even though the local preimage was correctly recorded as absent.

## Rollback result

The remote rollback transaction passed:

- target restored to absent state;
- CRM SHA unchanged;
- homepage SHA unchanged;
- catalog SHA unchanged;
- unexpected production changes: 0.

The public rollback verifier also expected HTTP 404 and therefore produced a second false negative. The public route continued to return the homepage fallback, which is the correct pre-canary public behavior for this host.

## Root cause

`PUBLIC_ABSENCE_MODEL_INCOMPLETE`: the validator supported only a literal HTTP 404 absence state and did not model the site's verified homepage fallback behavior.

## Minimal fix

Classify the public target as one of:

- `ABSENT_404`;
- `ABSENT_HOME_FALLBACK` when marker response bytes equal homepage response bytes;
- `EXISTING_FILE` when marker response is HTTP 200 and differs from the homepage.

Use the same classification for preimage validation and rollback verification.

## Regression protection

Deterministic regression assertions were added for `ABSENT_HOME_FALLBACK` while preserving the 10-test canary safety suite. The same TASK ID is retained; this is attempt 2 after root-cause correction, not a blind new task.
