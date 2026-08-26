# TASK 006 — UNIVERSAL NEW-CARD FACTORY GATE FOR UA-0009, UA-0010, AND FUTURE CARDS

MODE: READ_ONLY
MAX_ROUNDS: 10

## Owner outcome

End the per-card technical-task cycle. Deliver ONE PythonAnywhere runner and ONE mobile-size instruction that handle UA-0009 and UA-0010 in the same run and form the reusable algorithm for future UA cards.

The owner must never need to understand GitHub, Claude rounds, SQLite schema, generators, hashes, OBD internals, or file paths. The operator experience must be:

1. Add/update vehicle data and media in CRM.
2. Run one file.
3. Receive one result per vehicle:
   - READY_FOR_VISUAL_CHECK
   - NEEDS_DATA: exact fields
   - BLOCKED_SAFETY: exact reason
4. After visual YES, a separate CRITICAL publication approval is still required.

Do not publish in this task and do not modify CRM or production.

## Inputs and known constraints

Default targets: UA-0009 and UA-0010.

UA-0009 confirmed evidence:
- VIN KNAGU416BJA242741
- Kia K5 2018
- gas/LPG
- engine 2000 cm3
- mileage 300000 km
- draft / published=0

UA-0010:
- Do not invent vehicle facts.
- Recover only from its own CRM row, own media rows/files, own diagnostics, and own sandbox.
- If no UA-0010 CRM row exists, report CARD_NOT_IN_CRM and continue processing UA-0009. Do not make UA-0009 fail because UA-0010 is absent.

Existing UA-0001 through UA-0008 are protected and must remain byte-identical.
Media is usable only when its CRM status is ready and the referenced file exists.
Diagnostic CTA appears only when genuine card-specific diag media/text/OBD evidence exists.
Two video slots must never contain identical SHA-256 content.
No production publication without backup, whitelist, rollback proof, green tests, visual YES, and explicit APPROVE.

## Mandatory audit corrections from task_005

The task_005 runner compiled, but it is not acceptable for owner use. Replace it; do not merely rename it.

Fix all of these proven defects:

1. It only selected auto_number, VIN, published, and status columns, so transmission, drivetrain, color, price and other real fields were guaranteed missing. The new runner must safely map and read all whitelisted vehicle fields from the matched target row.
2. It hardcoded OBD rule PASS without reading OBD evidence. Compute this from actual UA-specific CRM columns/files/HTML.
3. It hardcoded media PASS while referencing no media. Validate ready-state, file existence, nonzero size, allowed extension, and unique hashes.
4. Its UA-0010 test only rendered a plain synthetic HTML string. The new-card compatibility test must inspect the real generator/template source and run only an isolated, non-production dry build if that can be proven safe; otherwise report NOT_PROVEN, never PASS.
5. Its generator candidates missed the known live layout. Include bounded read-only candidates:
   /home/Carix/stranica.py
   /home/Carix/yadro.py
   /home/Carix/master_card.py
   /home/Carix/stroy3.py
   /home/Carix/stroy8.py
   /home/Carix/mysite/stranica.py
   /home/Carix/mysite/master_card.py
   plus evidence discovered from current UA-0009 sandbox HTML.
6. It created a bare text table and called it a preview. Build a faithful isolated preview only from the approved existing card/sandbox structure or a proven safe isolated generator path. If not possible, report PREVIEW_STRUCTURE_NOT_PROVEN.
7. It treated any missing price/color/transmission/drivetrain as a reason not even to show a visual draft. Separate:
   - VISUAL_DRAFT_REQUIRED_FIELDS: identity and enough real content to show a draft
   - PUBLICATION_REQUIRED_FIELDS: every mandatory live field
   A draft may show Уточняется for missing publication fields and still be READY_FOR_VISUAL_CHECK. Publication must remain blocked.
8. If a file is larger than the hash limit, report NOT_PROVEN. Never compare two null hashes and call the database unchanged.
9. Re-discover watched paths after execution and detect additions/deletions.
10. Do not trust arbitrary paths from a manifest unless they resolve inside approved /home/Carix production roots and are regular non-symlink files.
11. Do not hardcode PASS for any measured validation.
12. Use the real current UTC timestamp. 2025 timestamps are invalid.

## Universal runner

Create cloud/uaart_card_factory_gate.py, Python 3.10 stdlib only.

Default invocation:

python3.10 /home/Carix/uaart_card_factory_gate.py

Optional invocation:

python3.10 /home/Carix/uaart_card_factory_gate.py UA-0011 UA-0012

No free-form commands, no configuration execution, no network, no application-module import.

Allowed writes only:

- /home/Carix/sandbox_uaart_card_factory/<CARD_ID>/video/*
- /home/Carix/video/uaart_card_factory_report.txt
- /home/Carix/video/uaart_card_factory_report.json

All writes must be exact-root-contained, non-symlink, atomic, fsync, and measured. No other writes.

## Required per-card processing

For each requested card independently:

1. Normalize and validate ID strictly as UA-[0-9]{4}.
2. Open crm.db URI mode=ro plus query_only=ON.
3. Discover exact vehicle row(s) by auto_number and, when known, VIN.
4. Safely map whitelisted columns:
   auto_number, vin, make/brand, model, year, mileage, engine, fuel,
   transmission, drivetrain, color, price, stage/status, published,
   photo/image, video, diag/diagnostic, obd, container, date.
5. Inspect related media/reference tables only when their columns contain the same exact card ID/VIN. Never print unrelated rows or PII.
6. Classify duplicates with exact safe table/row evidence.
7. Locate card-specific ready media and reject pending/rejected/quarantine items.
8. Verify photos/videos/diag files exist, are nonzero, have safe extensions, and do not duplicate video hashes.
9. Verify OBD/diagnostic CTA rule with real evidence.
10. Locate newest card-specific sandbox HTML and validate structure, local references, mobile viewport, exactly one chat block, zero duplicate diagnostics CTA, zero empty src/href.
11. Build a faithful isolated review copy when safe evidence exists. Values inserted into HTML must be escaped. Never execute untrusted seed code or production generator code.
12. Run deterministic sandbox generation 10 times and require normalized 10/10 equality.
13. Report draft readiness separately from publication readiness.

## Global safety processing

- quick_check PASS.
- Database before/after proof.
- Full established protected baseline for UA-0001..UA-0008 and relevant shared files.
- Fresh after discovery detecting modification/addition/deletion.
- Static generator inspection for hard limits to 1..8 and special-casing.
- Synthetic future-card test only if it uses the actual proven isolated template/generator logic; otherwise NOT_PROVEN.
- No broad crawl, media conversion, service reload, WSGI/schedule changes, shell, subprocess, eval/exec, dynamic imports, or network calls.

## Final report format

First print a simple owner summary:

UA-0009 | READY_FOR_VISUAL_CHECK / NEEDS_DATA / BLOCKED_SAFETY | exact short reason
UA-0010 | READY_FOR_VISUAL_CHECK / NEEDS_DATA / BLOCKED_SAFETY | exact short reason
GLOBAL_SAFETY | PASS / FAIL / NOT_PROVEN
PRODUCTION_CHANGED | NO
NEXT_OWNER_ACTION | one sentence

Then include a detailed JSON-equivalent block.

Per card fields:

CARD_ID
CRM_ROW_FOUND
DUPLICATE_CLASSIFICATION
FIELDS_RECOVERED
VISUAL_DRAFT_MISSING_FIELDS
PUBLICATION_MISSING_FIELDS
READY_MEDIA
REJECTED_MEDIA
OBD_DIAGNOSTIC_RULE
HTML_VALIDATION
SANDBOX_10_RUNS
SANDBOX_PATH
READY_FOR_VISUAL_CHECK
READY_FOR_PUBLICATION
BLOCKERS

Global fields:

SQLITE_QUICK_CHECK
DATABASE_UNCHANGED
UA0001_0008_UNCHANGED
PROTECTED_SHARED_FILES_UNCHANGED
GENERATOR_NOT_HARD_LIMITED
FUTURE_CARD_TEST
UNEXPECTED_CHANGES
PRODUCTION_WRITE_PERFORMED: NO
SAFE_TO_PUBLISH_NOW: NO
STATUS

## Morning instruction

Create cloud/uaart_card_factory_morning.md with only five numbered steps on one mobile screen:
1. upload/pull one file
2. exact destination
3. exact run command
4. exact report path
5. send report back; do not publish

## Deliverables

1. cloud/uaart_card_factory_gate.py
2. cloud/uaart_card_factory_spec.md
3. cloud/uaart_card_factory_morning.md
4. cloud/cloud_report_006.md
5. cloud/latest_status.md

## Acceptance

- GitHub worker compiles the Python file.
- Cloud statically proves every write boundary and SQL read-only boundary.
- No hardcoded measured PASS.
- UA-0009 and UA-0010 are independent; missing UA-0010 never blocks UA-0009.
- The output is understandable without technical knowledge.
- If live facts are unavailable, the runner reports them honestly and still produces the maximum safe draft evidence.
- No publication, CRM change, existing-card change, or CRITICAL action.
