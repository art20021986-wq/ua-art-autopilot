# TARGET_ARCHITECTURE.md — TASK 105 Phase 0

## Goal
Propose a target 6–8 workflow architecture built around a central UA ART Task Orchestrator that classifies work into FAST / STANDARD / CRITICAL lanes, reduces redundant GitHub Actions runs, AI calls, retries, and global queue blocking, while preserving rollback and production safety. This is a **proposal only** — nothing described here is implemented or activated in Phase 0.

## Target workflow set (6–8 workflows)
1. **`orchestrator-classify.yml`** — triggered on any `tasks/task_NNN.md` push. Runs a deterministic (non-AI) classifier that reads task metadata/keywords and assigns lane: FAST (docs/reports/no production/no AI needed), STANDARD (worker + tests, no production write), CRITICAL (touches production/CRM/DNS/Cloudflare or requests owner approval). Writes `TASK_STATE=CLASSIFYING` then hands off.
2. **`worker-fast.yml`** — for FAST lane only. NO_AI or minimal single-call AI routing, short timeout, no queue lock (does not touch `production_queue.py`), lightweight concurrency group scoped per-task (not global) so multiple FAST tasks can run in parallel.
3. **`worker-standard.yml`** — parameterized shared pipeline for STANDARD lane (replaces the many task-specific ad-hoc workflows identified as DELETE_CANDIDATE/MERGE in WORKFLOW_INVENTORY.md). Runs Claude/GPT worker with a resource-scoped lock (see below), runs offline tests, writes SELF_VERIFIED state.
4. **`controller-verify.yml`** — single shared verification workflow (Codex/controller equivalent) that independently re-checks deliverables for both STANDARD and CRITICAL lanes and writes CONTROLLER_VERIFIED. Replaces ad-hoc, per-task verification logic.
5. **`critical-gate.yml`** — CRITICAL lane only. Enforces AWAITING_OWNER_APPROVAL → requires an explicit OWNER_DIRECTIVE record before any downstream production step can run. This is the only workflow permitted to move a task toward APPROVED_FOR_PRODUCTION.
6. **`production-apply.yml`** — the only workflow with production-write / PythonAnywhere-production-write / Cloudflare-write / DNS-write capability. Runs only after `APPROVED_FOR_PRODUCTION`, requires Gate B evidence (per REC-0004), and always creates a rollback artifact before applying.
7. **`queue-and-locks.yml`** (or a reusable composite action) — replaces global `production_queue.py` serialization with **resource-aware locks**: separate lock keys per affected resource (e.g. `lock:crm`, `lock:pythonanywhere`, `lock:cloudflare-dns`, `lock:site-content`) so unrelated FAST/STANDARD tasks are never blocked by an unrelated CRITICAL production apply.
8. **`root-cause-mode.yml`** (optional 8th, could be folded into worker-standard as a mode flag) — triggered after N consecutive logical failures on the same task; switches from blind retry to structured root-cause diagnosis output (see MIGRATION_PLAN.md), preventing TASK096-style v3→v8 repair loops.

If 6 is preferred over 8, items 7 and 8 can be implemented as reusable composite actions/scripts invoked by the other workflows rather than standalone workflow files, keeping the top-level count at 6.

## AI routing rules (as required)
| Lane | Routing | Budget |
|---|---|---|
| FAST | NO_AI (deterministic script) or single GPT_PRIMARY call only if text generation is unavoidable | ≤1 AI call, ≤4k tokens |
| STANDARD | GPT_PRIMARY drafts, CLAUDE_REVIEW checks correctness/safety only when the task is code/logic-heavy | ≤2 AI calls total, ≤20k tokens combined |
| CRITICAL | CLAUDE_PRIMARY performs the work, DUAL_REVIEW (a second independent AI or controller pass) required before AWAITING_OWNER_APPROVAL | ≤3 AI calls, explicit token ceiling per task type, hard stop + escalate to owner if exceeded |

## Resource-aware locking (replacing global serialization)
Instead of one global queue lock in `automation/production_queue.py`, define named resource locks:
- `lock:site-content-cards`
- `lock:crm`
- `lock:pythonanywhere-production`
- `lock:cloudflare-dns`
- `lock:github-workflows` (for changes to workflows themselves)

A task only acquires the locks for resources it actually declares it will touch (declared during CLASSIFYING). Two tasks touching disjoint resources run concurrently; two tasks touching the same resource still serialize, preserving current safety guarantees without blocking unrelated FAST work.

## Deterministic retry policy
- Max 2 automatic retries for transient failures (network/timeout) with exponential backoff.
- On the 3rd consecutive failure of the *same logical step*, the task is switched into **ROOT_CAUSE_MODE**: no further blind retries; instead the workflow collects structured diagnostic evidence (exact error, environment snapshot, last successful state) and sets `TASK_STATE=BLOCKED` with `OWNER_ACTION_REQUIRED` only if the root cause requires an owner decision; otherwise it stays BLOCKED for controller/Codex follow-up.
- This directly targets the TASK096 v3–v8 anti-pattern by capping repair rounds and forcing a diagnosis artifact after failure #3 instead of failure #8.

## KPIs to measure after Phase 1 rollout (defined now, measured later)
- Task-to-`CLOSED_FINISHED`/`APPLIED_TO_PRODUCTION` time, by lane.
- Queue wait time, by lane (should approach zero for FAST once resource-aware locking is live).
- GitHub Actions runs per task, by lane (target: 1 run for FAST, ≤3 for STANDARD, ≤5 for CRITICAL including gate + apply + rollback-ready).
- AI calls per task, by lane (per budget table above).
- Retries per task (target: ≤2 before ROOT_CAUSE_MODE).
- False-"finished" count (tasks marked complete that were later reopened) — target trending to 0 once the canonical state machine removes ambiguous terminal states.
- Rollback rate for `APPLIED_TO_PRODUCTION` events.
