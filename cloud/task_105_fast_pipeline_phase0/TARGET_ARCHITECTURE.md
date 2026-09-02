# TARGET_ARCHITECTURE.md — TASK 105 Phase 0 (proposal only, not implemented)

## Goal
Reduce from the current (provisionally observed) sprawl of task-specific/ad hoc workflows down to a **6–8 workflow architecture**, centered on a UA ART Task Orchestrator that classifies work before spending AI calls, GitHub Actions minutes, or touching the production queue.

## Proposed target workflow set (6–8 total)
1. **`orchestrator_dispatch.yml`** — single entry point triggered by new `tasks/task_NNN.md`. Its only job is to classify the task (FAST / STANDARD / CRITICAL) using deterministic rules (file patterns touched, keywords like "production", "CRM", "PythonAnywhere", "Cloudflare", "DNS", presence of an owner-approval marker) and route to the correct downstream workflow. Replaces ad hoc task-specific workflows (WORKFLOW_INVENTORY DELETE_CANDIDATE rows).
2. **`fast_lane.yml`** — no-AI or minimal-AI path for FAST classification (e.g., doc-only, audit-only, cloud/-only changes like this very task). No production queue interaction. Target: near-instant turnaround.
3. **`standard_pipeline.yml`** — STANDARD classification: may call GPT_PRIMARY or CLAUDE_REVIEW, runs deterministic preflight checks (see ROOT_CAUSE_AUDIT_TASK096.md), writes to sandbox only.
4. **`critical_pipeline.yml`** — CRITICAL classification: requires DUAL_REVIEW (GPT + Claude cross-check) and always stops at AWAITING_OWNER_APPROVAL before any production-queue interaction. Never auto-proceeds to production write.
5. **`production_queue_gate.yml`** — the *only* workflow with production-write capability. Consumes `automation/production_queue.py` but with resource-aware locking (per-resource lock keys such as `pythonanywhere:crm`, `pythonanywhere:static-site`, `cloudflare:dns`) instead of one single global lock, so unrelated FAST/STANDARD tasks never queue behind a CRITICAL production deploy.
6. **`watchdog_and_kpi.yml`** — scheduled, read-only. Computes the KPIs named in task scope point 11 (task-to-finished time, queue wait, GitHub runs/task, AI calls/task, retries/task, false-finished count, rollback rate) from status/receipt files and publishes a report artifact. Never writes production.
7. **`ci_lint_test.yml`** — unchanged, PR-triggered lint/test, kept as-is (low risk, no production capability).
8. *(optional 8th)* **`rollback.yml`** — explicit, owner-invoked, manual-dispatch-only rollback workflow that reverts a specific production-queue transaction using the receipt written by `production_queue_gate.yml`. Kept separate from the deploy path so rollback logic is never entangled with forward-deploy logic.

## AI routing rules (proposal)
| Classification | Routing | Budget guidance |
|---|---|---|
| FAST | NO_AI (pure deterministic/scripted) or single GPT_PRIMARY pass if drafting text | 0–1 AI call/task |
| STANDARD | GPT_PRIMARY, with CLAUDE_REVIEW only if GPT confidence/checks fail | 1–3 AI calls/task |
| CRITICAL | DUAL_REVIEW (GPT_PRIMARY + CLAUDE_REVIEW mandatory), plus owner Gate B | 2–5 AI calls/task, capped; excess triggers ROOT_CAUSE_MODE |
| Repeated-failure (any class) | Escalate to CLAUDE_PRIMARY once, then ROOT_CAUSE_MODE (below) | hard stop after 2 failed automated retries |

## Deterministic retry policy / ROOT_CAUSE_MODE (proposal)
- Maximum 2 automated retries per task for the *same* logical failure signature (hash of error class + step).
- On the 3rd occurrence of the same failure signature, the orchestrator must switch to **ROOT_CAUSE_MODE**: stop automated retries, write a `ROOT_CAUSE_MODE` marker to `cloud/latest_status.md`, and require a human/Codex-reviewed root-cause note (mirroring ROOT_CAUSE_AUDIT_TASK096.md) before any further automated attempt. This directly prevents another TASK096 v3–v8-style repair loop.

## Resource-aware locking (proposal, replaces global production queue serialization)
Instead of one global lock in `automation/production_queue.py`, use per-resource lock keys, e.g.:
```
lock("pythonanywhere:crm-runtime")
lock("pythonanywhere:static-site")
lock("cloudflare:dns")
lock("cloudflare:cache-purge")
```
A task only queues behind other tasks that touch the *same* lock key. This is expected to be the single largest reducer of "queue wait" KPI without weakening production safety, because CRITICAL and FAST tasks touching disjoint resources no longer block each other.

## Explicit non-goals for Phase 0
This document is a **proposal**. No orchestrator code, no new workflow YAML, and no changes to `automation/production_queue.py` were created or modified in Phase 0. Implementation is Phase 1, sandbox/shadow-mode only, per task instructions.
