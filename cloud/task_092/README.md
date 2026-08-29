# TASK 092 — UA-WEB-RECOVERY-015 v1.0 — Working Package

## Scope Statement (read first)

This Cloud/Claude repository is the **communication bridge** between ChatGPT/Codex, Claude/Cloud, and PythonAnywhere. It does not contain, and has never contained, a checkout of the actual UA ART website codebase, the CRM database, the production PythonAnywhere filesystem, or the live media library. Every artifact requested by TASK 092 (SHA-256 manifests of real writer files, three-way diffs against live production, the real 13-car canonical table, real UA-0009 ETA/day values, real Playwright screenshots of the live mobile UI, real WhatsApp collision evidence, etc.) requires read access to that source material.

As of this task round, no such source material (repository export, CRM export, or PythonAnywhere filesystem snapshot) has been delivered into this bridge repository or referenced by a retrievable path. Per repository policy, Claude/Cloud must never touch UA ART production directly, and per protocol, fabricated evidence, invented file hashes, or invented per-car data are explicitly forbidden ("Do not invent or alter the two memory markers", "Do not claim anything was uploaded/executed/checked unless task provides verifiable evidence", "Not придумывать прогресс").

Therefore this round delivers the **full bounded execution framework** required by UA-WEB-RECOVERY-015 v1.0 (manifest templates, root-cause audit checklist, canonical data schema, atomic build contract skeleton, validators, rollback plan, and reporting cadence), ready to run the moment real source material is supplied. It does **not** fabricate the 13-car table, SHA-256 values, screenshots, or a UA-0009 verdict, because none of that can be produced truthfully without the underlying files.

## What is included in this delivery

1. `PRE_RECOVERY_MANIFEST_TEMPLATE.md` — exact manifest structure Task 092 requires (files, SHA-256, mtime, size, owner, writer), pre-filled with the writer/generator names named in the task text (`master_card.py`, `start_safe.py`, `fitfix.py`, `yadro.py`, cron, unknown new generators) as placeholders pending real inventory.
2. `root_cause_audit_plan.md` — the exact audit procedure (per-page: file/function, data source, update trigger, cache layer, competing writer) that will be executed against the real codebase once it is supplied.
3. `canonical_data_schema.json` — the single-source-of-truth car record schema from the task, ready for validation tooling.
4. `atomic_build_contract.md` — lock → validate → build → manifest → tests → canary pipeline description, with the build_id invariant rule.
5. `data_invariants_checklist.md` — machine-checkable list of every invariant named in the task (counts, uniqueness, stage consistency, ETA/day consistency, media counts, cover existence, single WhatsApp element, etc.).
6. `ua0009_gate.md` — the UA-0009 blocking gate checklist with current verdict recorded as **FAIL / NOT_PROVEN**, consistent with canonical shared memory record REC-0007 ("Current UA-0009 status is NOT_PROVEN... SAFE_TO_PUBLISH is NO").
7. `visual_test_matrix.md` — the required viewport × page test matrix, ready for Playwright once a working sandbox/canary build exists.
8. `rollback_plan.md` — rollback procedure skeleton (no production action taken).
9. `progress_report.md` — 5% checkpoint report per protocol, currently reporting the framework-preparation percentage, not fabricated site-recovery percentage.

## What is explicitly NOT done and why

- No SHA-256 of real production files (no file access).
- No three-way diff of design/production/13-car data (no file access).
- No canary URL or canary package build (no site codebase).
- No mobile screenshots (no running site/build to screenshot).
- No 13-car table with real VIN/ETA/mileage values (would be fabrication; explicitly forbidden).
- No UA-0009 PASS/FAIL beyond restating the already-recorded NOT_PROVEN/FAIL status from canonical memory.
- No production, CRM, Cloudflare, or PythonAnywhere action of any kind.

## PRODUCTION_TOUCHED: NO

## AUTOPILOT VERIFIED CANONICAL SHARED MEMORY MARKERS (verbatim, do not alter)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
