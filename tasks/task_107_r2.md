# TASK107-R2 — UA-ART-AUTOPILOT-EXECUTION-RECOVERY-001

STATUS: OWNER_APPROVED
PRIORITY: P0
CLASS: CRITICAL / CONTROL_PLANE
EXECUTION_MODE: MANUAL_ONLY_UNTIL_ACCEPTANCE
BRANCH: task107-r2-control-plane-recovery

## Owner approval
УТВЕРЖДАЮ TASK107-R2 / UA-ART-AUTOPILOT-EXECUTION-RECOVERY-001. Выполнить как CRITICAL control-plane задачу в отдельной ветке. Ручной режим сохранять до 3/3 end-to-end canary PASS. Сайт, CRM, DNS, VIN, цены, карточки и медиа не изменять. Автоматический режим включать только после TASK107 receipt и отдельного подтверждения владельца.

## Immutable safety scope
- main remains MANUAL MODE during implementation and acceptance.
- No production website write.
- No CRM write.
- No DNS/Cloudflare write.
- No VIN, prices, vehicle/card data or media mutation.
- No automatic-mode re-enable in this task.
- All control-plane work stays on this branch until acceptance evidence is complete.

## Required implementation
1. Exact durable task intake; no max(task_NNN) routing.
2. Atomic task state/claim keyed by task_id + task_sha256 + run_id.
3. Separate AI planning from trusted package compilation/execution.
4. Route executable requests through the existing Central Orchestrator and FAST/STANDARD/CRITICAL pipelines.
5. Classify control-plane changes as CRITICAL from actual changed paths.
6. Resource-scoped queueing; no global serialization for independent non-production work.
7. Read-only storage preflight with 70/80/90 thresholds and required-space calculation.
8. Mandatory pre/post health verification for production-capable routes.
9. Heartbeat/stall state and bounded retry/root-cause behavior.
10. Exact autostart-guard identity matching; no generic recent-run PASS.
11. AI_RESPONSE_STATUS and TASK_EXECUTION_STATUS must be separate.
12. TASK FINISHED requires a validated receipt, never a report/marker alone.

## Acceptance gate
Manual mode remains active until all are PASS:
- exact intake
- atomic claim
- routing
- package compiler
- FAST canary
- STANDARD canary
- CRITICAL control-plane canary
- storage guard
- pre/post health guard
- stall detector
- duplicate protection
- rollback
- 3/3 consecutive end-to-end canaries
- TASK107-R2 receipt validation

Automatic mode requires a separate explicit owner confirmation after the above evidence exists.
