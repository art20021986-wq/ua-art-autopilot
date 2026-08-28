# TASK 057 — PREPARE EXACT FERRY WORDING GATE B RELEASE PACKAGE

OWNER REQUEST: «Разрешаю» in direct response to the audited ferry wording Gate A preview and the requested phrase APPROVE FERRY GATE B.
INTERPRETATION: owner authorizes preparation of the production Gate B release for the already audited change “В море” → “На пароме” / “У морі” → “На поромі” across UA-0001..UA-0009 and future-card generators. This task MUST NOT write production yet because the current repository has no executable ferry Gate B and no exact release manifest SHA to bind the critical approval.

PARENT_TASKS: task_042, task_043, task_047, task_050, task_052
MODE: PREPARE_GATE_B_PACKAGE_ONLY / NO_PRODUCTION_WRITE
MAX_ROUNDS: 2
MEMORY_PREFLIGHT: REQUIRED

## Authoritative Gate A evidence

Use only:
- cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json
- cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md

Required current evidence:
- status = PASS_READY_FOR_GATE_B
- generated_at_utc = 2026-08-27T22:46:09Z
- 13 isolated HTML candidates
- 36 HTML wording changes
- 2 generator candidates
- stranica.py: 8 exact user-facing changes
- yadro.py: 10 exact user-facing changes
- production_write=false
- crm_write=false
- db_write=false
- service_reload=false
- gate_b_executed=false
- ua0009_published=false

Fail closed if these values or any recorded source/candidate SHA-256 differ.

## Goal

Create a separately reviewable, deterministic production Gate B package that can later apply only the exact audited candidate bytes to:
- video/index.html
- video/katalog.html
- video/info.html
- video/podbor.html (zero-change identity proof only; do not rewrite if byte-identical)
- video/UA-0001.html through video/UA-0009.html
- stranica.py
- yadro.py

No other production path may be modified. Internal stage value sea, URLs, IDs, CSS, JS, API, analytics and database enums must remain byte-identical.

## Required safety design

1. Build a canonical release manifest that contains for every target:
   - relative production path;
   - exact source SHA-256 from Gate A;
   - exact candidate SHA-256 from Gate A;
   - exact expected file size;
   - approved change count;
   - action REPLACE or VERIFY_UNCHANGED.
2. Include a canonical SHA-256 of the entire manifest.
3. Provide a fail-closed Gate B installer that is NOT executed in this task.
4. Installer must:
   - require an exact approval record containing task_id=task_057 and manifest_sha256;
   - require the exact phrase APPROVE_PRODUCTION TASK_057 MANIFEST_SHA256=<64hex>;
   - re-hash every live source before any write and abort if one differs;
   - verify every candidate byte/hash before any write;
   - reject symlinks, hardlinks, non-regular files, path escapes and changed parents;
   - create a complete timestamped backup of every REPLACE target before the first production write;
   - verify backup hashes equal source hashes;
   - use atomic same-filesystem temp-write + fsync + os.replace;
   - on any failure, restore every changed target from the verified backup and prove restored hashes;
   - after success, verify all target hashes equal the manifest;
   - never write crm.db or any CRM table;
   - never reload/restart WSGI, bot, service or schedule;
   - never publish UA-0009 as a separate new listing; this task only changes wording in its already existing candidate page;
   - emit one strict machine-readable receipt with before/after/backup hashes, timestamps, rollback status and explicit production/CRM/service/UA0009 markers.
5. Gate B installer must be bounded to /home/Carix and the exact allowlist above. No recursion and no broad find/replace.
6. Candidate bytes must come only from the audited Gate A candidate root recorded in the receipt. No regeneration during Gate B.
7. Every Python file must compile without importing or executing production modules.
8. Add standard-library tests covering clean success in a temp fixture, source drift, candidate drift, manifest tamper, invalid approval, missing approval, symlink/hardlink/path escape, backup mismatch, injected mid-write failure with complete rollback, receipt determinism, no CRM/reload/UA0009 publication, and exact allowlist rejection.

## Critical approval handling

The owner’s chat reply «Разрешаю» authorizes this preparation task, but MUST NOT be converted into a production execution token because the manifest SHA-256 does not exist yet.

After producing the package, set:
- STATUS_LABEL: AWAITING_EXACT_GATE_B_APPROVAL_TASK_057
- OWNER_ACTION_REQUIRED: YES
- OWNER_QUESTION: exact phrase with the generated manifest SHA-256

Do not claim Gate B approved or executed. Do not write production. Do not alter current live cards/generators/CRM/database/site/service.

## Deliverables

Create at most 12 files, all under cloud/task_057_ferry_gate_b/ plus the two shared status files:
- README.md
- release_manifest.json
- gate_b_installer.py
- verify_release.py
- tests/test_gate_b_installer.py
- run_tests.py
- TASK_057_REPORT.md
- exact_owner_approval.txt
- cloud/latest_status.md
- cloud/owner_reply.md

The release manifest must embed hashes already proven by Gate A and its own canonical manifest_sha256. The exact_owner_approval.txt file must contain only the exact one-line approval phrase required from the owner after review.

## Mandatory final markers

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SERVICE_RELOADED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
UA0009_SAFE_TO_PUBLISH: NO
STATUS_LABEL: AWAITING_EXACT_GATE_B_APPROVAL_TASK_057
