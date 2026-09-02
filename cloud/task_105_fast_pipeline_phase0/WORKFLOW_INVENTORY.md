# WORKFLOW_INVENTORY.md — TASK 105 Phase 0

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Method and honesty disclosure
This Phase 0 audit was produced by the Claude/Cloud worker without direct interactive filesystem browsing tools in this execution context. The worker did not run `ls .github/workflows/` or open each YAML file live. Because the durable-memory protocol in this repository forbids fabricating verification evidence, this inventory is delivered as:

1. A **structural inventory template** with the exact classification schema required by the task, ready to be filled/confirmed against the live tree.
2. **Known workflow references** that are inferable with reasonable confidence from durable task history already present in `cloud/` and `tasks/` (task_015, task_019, task_021, task_096 v3-v8, task_105 itself), because those tasks explicitly describe Claude worker launch, PythonAnywhere sync, and production queue behavior driven by GitHub Actions.
3. Explicit **UNVERIFIED** markers on every row whose existence/content the worker could not confirm by reading the actual file in this session.

This is reported transparently in `PHASE0_REPORT.md` as an unresolved blocker. It is not a claim of 100% verified inventory; it is the best-effort deliverable achievable in this session, structured so the controller (Codex/ChatGPT) can diff it against the real `.github/workflows/` directory in one pass and mark items CONFIRMED.

## Classification schema (as required by task)
- KEEP — required, no overlap, correct scope.
- MERGE — overlaps with another workflow; should become one parameterized shared pipeline.
- ARCHIVE — historical/task-specific, safe to move out of active triggers but not delete.
- DELETE_CANDIDATE — appears fully superseded/duplicate; requires owner sign-off before removal (not performed in Phase 0).

## Inventory table (fill/confirm against live `.github/workflows/*.yml`)

| # | Workflow file (expected/likely) | Purpose (inferred) | Trigger(s) | Production-write capable? | PythonAnywhere transport used? | Claude/Anthropic call? | Classification | Verification status |
|---|---|---|---|---|---|---|---|---|
| 1 | claude-worker.yml (or similarly named worker dispatcher) | Launches Claude/Cloud worker on new task_NNN.md, writes cloud/ deliverables, status, owner_reply | push to tasks/**, workflow_dispatch | NO (worker writes only to cloud/) | Possibly triggers downstream sync, not direct | YES (Claude/Anthropic) | KEEP | UNVERIFIED — confirm exact filename and trigger paths |
| 2 | production_sync.yml / pythonanywhere_deploy.yml (naming inferred) | Pushes verified changes to PythonAnywhere production paths | manual/workflow_dispatch, possibly tag-gated | YES — production writer | YES | Possibly NO | KEEP (highest scrutiny) | UNVERIFIED — must confirm this is gated behind owner approval (Gate B per REC-0004) |
| 3 | queue_watchdog.yml / production_queue watchdog | Monitors automation/production_queue.py state, retries stuck tasks | schedule (cron) | Indirect (can trigger writer workflows) | Possibly | NO | MERGE candidate into orchestrator | UNVERIFIED |
| 4 | task096-repair / wrapper-repair workflows (v3–v8 iterations) | One-off repair workflows created during TASK096 wrapper/transport/controller/API fix cycles | manual/workflow_dispatch | Varies | Varies | Varies | ARCHIVE (root cause: reactive per-incident workflow creation instead of deterministic preflight — see ROOT_CAUSE_AUDIT_TASK096.md) | UNVERIFIED — likely multiple near-duplicate files (v3, v4, v5, v6, v7, v8 suffixes or similar) |
| 5 | ci-tests.yml / offline-tests.yml | Runs offline test suites (e.g. the 41/41 suite referenced for TASK021) | push, pull_request | NO | NO | NO | KEEP | UNVERIFIED |
| 6 | shared-memory-verify.yml (or bootstrap/healthcheck workflow referenced for TASK015/019) | Verifies canonical shared memory bundle hash, bootstrap, healthcheck | push to cloud/**, schedule | NO | NO | NO | KEEP, candidate for MERGE into orchestrator preflight | UNVERIFIED |
| 7 | gate-a-package.yml (Gate A execution/prep) | Prepares/executes Gate A evidence packages (TASK014/017) | manual/workflow_dispatch | Conditional — evidence only, not production | Possibly | NO/Possibly | KEEP, high scrutiny | UNVERIFIED |
| 8 | misc one-off task workflows (task-specific dispatchers per TASK_ID) | Ad-hoc workflows created per task number instead of parameterized | workflow_dispatch | Varies | Varies | Varies | DELETE_CANDIDATE / MERGE into single parameterized `task-dispatcher.yml` | UNVERIFIED — count unknown |

## Required next action to close verification gap
Controller/Codex (or a subsequent Claude session with `ls`/`cat` tool access) must:
1. Run `find .github/workflows -maxdepth 1 -type f` and paste the literal file list into a follow-up task or into `cloud/task_105_fast_pipeline_phase0/WORKFLOW_INVENTORY_CONFIRMED.md`.
2. For each file, confirm trigger block, `concurrency:` group, and any `secrets.*`/PythonAnywhere/Anthropic API usage lines (without pasting secret values).
3. Re-run the classification pass against confirmed content.

Until that confirmation happens, the classifications above are **provisional** and must not be used as authorization to archive/delete/merge any real file.
