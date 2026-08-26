# TASK 004 — UA-0009 DRAFT CARD LAUNCH: RESOLVE GATE + BUILD ISOLATED SANDBOX

MODE: READ_ONLY
MAX_ROUNDS: 10

## Owner directive
Prepare and launch the ninth card as far as safely possible now, with minimum owner involvement. The owner wants a usable UA-0009 draft/card for placement. Do NOT publish to production yet because the current release gate is not green. Do not ask the owner to repeat facts already present in UA-0009 evidence.

## Known confirmed UA-0009 facts
Use only as UA-0009-specific evidence, never copy from another vehicle:
- auto_number: UA-0009
- VIN: KNAGU416BJA242741
- make/model/year: Kia K5 2018
- fuel: gas/LPG (CRM value previously reported as `газ`)
- engine: 2000 cm3 (owner evidence)
- mileage: 300000 km (owner evidence)
- published: 0 / draft

Current PythonAnywhere gate evidence also reported:
- SQLite quick_check PASS; journal_mode delete
- UA-0009 exists in CRM
- reported VIN duplicate count 1 and auto_number duplicate count 1 — these must be investigated, not blindly treated as true duplicates
- existing UA-0009 sandbox HTML files were previously seen under `/home/Carix/sandbox2/video/` and `/home/Carix/sandbox/video/`
- UA-0001..UA-0008 baseline was captured
- current SAFE_TO_PUBLISH_UA0009_NOW is NO

## Goal
Produce a single safe PythonAnywhere launcher/probe that, when run, does all non-destructive work needed to get UA-0009 into an isolated, reviewable draft sandbox and tells us exactly what irreducible owner data remains. It must NEVER write production, never alter crm.db, and never publish.

### Track A — resolve duplicate finding precisely
Read `/home/Carix/crm.db` in SQLite URI `mode=ro` only. Locate every row matching UA-0009 auto_number and every row matching the UA-0009 VIN. Report only safe identifiers needed to distinguish the rows (table, rowid/primary key, auto_number, VIN, published/status if present), no unrelated customer PII. Classify:
- TRUE_DUPLICATE
- SAME_ROW_COUNTING_ARTIFACT
- MULTI_TABLE_REFERENCE_NOT_DUPLICATE
- MORE_PROOF_NEEDED
Do not delete/update/dedupe anything.

### Track B — recover all UA-0009-only fields automatically
Search only UA-0009-specific sources: the UA-0009 CRM row(s), existing UA-0009 sandbox HTML, UA-0009-specific files/media metadata/filenames, and source/config text. Never borrow values from UA-0001..UA-0008.
For each publication field classify:
- PRESENT_CONFIRMED
- DERIVED_FROM_UA0009_ONLY_EVIDENCE
- MISSING_OWNER_REQUIRED
- OPTIONAL_NOT_BLOCKING_DRAFT

At minimum cover: auto_number, VIN, make, model, year, mileage, engine, fuel, transmission, drivetrain, color, price, stage/status, published, photos, videos, diagnostic references.
The known owner evidence above may satisfy engine and mileage if CRM lacks them, but only in the isolated sandbox/report; do not write those values to production CRM.

### Track C — build/launch isolated UA-0009 draft sandbox
The launcher may write ONLY inside a newly created isolated directory under `/home/Carix/sandbox_ua0009_task004/` and its own report `/home/Carix/video/ua0009_task004.txt`.
It must not write `/home/Carix/site`, production `/home/Carix/video` HTML/media (except the one report txt), `/home/Carix/crm.db`, production source files, WSGI, schedules, or any UA-0001..UA-0008 file.

Preferred safe strategy:
1. Capture SHA-256 of current protected production UA-0001..UA-0008 files before sandbox work.
2. Locate the newest existing UA-0009 sandbox card/diag HTML and use it as a seed if it is structurally valid.
3. Create a self-contained review copy under `/home/Carix/sandbox_ua0009_task004/video/`.
4. Fill only values supported by UA-0009-specific evidence. For irreducible missing owner fields, render a visible neutral `Уточняется`/draft marker in the sandbox rather than inventing a value.
5. Preserve the approved card structure/style as far as can be verified from current source/baseline, but do not execute production generators if they can write outside the sandbox.
6. Validate HTML, local references, required buttons/diagnostic structure, no duplicate diagnostic CTA, no broken empty media elements, and no production-path writes.
7. Re-hash UA-0001..UA-0008 after sandbox creation and require exact unchanged result.
8. Produce a concise final owner-input list containing ONLY fields that truly cannot be recovered automatically.

If safe sandbox generation cannot be proven, do not improvise: produce a launcher that stops before any unsafe step and reports the exact blocker.

## Deliverables under cloud/
Create/update all of:
1. `cloud/ua0009_task004_launcher.py` — Python 3.10 stdlib only; production read-only; writes only isolated sandbox plus the one report txt.
2. `cloud/ua0009_task004_spec.md`
3. `cloud/cloud_report_004.md`
4. `cloud/latest_status.md`

Cloud must compile/static-check the Python launcher before finishing. Do not claim PythonAnywhere execution unless it actually occurred there.

## Mandatory launcher final block
TASK_ID: task_004
SQLITE_QUICK_CHECK: PASS/FAIL
DUPLICATE_CLASSIFICATION: ...
UA0009_EXISTS_IN_CRM: YES/NO
UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE: YES/NO
UA0009_OWNER_INPUT_REQUIRED: ...
UA0009_EXISTING_SANDBOX_FOUND: YES/NO
UA0009_TASK004_SANDBOX_CREATED: YES/NO
UA0009_TASK004_CARD_PATH: ...
UA0009_TASK004_DIAG_PATH: ...
UA0001_0008_UNCHANGED_AFTER: PASS/FAIL
PRODUCTION_WRITE_PERFORMED: NO
DATABASE_CHANGED: NO
PRODUCTION_SITE_FILES_CHANGED: 0
SAFE_FOR_OWNER_VISUAL_REVIEW: YES/NO
SAFE_TO_PUBLISH_UA0009_NOW: NO
NEXT_ACTION: ...

## Hard prohibitions
- no production publication
- no write/update/delete in crm.db
- no WAL/journal_mode change
- no production source edits
- no production HTML/media edits
- no WSGI/reload/restart
- no copying vehicle facts from UA-0001..UA-0008
- no invented price/color/stage/transmission/drivetrain
- no destructive duplicate cleanup

## Acceptance
Task is successful when Cloud delivers a statically valid safe launcher capable of creating an isolated reviewable UA-0009 draft on PythonAnywhere, or proves a concrete blocker. Owner should only be asked for irreducible vehicle facts after automatic recovery is exhausted. Publication remains a later CRITICAL action after visual review and a green release gate.