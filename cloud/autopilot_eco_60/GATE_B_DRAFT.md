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
- Billing/quota/access/unknown-paid-outcome blocker prevents further model reservation.
- Stage persistence supports resume semantics.
- Deterministic local acceptance test uses no provider/model call.

## Still required before Gate B PASS
- Wire every actual provider invocation in FAST/STANDARD/CRITICAL execution paths through this ledger.
- Prove no bypass path exists for nested repair/retry provider calls.
- Run repository CI/contract tests on the rebased ECO branch.
- Capture available baseline provider usage; otherwise report NOT_MEASURED.
- Verify current main has not moved and rebase/update before final acceptance.

## Safety
This branch does not authorize Production. No site, CRM, card, VIN, media, catalogue, DNS or server mutation is part of this implementation.

## Current Gate B verdict
PARTIAL — do not enable on active autopilot.
