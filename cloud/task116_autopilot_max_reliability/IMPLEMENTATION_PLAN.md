# TASK116 implementation plan

STATUS: PACKAGE_SCAFFOLD
PRODUCTION: FORBIDDEN
BRANCH: task116-autopilot-max-reliability
BASELINE: 59/100
TARGET: 93/100

## Safety boundary

This branch may change repository control-plane code, tests and sandbox evidence only. It must not contain an AUTO launch marker, production approval, production credential, remote write command or mutation of website/CRM/card/media data.

## Ordered implementation

### Phase 1 — baseline and contracts (0–10%)

- Preserve the approved task and evidence baseline.
- Define schemas for canonical registry, reconciliation result, reliability metrics and recovery identity.
- Map every current active workflow and runtime hash.
- Define protected path and capability policy.
- Add tests that prove this phase cannot target production.

Exit: package compiles; repository-only scope and no-launch invariant pass.

### Phase 2 — canonical registry and reconciliation (10–30%)

- Implement registry records keyed by task id and immutable request hash.
- Reconcile requests, branches, PRs, issues, claims, runs, transactions and receipts.
- Detect out-of-queue work and conflicting states.
- Add lease expiry, heartbeat and idempotent stale-claim recovery.
- Replace fixed pagination with complete bounded pagination.

Exit: TASK108/TASK112-like fixtures are detected; duplicates/lost tasks = 0.

### Phase 3 — immutable preflight and stable execution (30–50%)

- Build one immutable preflight snapshot.
- Validate exact approval/scope/runtime/storage/queue/remote hashes.
- Separate transient retry from permanent validation failure.
- Remove manual rebind/relaunch dependencies.
- Add integration fixtures for stale approval, stale storage, pagination and HALT recovery.

Exit: 10/10 sandbox launches complete on first attempt.

### Phase 4 — recovery and rollback (50–70%)

- Add emergency recovery identity independent of launch nonce.
- Implement atomic rollback under ledger damage, runner restart and API outage.
- Verify preimage/postimage before restore.
- Add independent encrypted backup contract and restore readback.
- Run five forced failure scenarios.

Exit: 5/5 automatic recovery PASS, <=15 minutes, zero manual commits.

### Phase 5 — autonomous package authoring (70–82%)

- Normalize an owner request into a typed contract.
- Generate plan, code package, tests, manifest and draft PR in sandbox.
- Enforce deterministic validation and capability restrictions.
- Keep AI outside production credentials.
- Require independent Gate validation before production eligibility.

Exit: owner request to Gate A package completes without manual file preparation.

### Phase 6 — monitoring and product guards (82–90%)

- Generate canonical live status from state and API evidence.
- Check runtime/queue/transactions every five minutes.
- Check all current/future cards every 15 minutes.
- Full crawl hourly.
- Enforce VIN no-ad/no-leak and specification persistence.
- Verify CRM/catalog/card critical-field consistency.
- Send owner progress at each verified 5% and immediate P0 alerts.

Exit: status freshness <=5 minutes; P0 alert <=5 minutes; 16/16 guards PASS.

### Phase 7 — reliability acceptance (90–100% of task work)

- Execute 20 consecutive sandbox or production-equivalent tasks.
- Require >=95% first-attempt success.
- Run 72-hour uninterrupted soak including restart/recovery.
- Produce Gate A evidence and Gate B report.
- Do not merge or deploy without separate owner production authorization.

Exit: independent score >=90/100, target 93/100.

## Required artifacts

- schemas/canonical registry
- reconciliation module and tests
- immutable preflight snapshot module and tests
- retry classifier and tests
- emergency recovery identity
- rollback fault-injection suite
- off-host backup contract
- request normalizer and deterministic validator
- generated status/dashboard data
- all-card semantic monitor
- progress/P0 notification contract
- 20-run evidence
- 72-hour soak evidence
- Gate A report
- Gate B report
- final receipt

## Non-negotiable product invariants

- No VIN advertising or third-party VIN leakage.
- Additional specification survives every publication.
- No unexpected CRM, price, stage, card, diagnostic or media mutation.
- One value maps to one intended CRM field.
- Ukrainian is the primary language.
- UA-0009 receives an explicit separate check.
- No completion claim without live evidence and a validated receipt.
