# UA-ART-AUTOPILOT-ECO-60-001 — Gate B draft

Status: IMPLEMENTATION_IN_BRANCH / NOT_ENABLED
Production touched: false
Site/CRM/cards touched: false

## Implemented in branch
- Persistent aggregate task+input-fingerprint ECO ledger.
- Two model-call ceiling and 24,000-token reservation ceiling.
- Budget persists on disk across process/workflow restart when state is preserved.
- Completed duplicate blocks a new generation.
- Changed input fingerprint gets a distinct ledger; stale evidence is not reused.
- Billing/quota/access blockers prevent further model reservation.
- Unreconciled paid-call reservation fails closed on the next call rather than blindly retrying.
- Stage persistence supports resume semantics.
- Deterministic acceptance test source uses no provider/model call.

## Current architecture evidence
TASK113 merged the centralized global control plane and reduced active workflows to the central set. ECO implementation is based on the current main snapshot, not the obsolete original ECO branch base.

## Measured baseline
Provider token/call baseline: NOT_MEASURED (no provider usage evidence collected in this branch; no paid call was made to create a baseline).
Claimed savings percentage: NOT_CLAIMED.

## Validation status
The acceptance test source is committed but has NOT yet been executed by CI or a runner in this task. Therefore no PASS claim is made for runtime tests.

## Still required before Gate B PASS
- Wire every actual provider invocation in FAST/STANDARD/CRITICAL execution paths through this ledger.
- Prove no bypass path exists for nested repair/retry provider calls.
- Execute repository CI/contract tests on the ECO branch and record evidence.
- Verify current main has not moved and update branch before final acceptance.

## Safety
This branch does not authorize Production. No site, CRM, card, VIN, media, catalogue, DNS or server mutation is part of this implementation.

## Current Gate B verdict
PARTIAL — do not enable on active autopilot.
