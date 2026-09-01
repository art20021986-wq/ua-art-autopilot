# ACCEPTANCE TEST PLAN — TASK105

## Phase 0 evidence tests

1. Every `.github/workflows/*.yml|yaml` appears exactly once in the inventory.
2. Every inventory row has one of KEEP / MERGE / ARCHIVE / DELETE_CANDIDATE.
3. Every row maps to exactly one target permanent workflow.
4. Production/PythonAnywhere/Anthropic/watchdog/queue/retry flags are emitted.
5. TASK096 commit evidence and deterministic-preflight recommendations are present.
6. No production, CRM, PythonAnywhere, Cloudflare or DNS write occurs.

## Phase 1 unit tests

- Classification of representative FAST/STANDARD/CRITICAL tasks.
- Protected paths always escalate to CRITICAL.
- Resource locks allow unrelated tasks and serialize conflicting tasks.
- Retry accepts transient failures only.
- Second repeated logical failure enters ROOT_CAUSE_MODE.
- Receipt validator rejects missing live verification or rollback data.

## Failure injection

1. GitHub runner cancellation.
2. Network timeout.
3. HTTP 429.
4. PythonAnywhere 502/503.
5. Syntax error.
6. Unit-test regression.
7. Protected-file mutation.
8. Duplicate task dispatch.
9. Two unrelated production resources.
10. Rollback verification failure.

## Canary gates

- FAST synthetic: 20/20 PASS.
- STANDARD sandbox: 10/10 PASS.
- False FINISHED: 0.
- Unexpected protected changes: 0.
- Production regression: 0.
- Rollback drill: PASS.
