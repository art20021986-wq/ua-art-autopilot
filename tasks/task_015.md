# TASK 015 — UA ART SHARED MEMORY

OWNER APPROVAL: «УТВЕРЖДАЮ SHARED MEMORY»
APPROVED_AT_UTC: 2026-08-27T07:22:17Z
MODE: NON-PRODUCTION
PRODUCTION_WRITE: FORBIDDEN
CRM_WRITE: FORBIDDEN

## Objective
Implement one canonical, versioned UA ART Shared Memory used by Claude, ChatGPT, Python automation, and future agents so every worker starts from the same verified context and stale/conflicting tasks fail closed.

## Core contract
GitHub is canonical durable memory. PythonAnywhere may receive a safe read/sync mirror/index only and is not canonical. Claude/ChatGPT conversation memory is auxiliary and cannot override canonical memory. Every technical task performs MEMORY PREFLIGHT and builds a deterministic CONTEXT_BUNDLE carrying MEMORY_VERSION_READ and CONTEXT_BUNDLE_SHA256. Agents submit memory proposals to an inbox; canonical facts change only through guard/merge. Preserve Gate A/Gate B. Memory synchronization never grants production-write. Missing/corrupt/stale/conflicting memory fails closed for unsafe actions. Relevant website tasks must include evidence-based UA0009_SAFE_TO_PUBLISH=YES/NO.

## Required implementation
Create/document canonical memory including manifest, current state, immutable owner directives, architecture, production protection, source registry, decisions/incidents/task history, generic UA-XXXX card records with UA-0009 seeded, system records, active/completed tasks, schemas; plus deterministic memory_bootstrap.py, memory_guard.py, memory_merger.py, memory_healthcheck.py, context_builder.py and status_generator.py (equivalent safer names/structure allowed if documented).

Manifest must include schema_version, monotonic memory_version, generated_at_utc, git commit/bootstrap equivalent, previous version, canonical branch, managed-file SHA-256 and status.

Support record classes FACT, OWNER_DIRECTIVE, DECISION, HYPOTHESIS, INCIDENT, TASK, RESULT, WARNING, APPROVAL; HYPOTHESIS never silently becomes FACT.

Authority: direct owner directive > latest non-superseded owner approval/directive > verified production > verified CRM/SQLite > canonical GitHub > automated tests/reports > Claude/GPT report > AI hypothesis. Conflicts produce MEMORY_CONFLICT and are never silently resolved by timestamp.

Owner directives are append-only/immutable. Seed: Shared Memory approval; safe filtered upload/sync to PythonAnywhere allowed when required; that permission is NOT production-write; production-write still requires existing safe gate/owner approval; UA-0009 readiness must be checked in relevant website tasks.

Never persist API keys, GitHub tokens, passwords, cookies, session tokens, SSH private keys, PythonAnywhere secrets, or other secret values.

Define machine-readable inbox proposals with agent/task/version, discovered facts, file changes, tests, incidents, proposed decisions, card/current-state updates and evidence. Guard rejects/quarantines invalid schema, path traversal, secret-like content, unsupported classes, stale/conflicting unsafe updates and malformed evidence. Merger is deterministic/idempotent, preserves audit history, advances version only for accepted changes, regenerates hashes, and never writes production/CRM.

Context builder always includes global owner directives, production protection, current state, active task, architecture, incidents/protected components and relevant entity context; UA-XXXX automatically includes its card memory. cloud/latest_status.md and state/current_status.md become generated views from one canonical state rather than independent truths. Future tasks carry MEMORY_VERSION and CONTEXT_BUNDLE_SHA256 and stale tasks require revalidation/rebase. Parallel task dependencies must prevent stale execution.

Healthcheck verifies manifest/schema/hash consistency, card index, active task, owner directives, duplicates, conflicts, stale records/tasks, orphan references, secret leakage and production-write invariants.

## Acceptance
Sandbox tests must prove same canonical input gives Claude/GPT the same memory version/context hash; latest owner directive present; stale task detected; conflicts preserved; secrets blocked; forged/invalid owner-directive update blocked; replay idempotent; PythonAnywhere/Claude/GPT failure cannot corrupt canonical memory; sync failure cannot enable production write; UA-0009 gets full relevant context; future UA-XXXX is generic; latest/current status derive from one source; rollback/reconstruction documented/tested; production and CRM unchanged. Repeat tests where practical.

## Required report
Create cloud/cloud_report_015.md and update generated status mechanism. Include CLAUDE_STATUS, MEMORY_HEALTH, MEMORY_VERSION, CONTEXT_BUNDLE_SHA256, CONFLICT_DETECTION, SECRET_SCAN, STALE_TASK_PROTECTION, UA0009_MEMORY_CHECK, PRODUCTION_WRITE:NO, CRM_WRITE:NO, files changed, exact test results and remaining owner action.

## Hard prohibitions
NO production write. NO CRM write. NO owner-directive deletion/rewrite. NO secrets. NO direct agent-to-agent state treated as canonical without guard/merge. NO weakening Gate A/Gate B.

## Done
Shared Memory bootstrap, guard, merger, context builder, status generator, healthcheck and tests are committed; acceptance tests pass or blockers are evidenced; production/CRM remain untouched; report provides reproducible audit trail.