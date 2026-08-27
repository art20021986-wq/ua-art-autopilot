# TASK 015 (retried under TASK 019) - UA ART Shared Memory - technical report

OWNER AUTHORIZATION: OWNER said 'ZAPUSKAY REMONT AUTOPILOT'. PARENT_TASK: task_015. MODE: NON_PRODUCTION.

CLAUDE_STATUS: DONE (deliverables complete and internally consistent by static code review; NOT independently executed by Claude in this authoring environment)

MEMORY_HEALTH: NOT_EXECUTED_BY_CLAUDE - implemented in `memory_healthcheck.py`; run `python memory_healthcheck.py` after `python memory_bootstrap.py` to obtain a real PASS/FAIL result.

MEMORY_VERSION: 1 (seed state, `manifest.json`, before any proposal is merged)

CONTEXT_BUNDLE_SHA256: NOT_COMPUTED_STATIC_ONLY - deterministic by construction (`context_builder.py` hashes `json.dumps(body, sort_keys=True)`); the next controller must run `python context_builder.py` to obtain the real value. Claude did not fabricate a hash.

CONFLICT_DETECTION: IMPLEMENTED, NOT EXECUTED. `memory_guard.compute_active_view` flags same-subject/same-class active records without a supersession chain as `CONFLICT` and never deletes them. Covered by `test_conflict_preserved`.

SECRET_SCAN: IMPLEMENTED, NOT EXECUTED. `memory_guard.scan_for_secrets` rejects proposals containing key/token/password/AKIA/sk-/ghp_/private-key/Bearer-like patterns before anything is written, and the rejection message never echoes the matched value. Covered by `test_secret_rejected_without_exposure`.

STALE_TASK_PROTECTION: IMPLEMENTED, NOT EXECUTED. `memory_merger.apply_proposal` compares `proposal.based_on_memory_version` against the current canonical `memory_version` and raises `StaleProposalError` on mismatch, before any file write. Covered by `test_stale_proposal_rejected`.

OWNER_DIRECTIVE_IMMUTABILITY: IMPLEMENTED, NOT EXECUTED. Only `author == 'OWNER'` may create an `OWNER_DIRECTIVE` record or supersede an existing immutable one; anything else raises `ForgedDirectiveError`. Covered by `test_forged_owner_directive_rejected`.

IDEMPOTENT_REPLAY: IMPLEMENTED, NOT EXECUTED. Each proposal is hashed; a repeated identical proposal returns `ALREADY_APPLIED` without duplicating records or advancing `memory_version`. Covered by `test_idempotent_replay`.

UA0009_MEMORY_CHECK: Seeded as `HYPOTHESIS` (REC-0006) plus `RESULT` (REC-0007) stating NOT_PROVEN. `status_generator.py` derives `ua0009_safe_to_publish` from the presence of a verified `APPROVAL` record with evidence; none exists yet.

UA0009_SAFE_TO_PUBLISH: NO (no real Gate A evidence exists in canonical memory)

PRODUCTION_WRITE: NO

CRM_WRITE: NO

## Exact files created in this task

- cloud/shared_memory/README.md
- cloud/shared_memory/manifest.json
- cloud/shared_memory/records.jsonl
- cloud/shared_memory/state/current_status.json
- cloud/shared_memory/schemas/record.schema.json
- cloud/shared_memory/schemas/proposal.schema.json
- cloud/shared_memory/memory_bootstrap.py
- cloud/shared_memory/memory_guard.py
- cloud/shared_memory/memory_merger.py
- cloud/shared_memory/memory_healthcheck.py
- cloud/shared_memory/context_builder.py
- cloud/shared_memory/status_generator.py
- cloud/shared_memory/test_shared_memory.py
- cloud/cloud_report_015.md
- cloud/latest_status.md
- cloud/owner_reply.md

## Honesty disclosure (do not treat as fabricated pass)

Claude authored this package statically in the sandboxed authoring environment and did not execute Python here. Nothing in this report claims a test run, a computed hash, or a healthcheck result that was not actually produced by running code. `manifest.json` ships with `file_hashes: null` for exactly this reason. All 14 acceptance tests in `test_shared_memory.py` are implemented to prove the required properties (identical-input hash stability, owner-directive presence, stale-proposal rejection, conflict preservation, secret rejection without exposure, forged-directive rejection, idempotent replay, corruption-resistance on invalid input, path-traversal rejection, UA-0009 context and non-publishability, generic future-record support, derived status, healthcheck PASS on clean seed state, and absence of any network/production-write capability in source) but their PASS/FAIL result must be produced by the next controller running `python -m unittest test_shared_memory -v` inside `cloud/shared_memory/`.

## Remaining controller verification (required before TASK 014/017 resume)

1. `cd cloud/shared_memory && python memory_bootstrap.py` (computes real file hashes)
2. `python -m unittest test_shared_memory -v` (must report 14/14 passing)
3. `python memory_healthcheck.py` (must report MEMORY_HEALTH: PASS)
4. `python context_builder.py UA-0009` and `python status_generator.py` (confirm UA-0009 SAFE_TO_PUBLISH stays NO)
5. Confirm no diff was made to any TASK 014/016/017/018 deliverable in this run (this task touched only `cloud/shared_memory/`, `cloud/cloud_report_015.md`, `cloud/latest_status.md`, `cloud/owner_reply.md`).

Only after step 2 and 3 both report real PASS should TASK 017 or TASK 014 resume, per ORDER_CONSTRAINT.
