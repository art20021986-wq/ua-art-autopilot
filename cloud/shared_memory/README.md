# UA ART Shared Memory (canonical, versioned)

Status: TASK 019 (ordered retry / completion of TASK 015). NON_PRODUCTION. No production or CRM write capability exists anywhere in this package.

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

## Known limitation disclosed honestly

The shipped `manifest.json` ships with `file_hashes` set to `null` and `hashes_status: NOT_COMPUTED_RUN_MEMORY_BOOTSTRAP` because Claude did not execute Python in this authoring environment and will not fabricate SHA-256 values by hand. Running `memory_bootstrap.py` once computes and persists the real hashes deterministically. `memory_healthcheck.py` only hash-compares when a hash is already recorded, so it fails closed rather than silently trusting an unverified value.
