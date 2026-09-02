# DEPENDENCY_MAP.md — TASK 105 Phase 0

## Purpose
Map triggers → jobs → shared resources → production-write capability, based on durable memory history (task_015/019/021/096) and the architecture implied by this repository's protocol (README-level rules in this task's system context).

## Core shared resources identified
1. **`automation/production_queue.py`** — described as the central queue mechanism gating production-affecting work. Current design (per task text) appears to enforce **global serialization**: one task occupies the whole queue regardless of blast radius (FAST vs CRITICAL), which is the primary throughput bottleneck this Phase 0 is meant to diagnose.
2. **Claude worker / launcher / transport** — the component that receives `tasks/task_NNN.md`, executes the worker, and writes `cloud/` deliverables + `cloud/latest_status.md` + `cloud/owner_reply.md`. TASK096 v3–v8 iterations indicate this transport layer was repeatedly patched (wrapper repairs), suggesting it lacks a deterministic preflight/contract test.
3. **PythonAnywhere sync/production paths** — a separate transport that moves verified artifacts to the live PythonAnywhere environment. Per REC-0002/REC-0003/REC-0004, only *filtered safe-inbox sync* is currently authorized; actual production write remains behind an owner-bound Gate B, independent of memory sync state.
4. **Status/receipt files** — `cloud/latest_status.md`, `cloud/owner_reply.md`, and per-task evidence files (e.g. Gate A evidence referenced in REC-0013) act as the source of truth for state, but the vocabulary (FINISHED / PASS / AWAITING_PRODUCTION_APPROVAL) is not a single canonical enum — see CURRENT_STATE_MACHINE.md.
5. **Shared Memory bundle** (`bundle`, `MEMORY_VERSION`, `CONTEXT_BUNDLE_SHA256`) — canonical durable memory referenced by every task; workflows that read/write records must not silently diverge from the hash used for context construction.

## Dependency chain (inferred, high-confidence based on task history)
```
task_NNN.md (push) 
  -> claude-worker workflow 
     -> Claude worker/launcher/transport 
        -> writes cloud/*, cloud/latest_status.md, cloud/owner_reply.md 
           -> (optional) production_queue.py enqueue 
              -> queue watchdog / retry workflow 
                 -> (Gate B / owner approval) 
                    -> PythonAnywhere production sync workflow 
                       -> live production paths (OUT OF SCOPE for Phase 0 write access)
```

## Overlap / duplication risk points
- Multiple task-specific repair workflows (TASK096 v3–v8) each independently touched wrapper/transport/controller/API layers instead of sharing one deterministic preflight step — this is the primary duplication risk (see ROOT_CAUSE_AUDIT_TASK096.md).
- Watchdog/retry logic appears to exist in more than one place (queue-level and workflow-level), risking double-retry / conflicting recovery actions.
- Status vocabulary is produced by multiple writers (Claude worker report vs Codex controller acceptance vs owner directive) without one canonical merge rule.

## Unresolved verification gap
Exact YAML `concurrency:` group names, `needs:` job graphs, and `on:` trigger filters could not be read verbatim in this session (see WORKFLOW_INVENTORY.md verification gap). This map is therefore a **logical dependency map derived from documented behavior**, not a line-by-line static analysis of the YAML. It should be reconciled against the literal files before Phase 1 implementation begins.
