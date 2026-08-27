# UA ART Shared Memory (canonical, versioned)

Status: memory version 4; TASK 015 accepted and corrected TASK 014/017 Gate A package independently verified. NON_PRODUCTION. No production or CRM write capability exists anywhere in this package.

## Purpose

This directory is the single canonical, versioned shared memory for UA ART Autopilot, as required by the canonical contract:

- GitHub is the canonical durable memory.
- PythonAnywhere may only ever receive an already-authorized filtered safe-inbox mirror; nothing in this package executes on PythonAnywhere.
- Conversation memory is auxiliary and never overrides these canonical records.
- Every future technical task should build a deterministic context bundle via `context_builder.py`, which returns `MEMORY_VERSION_READ` and `CONTEXT_BUNDLE_SHA256`.
- Gate A / Gate B are preserved. Nothing here grants production-write.
- Missing, corrupt, stale, conflicting, or secret-bearing input fails closed (raises an exception, nothing is written).

## Files

- `manifest.json` - schema version, monotonic `memory_version`, canonical branch, previous version, managed-file SHA-256 map, status.
- `records.jsonl` - append-only canonical record log (one JSON object per line).
- `state/current_status.json` - generated status view (derived, not hand-maintained).
- `schemas/record.schema.json`, `schemas/proposal.schema.json` - documentation-grade JSON Schemas describing the record and proposal shapes. `memory_guard.py` enforces the real constraints in Python (stdlib only, no jsonschema dependency).
- `memory_bootstrap.py` - idempotent bootstrap; computes and persists managed-file hashes.
- `memory_guard.py` - schema/proposal validation, secret scanning, path-traversal rejection, forged-directive rejection, conflict detection (`compute_active_view`).
- `memory_merger.py` - deterministic, idempotent proposal merger (append-only writes, monotonic version bump, replay-safe).
- `memory_healthcheck.py` - integrity checks (duplicate ids, hash match, immutability, secret scan, conflicts).
- `context_builder.py` - builds the deterministic context bundle and its SHA-256.
- `status_generator.py` - derives `state/current_status.json` purely from canonical records.
- `test_shared_memory.py` - stdlib `unittest` acceptance tests. Not executed by Claude in this run; must be executed independently by the next controller.

## Record classes

FACT, OWNER_DIRECTIVE, DECISION, HYPOTHESIS, INCIDENT, TASK, RESULT, WARNING, APPROVAL.

## Authority order (highest first)

direct owner directive > latest non-superseded owner approval/directive > verified production > verified CRM > canonical GitHub > automated evidence > AI report > hypothesis.

## Seeded immutable owner directives

- REC-0001 Shared Memory approved.
- REC-0002 filtered safe-inbox synchronization to PythonAnywhere is allowed when required.
- REC-0003 safe-inbox permission is not production-write permission.
- REC-0004 production-write remains behind the existing owner-bound Gate B.
- REC-0005 every relevant site task must verify UA-0009 readiness and protect existing cards.

Owner directives are `immutable: true` and can only be superseded by another `OWNER_DIRECTIVE` record authored by `OWNER` (`memory_guard.ForgedDirectiveError` otherwise).

## UA-0009

Seeded as HYPOTHESIS + RESULT with `SAFE_TO_PUBLISH: NO`. It stays NO until a real `APPROVAL` record with verified Gate A evidence is merged. `status_generator.py` derives this automatically; nothing hardcodes YES.

## How the next controller should verify this package

```
cd cloud/shared_memory
python memory_bootstrap.py
python -m unittest test_shared_memory -v
python status_generator.py
python context_builder.py UA-0009
python memory_healthcheck.py
```

None of these commands touch production, CRM, or PythonAnywhere. There is no network code, no subprocess, no filesystem access outside this directory tree.

## Controller acceptance

The controller executed the full acceptance suite after delivery: 15 of 15 tests passed, bootstrap populated every managed-file hash, the full managed-file healthcheck passed, and deterministic context construction passed. The acceptance is recorded append-only in canonical memory; it releases the TASK 014/017 ordering dependency but grants no Production or CRM write authority.

## TASK 021 Gate A package acceptance

The controller corrected the generated package and independently executed its complete offline suite ten times: 41 of 41 tests passed in every run (410 total), all Python files compiled, the no-argument entrypoint completed against temporary fixtures, protected inputs stayed byte-identical, and all writes stayed inside the temporary report namespace. REC-0013 records `READY_FOR_GATE_A_EXECUTION` only. Gate A has not been run on PythonAnywhere, Gate B is not authorized, Production/CRM remain unchanged, and UA-0009 remains `SAFE_TO_PUBLISH: NO`.
