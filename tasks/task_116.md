# TASK116 — UA-ART-AUTOPILOT-MAX-RELIABILITY-001

STATUS: OWNER_APPROVED_FOR_PACKAGE_PREPARATION
PRIORITY: P0
CLASS: CRITICAL / CONTROL_PLANE
BRANCH: task116-autopilot-max-reliability
BASELINE_SCORE: 59
MIN_ACCEPTANCE_SCORE: 90
TARGET_SCORE: 93
PRODUCTION_ALLOWED: false
LAUNCH_MARKER_ALLOWED: false

## Owner authorization

УТВЕРЖДАЮ UA-ART-AUTOPILOT-MAX-RELIABILITY-001 v1.0. Подготовить execution package в отдельной ветке. Production не менять до отдельного Gate B отчёта и моей команды.

Дополнительное подтверждение владельца: УТВЕРЖДАЮ в работу.

## Immutable safety scope

- Work only on branch `task116-autopilot-max-reliability`.
- No production website, CRM, bot, DNS, Cloudflare, database or PythonAnywhere mutation.
- No changes to VIN, prices, stages, cards, specifications, diagnostics, media or container data.
- Do not create `tasks/launch/AUTO-*.json` in this phase.
- This approval authorizes package preparation and sandbox validation only.
- Production requires a complete Gate B report and a new explicit owner command.
- Any ambiguity, scope drift or unexpected protected change is fail-closed.

## Objective

Raise the evidence-backed autopilot score from 59/100 to at least 90/100, target 93/100, by converting the guarded executor into a reliable owner-request-to-verified-result system without weakening existing production safeguards.

## Required workstreams

### A. Trust root and repository protection

1. Protect `main`; PR-only changes and required checks.
2. Separate immutable production approval from the task branch.
3. Limit production secrets to exact gated jobs; remove broad secrets inheritance.
4. Bind remote deployed generators to the runtime manifest.
5. Require scope, commit SHA, task id, expiry and one-time nonce in approvals.

### B. Autonomous request preparation

1. Normalize one owner instruction into a typed request.
2. Generate plan, package, branch and draft PR automatically in sandbox.
3. Keep AI planner/code builder outside production credentials.
4. Validate AI output deterministically.
5. Represent real typed actions in manifests; no hidden semantic `noop`.

### C. Queue and reconciliation

1. One canonical registry and state machine.
2. Atomic idempotency key, claim lease and heartbeat.
3. Full pagination; no fixed recent-run limit.
4. Fresh live storage measurement.
5. Automatic reconciliation of request, branch, PR, issue, claim, run, transaction and receipt every five minutes.
6. Detect TASK108/TASK112-like work outside the queue.
7. No manual launch, rebind, clear-halt or relaunch after approved package creation.

### D. Execution reliability

1. Preserve the existing central tests and run all relevant suites.
2. Add end-to-end, race, stale claim, pagination, disk-full, timeout, duplicate, partial-write and delayed-verify tests.
3. Retry only transient errors.
4. Use one immutable preflight snapshot.
5. Reach first-attempt success >=95% over 20 consecutive tasks.

### E. Backup, rollback and self-heal

1. Exact target inventory and preimage hashes.
2. Independent encrypted off-host backup for CRITICAL changes.
3. Atomic writes and compare-before-write.
4. Emergency recovery identity independent of launch nonce.
5. Pass 5/5 forced fault drills, including restart during OPEN and unavailable GitHub API.
6. Restore exact preimage within 15 minutes with zero manual repair commits.

### F. Monitoring and owner reporting

1. Runtime/queue/transaction checks every five minutes.
2. All-card business checks every 15 minutes.
3. Full crawl hourly and maintenance daily.
4. Canonical generated status freshness <=5 minutes.
5. Alert owner within five minutes on HALT, failed rollback, stale queue, production failure, protected drift, storage threshold or VIN/specification violation.
6. Progress reports at each verified 5% milestone.
7. Finish every successful project with an explicit completion message and emojis.

### G. Permanent UA ART product guards

1. VIN is vehicle data only. No ads, provider branding, affiliate/referral, external VIN CTA, iframe, widget, redirect or third-party VIN leakage.
2. Additional specification remains present on all current and future cards and cannot be replaced by provider content.
3. Unexpected CRM/card/media/price/stage/VIN/specification mutation triggers rollback.
4. One value maps to one intended CRM field; duplicates are forbidden.
5. Preserve all 16 current cards and future cards, UA-0009 separate check.
6. Ukrainian remains the primary site language.
7. Do not claim completion until live site, CRM/integrations, rollback and receipts are proven.

## Mandatory acceptance

- Protected main and required checks.
- External/hash-bound owner approval.
- One canonical queue/registry with zero lost tasks.
- 20 consecutive tasks with >=95% first-attempt success.
- Five forced rollback drills: 5/5 PASS.
- Recovery <=15 minutes, manual recovery commits = 0.
- Status freshness and P0 alert <=5 minutes.
- All current/future cards pass VIN no-ad and specification guards.
- Unexpected protected changes = 0.
- 72-hour uninterrupted autonomous soak = PASS.
- Final machine-readable receipt and independent audit score >=90/100.

## Delivery phases

1. Baseline and package scaffold.
2. Sandbox implementation and unit/integration tests.
3. Fault-injection and recovery drills.
4. Gate A evidence.
5. 72-hour sandbox soak.
6. Gate B report for owner.
7. Production remains blocked until a separate explicit owner command.

## Current phase

PHASE_1_BASELINE_AND_PACKAGE_SCAFFOLD
