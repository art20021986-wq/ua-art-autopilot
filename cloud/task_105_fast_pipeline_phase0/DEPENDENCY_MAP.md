# DEPENDENCY_MAP.md — TASK 105 Phase 0

## Core dependency chain (as understood from protocol + task096 history)

```
owner request
  -> Codex writes tasks/task_NNN.md (durable handoff, GitHub)
    -> GitHub Actions trigger: claude-worker.yml
      -> Claude worker reads newest tasks/task_NNN.md
      -> Claude worker writes cloud/ deliverables + cloud/latest_status.md + cloud/owner_reply.md
    -> (separate) production_queue.py enqueues/serializes any task marked for production write
      -> PythonAnywhere transport step (sync/deploy)
        -> PythonAnywhere production filesystem / CRM runtime
    -> status/receipt files (cloud/latest_status.md, plus any *.receipt.json under automation/ or logs/) recorded
    -> Codex/ChatGPT audits cloud/ outputs and relays to owner
```

## Shared dependencies identified
1. **`automation/production_queue.py`** — named in scope as the single serialization point for production writes. This is the global lock referenced in KPI item "queue wait" and the target of the resource-aware locking proposal (see TARGET_ARCHITECTURE.md). It is a shared dependency for *every* task that eventually needs a production write, regardless of whether the task itself is FAST, STANDARD, or CRITICAL — this is the root cause of unnecessary global blocking called out in the task objective.
2. **Claude worker/launcher/transport chain** — the same worker code path handles trivial doc-only tasks (like this Phase 0 audit) and CRITICAL production-affecting tasks. There is currently no classification step before invocation, so every task pays the same AI-call and retry cost.
3. **PythonAnywhere sync/production paths** — a single transport mechanism is reused across tasks; TASK096 v3–v8 shows this transport was repeatedly repaired in-place rather than validated once with a deterministic preflight check.
4. **Status/receipt files** — `cloud/latest_status.md` is overwritten per task rather than appended/versioned, which is one contributor to the FINISHED/PASS/AWAITING_PRODUCTION_APPROVAL ambiguity (task scope point 7): there is no single canonical state file separate from the human-readable status report.

## Cross-task coupling risk
- Any workflow that both (a) can trigger on a schedule/cron AND (b) shares the same concurrency group as the production queue creates unpredictable serialization: a low-priority scheduled healthcheck can block a FAST classification task. This is the primary technical justification for replacing global serialization with resource-aware locking.
- Task-specific repair workflows (TASK096 v3–v8 pattern) each independently touched wrapper/transport/controller/API code, meaning the same underlying bug surface was patched multiple times through different one-off workflow files instead of once through a shared deterministic preflight. This created N workflows depending on the same fragile transport instead of 1 workflow depending on a validated transport.

## Unresolved blocker
BLOCKER-DEP-01: exact concurrency-group names and job-level `needs:` graphs could not be read from live YAML in this session (same root cause as BLOCKER-INV-01). The dependency chain above is derived from documented protocol behavior and task096 narrative evidence, not a byte-level YAML diff.
