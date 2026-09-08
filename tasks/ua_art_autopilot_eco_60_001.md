# UA-ART-AUTOPILOT-ECO-60-001 v1.0

OWNER_APPROVED: YES
OWNER_CONTINUE_COMMAND: YES
PRODUCTION_AUTHORIZED: NO
SITE_CHANGES_AUTHORIZED: NO
CRM_CHANGES_AUTHORIZED: NO
CARD_CHANGES_AUTHORIZED: NO
NEW_PAID_SERVICES_AUTHORIZED: NO
TIMEBOX_MINUTES: 60

## Objective
Reduce unnecessary AI/model calls in the current central control plane without weakening safety or production gates.

## ECO_SIMPLE policy
- MAX_MODEL_CALLS_PER_TASK: 2
- MAX_TOTAL_TOKENS_PER_TASK: 24000
- MAX_NETWORK_RETRIES_AFTER_FIRST_ATTEMPT: 2
- Queue/status/reporting paths: 0 model calls.
- Aggregate budget persists across retries, repair paths and workflow reruns.
- Duplicate completed task with unchanged input fingerprint: 0 new generations and 0 duplicate apply.
- Billing/quota/access blocker: fail closed; no blind paid retry loop.

## Current architecture binding
Implement against the current centralized TASK113+ control plane on current main, not the obsolete pre-TASK113 branch snapshot. Active workflow safety and exact-identity/runtime bindings remain mandatory.

## Required implementation
1. Trace actual task -> launch -> autostart -> orchestrator -> executor/model -> verification -> receipt path.
2. Record available baseline usage counters without making paid calls; unavailable values = NOT_MEASURED.
3. Add a persistent aggregate ECO budget ledger keyed by task identity plus input fingerprint.
4. Reserve call/token budget before provider invocation and reconcile actual provider usage when available.
5. Route nested repair/retry invocations through the same ledger; workflow rerun must not reset it.
6. Keep queue/status/test/report operations deterministic and model-free where possible.
7. Persist stage, fingerprint, evidence and idempotency marker; valid restart resumes instead of regenerating.
8. Run acceptance with stubs/mocks whenever possible; no paid model call merely to test budget enforcement.
9. Produce Gate B with changed files, tests, BEFORE/AFTER evidence, NOT_MEASURED values, blockers, rollback, and production_touched=false.

## Protected scope
Do not modify site, CRM, VIN data, specifications, prices, stages, media, catalogue, DNS, server configuration, UA-0017 or UA-0018. Do not enable ECO in active production/autopilot before separate owner Gate B command.

## Stop conditions
If acceptance cannot pass in the timebox, preserve branch work and report PARTIAL/BLOCKED. No automatic continuation beyond approved scope.
