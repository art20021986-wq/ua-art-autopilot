# TASK 079 — Gate B manual workflow (PREPARED, NOT EXECUTED)

MEMORY MARKERS (verbatim):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

**This document describes a plan only. Nothing in this document has been
executed. Gate B execution is CRITICAL and requires explicit, separate owner
approval using the exact token below. Mentioning the token here is not
approval.**

Exact required owner token for any future Gate B execution:

```
CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED
```

## Preconditions before Gate B may even be scheduled

1. `cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py`
   has been independently executed (not by this Cloud/Claude channel) with a
   recorded pass count, and the result has been written into canonical
   memory as a `RESULT` record, matching the TASK 015/021 acceptance pattern.
2. A fresh, verified BACKUP of the production database and the bounded live
   file set (card, diagnostic page, /video catalog, /site catalog for the
   affected VINs) exists and its checksum is recorded.
3. The owner has supplied the exact token above through the approved
   channel, tied specifically to this contract version
   (`CRM-CONTAINER-STAGE-SYNC-004 v1.0`).

## Planned Gate B steps (NOT executed by this task)

1. Run `live_patcher.py` against the real checkout with the real expected
   per-function source hashes (to be captured fresh at Gate B time, not
   reused from this document) for:
   - `konteyner.prinyat`
   - `cars_ui.apply_value`
   - `cars_ui.toggle_publish`
   Abort immediately on any anchor or function-hash mismatch, exactly as
   `live_patcher.py` is coded to do.
2. Replace each of those three functions' bodies with calls into the shared
   writer (`eta_release_candidate.apply_eta_change` / `.toggle_publish`),
   preserving all existing argument/return contracts visible to callers.
3. Apply the narrow stale-sentence sanitizer only to UA-0009's description,
   removing only the sentence matching the arrival+date pattern documented
   in `evidence/gate_a_findings.md`, leaving everything else byte-identical.
4. Deploy to a CANARY copy first; run the full sandbox suite again against
   the canary database copy; verify UA-0009/0010/0011/0012 target states.
5. Only after canary verification, and only with the owner token present,
   apply to production during a low-traffic window, with the pre-captured
   backup checksum available for immediate restore.
6. Immediately after production apply: read back the DB rows for the
   affected cars from a fresh connection, verify the bounded public file set
   (card, diagnostic, /video, /site) for each, and record the result as a
   new canonical memory `RESULT` record before declaring the rollout done.
7. If any step 4–6 fails, execute the compensating rollback exactly as
   `apply_eta_change`/`toggle_publish` implement it, verify exact restoration,
   and stop — do not retry automatically.

## Explicit non-actions in this delivery

- No step above has been run.
- No production file or database was opened, read, or written by this task.
- No process reload occurred.
- No CRM write occurred.
