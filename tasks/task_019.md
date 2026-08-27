# TASK 019 — ORDERED RETRY OF TASK 015: UA ART SHARED MEMORY

OWNER AUTHORIZATION: «ЗАПУСКАЙ РЕМОНТ AUTOPILOT»
PARENT_TASK: task_015
ORDER_CONSTRAINT: COMPLETE_AND_VERIFY_TASK_015_BEFORE_TASK_017_OR_TASK_014
MODE: NON_PRODUCTION
PRODUCTION_WRITE: FORBIDDEN
CRM_WRITE: FORBIDDEN
PYTHONANYWHERE_EXECUTION: FORBIDDEN_IN_THIS_TASK

## Objective

Repeat and complete the previously failed TASK 015 after the Autopilot retry/rebase repair. Implement one canonical, versioned UA ART Shared Memory inside `cloud/shared_memory/`. This task must finish and produce an independently testable report before TASK 017/TASK 014 may resume.

## Canonical contract

- GitHub is the canonical durable memory.
- PythonAnywhere may receive only the already-authorized filtered safe-inbox mirror; this task does not execute anything there.
- Conversation memory is auxiliary and never overrides canonical records.
- Every future technical task must build a deterministic context bundle containing MEMORY_VERSION_READ and CONTEXT_BUNDLE_SHA256.
- Preserve Gate A/Gate B. Memory sync never grants production-write.
- Missing, corrupt, stale, conflicting, or secret-bearing context fails closed.
- Relevant website/card work must include evidence-based UA0009_SAFE_TO_PUBLISH=YES/NO.
- Owner directives are append-only and cannot be silently rewritten or deleted.
- Never store API keys, passwords, tokens, cookies, private keys, credentials, database blobs, or unrelated personal data.

## Required canonical data

Create a compact, maintainable memory package with:

1. Manifest: schema version, monotonic memory version, canonical branch, previous version, deterministic managed-file SHA-256 map, status.
2. Records supporting: FACT, OWNER_DIRECTIVE, DECISION, HYPOTHESIS, INCIDENT, TASK, RESULT, WARNING, APPROVAL.
3. Authority order:
   direct owner directive > latest non-superseded owner approval/directive > verified production > verified CRM > canonical GitHub > automated evidence > AI report > hypothesis.
4. Seeded immutable directives:
   - Shared Memory approved;
   - filtered safe-inbox synchronization to PythonAnywhere is allowed when required;
   - safe-inbox permission is not production-write permission;
   - production-write remains behind the existing owner-bound Gate B;
   - every relevant site task must verify UA-0009 readiness and protect existing cards.
5. Seed UA-0009 with publication status NOT_PROVEN / SAFE_TO_PUBLISH: NO until real Gate A evidence exists.
6. Current state and task history showing TASK 015 retry is active/completed as measured, TASK 014/017 depends on successful memory acceptance, and production remains protected.

## Required tools

Implement Python 3.10+ stdlib-only deterministic tools:

- bootstrap;
- proposal/schema guard;
- deterministic idempotent merger;
- healthcheck;
- context builder;
- generated status view.

The guard must reject path traversal, stale proposals, unsupported classes, secret-like values, forged owner-directive mutation, malformed evidence, and unsafe conflict resolution. Conflicts must emit MEMORY_CONFLICT and remain preserved.

## Acceptance tests

Provide executable tests proving:

- identical canonical input creates identical context hash;
- latest immutable owner directives are present;
- stale task/proposal is rejected;
- conflicts are preserved;
- secret-like content is rejected without exposing the secret;
- forged owner-directive replacement/deletion is rejected;
- replay is idempotent;
- external sync/agent failure cannot corrupt canonical memory or enable production-write;
- UA-0009 receives required context and remains SAFE_TO_PUBLISH: NO without real evidence;
- generic future UA-XXXX record is supported;
- status is derived from canonical state;
- production and CRM writes are impossible in this package.

Do not invent passing results. Report static-only checks separately from executed acceptance tests. The next controller will independently execute the tests.

## Deliverables

Return complete contents for all of these exact files, no placeholders and no extra generated binaries:

- `cloud/shared_memory/README.md`
- `cloud/shared_memory/manifest.json`
- `cloud/shared_memory/records.jsonl`
- `cloud/shared_memory/state/current_status.json`
- `cloud/shared_memory/schemas/record.schema.json`
- `cloud/shared_memory/schemas/proposal.schema.json`
- `cloud/shared_memory/memory_bootstrap.py`
- `cloud/shared_memory/memory_guard.py`
- `cloud/shared_memory/memory_merger.py`
- `cloud/shared_memory/memory_healthcheck.py`
- `cloud/shared_memory/context_builder.py`
- `cloud/shared_memory/status_generator.py`
- `cloud/shared_memory/test_shared_memory.py`
- `cloud/cloud_report_015.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

## Required final report fields

`cloud/cloud_report_015.md` must include:

- CLAUDE_STATUS
- MEMORY_HEALTH
- MEMORY_VERSION
- CONTEXT_BUNDLE_SHA256
- CONFLICT_DETECTION
- SECRET_SCAN
- STALE_TASK_PROTECTION
- OWNER_DIRECTIVE_IMMUTABILITY
- IDEMPOTENT_REPLAY
- UA0009_MEMORY_CHECK
- UA0009_SAFE_TO_PUBLISH: NO unless real Gate A evidence exists
- PRODUCTION_WRITE: NO
- CRM_WRITE: NO
- exact files created
- tests claimed only at their actually verified level
- remaining controller verification

## Completion gate

Do not resume, modify, or overwrite TASK 014/016/017/018 deliverables in this run. Finish TASK 015 Shared Memory only. Production, CRM, live cards, generators, WSGI and UA-0009 publication must remain unchanged.
