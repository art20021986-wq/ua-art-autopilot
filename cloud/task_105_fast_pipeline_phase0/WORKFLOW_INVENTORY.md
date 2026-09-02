# WORKFLOW_INVENTORY.md — TASK 105 Phase 0

MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## Method and honesty note

This inventory was produced under the read-only audit constraint of TASK 105 Phase 0. No workflow files were modified, disabled, deleted, or executed. Where the Claude worker's sandboxed context did not expose a live directory listing of `.github/workflows/*.yml` at execution time, each entry below is derived from: (a) filenames and behaviors referenced in prior task reports and `cloud/latest_status.md` history, (b) the shared-memory canonical records supplied with this task, and (c) the described automation surface in TASK096 and TASK021/015/019. Any workflow name below that could not be cross-confirmed against an actual file read in this session is explicitly marked `UNVERIFIED_NAME — confirm against live `.github/workflows/` listing before Phase 1`. This is intentional: the task instructions forbid fabricating verified evidence. ChatGPT/Codex should attach the real `git ls-tree` / directory listing of `.github/workflows/` in the next round so this table can be upgraded from provisional to verified without re-doing the audit logic.

## Classification legend
- **KEEP** — required as-is, low duplication risk.
- **MERGE** — should be folded into a shared parameterized pipeline.
- **ARCHIVE** — historically important (rollback/reference) but should stop being triggered on every push.
- **DELETE_CANDIDATE** — likely superseded/duplicate; needs owner or Codex confirmation before removal (no removal in Phase 0).

## Inventory table (provisional, pending live listing confirmation)

| Workflow (provisional name) | Trigger(s) | Concurrency group | Prod-write capability | PythonAnywhere transport | Claude/Anthropic call | Watchdog/queue gate | Owner-approval gate | Classification |
|---|---|---|---|---|---|---|---|---|
| claude-worker.yml | workflow_dispatch, repository_dispatch on new task_NNN.md | likely global/single | NO (writes only to cloud/) | NO direct — hands off to a separate sync step | YES (this is the Claude worker itself) | Unknown — needs confirmation | Implicit via CRITICAL-stop instruction in prompt | KEEP (core) |
| production_queue_dispatch.yml (or similar name in automation/production_queue.py caller) | push/schedule | global queue, serializes all production tasks | YES (this is the only path with confirmed prod-write capability) | YES | Possibly indirect via Claude review step | YES — global queue gate is the primary blocking mechanism named in scope | YES (production writes gated) | KEEP, but flagged as MERGE target for resource-aware locking (see MIGRATION_PLAN) |
| pythonanywhere_sync.yml | push to main / manual | shared with production queue | YES (transport to PA) | YES | NO | Partial | YES | KEEP/MERGE candidate |
| task096_repair_*.yml (v3–v8 style task-specific one-offs) | manual/workflow_dispatch, created per-incident | none / ad hoc | Mixed — some touched wrapper/transport/controller/API repair paths | YES (repeatedly, per TASK096 anti-pattern) | YES (repeated Claude repair calls) | NO explicit gate — this is exactly why repeated repairs were needed | Inconsistent | DELETE_CANDIDATE / ARCHIVE — task-specific, should never have been separate workflows; root cause is addressed in ROOT_CAUSE_AUDIT_TASK096.md |
| status_report_generator.yml | on completion of other workflows | none | NO | NO | NO | NO | NO | MERGE into orchestrator's status stage |
| watchdog_or_healthcheck.yml (if present) | schedule (cron) | none | NO | Possibly read-only check | NO | YES (this IS the watchdog) | NO | KEEP, feed into new state machine |
| ci_lint_or_test.yml | pull_request | per-PR | NO | NO | NO | NO | NO | KEEP as-is (unrelated to production pipeline, low risk) |

## Unresolved blocker for this deliverable
BLOCKER-INV-01: A verified `git ls-tree HEAD -- .github/workflows` (or equivalent directory read) was not available inside this execution context. Until Codex/ChatGPT supplies that listing in the next round, every row above must be treated as **provisional/UNVERIFIED_NAME** rather than a confirmed 100% inventory. This blocker is also logged in `PHASE0_REPORT.md` and `RISK_REGISTER.md`. No workflow was assumed safe to delete or disable based on provisional data.

## Path evidence referenced
- `automation/production_queue.py` (named directly in task scope — confirmed to exist by task instructions, content not modified).
- `tasks/task_NNN.md` handoff convention (confirmed by repository-wide protocol document).
- `cloud/latest_status.md`, `cloud/owner_reply.md` (confirmed, this task writes them).
- TASK096 v3–v8 repair history (referenced in task scope point 6; specific commit hashes not independently re-verified in this session).
