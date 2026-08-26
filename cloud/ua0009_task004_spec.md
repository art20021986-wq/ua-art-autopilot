# UA-0009 TASK_004 — Spec: Resolve Gate + Isolated Sandbox Draft

## Purpose
Get UA-0009 as far as possible toward a reviewable draft card WITHOUT touching
production, WITHOUT writing crm.db, and WITHOUT publishing. Resolve the
ambiguous "duplicate count 1" finding with precise evidence instead of
treating it as a confirmed true duplicate.

## Scope boundaries (hard)
- Reads `/home/Carix/crm.db` strictly via `sqlite3.connect("file:...?mode=ro", uri=True)`.
  No PRAGMA that mutates state (no journal_mode change, no writes).
- Writes are allowed ONLY to:
  - `/home/Carix/sandbox_ua0009_task004/video/*` (new isolated tree)
  - `/home/Carix/video/ua0009_task004.txt` (the one explicitly permitted report file)
- Never writes: `/home/Carix/site`, any other file under production `/home/Carix/video`,
  `crm.db`, WSGI files, cron/schedule files, or any UA-0001..UA-0008 file.
- Never borrows facts from UA-0001..UA-0008. Only UA-0009-row CRM data,
  UA-0009-named sandbox HTML, and the explicit owner-confirmed evidence
  constants (VIN, make/model/year, engine, mileage, fuel) are used.

## Track A — Duplicate resolution logic
1. Enumerate all tables in `crm.db` via `sqlite_master`.
2. For each table, scan rows (rowid + all columns, capped at 20,000 rows/table
   for safety) for:
   - exact match of `auto_number` column value == `UA-0009`
   - any column value containing the UA-0009 VIN (case-insensitive)
3. Classification decision tree:
   - No matches at all → `MORE_PROOF_NEEDED`, `UA0009_EXISTS_IN_CRM=NO`
   - Exactly one distinct `(table, rowid)` across both auto_number and VIN
     matches → `SAME_ROW_COUNTING_ARTIFACT` (the earlier "duplicate count 1"
     was simply the normal single-row match count, not a true duplicate)
   - More than one distinct rowid for auto_number **within the same table**
     → `TRUE_DUPLICATE`
   - Matches spread across more than one table but each table has at most one
     matching row → `MULTI_TABLE_REFERENCE_NOT_DUPLICATE` (e.g. main table +
     media/reference table, which is expected and not a defect)
   - Anything else / ambiguous → `MORE_PROOF_NEEDED`
4. Only safe, whitelisted columns (identity/spec columns) are extracted for
   the report; anything not matching the safe-column keyword list is treated
   as potential PII and excluded.
5. No delete/update/merge is ever executed regardless of classification.

## Track B — Field recovery
Recovery priority order per field:
1. UA-0009 CRM row value (if present and non-empty) → `PRESENT_CONFIRMED`
2. Regex-extracted value from the most recent UA-0009-named sandbox HTML
   (matched by `0009` or the VIN appearing in the filename) →
   `DERIVED_FROM_UA0009_ONLY_EVIDENCE`
3. Explicit owner-confirmed evidence constants (VIN, make, model, year,
   engine=2000cc, mileage=300000km, fuel=газ) used only inside the sandbox
   render, never written back to CRM → `DERIVED_FROM_UA0009_ONLY_EVIDENCE`
4. If still absent for a field required to render the draft meaningfully
   (transmission, drivetrain, color, price, stage) → rendered as the neutral
   marker `Уточняется` and listed under `UA0009_OWNER_INPUT_REQUIRED` →
   `MISSING_OWNER_REQUIRED`
5. Anything not needed to render a basic draft (e.g. secondary media counts)
   is `OPTIONAL_NOT_BLOCKING_DRAFT` and does not block sandbox creation.

Core identity fields (auto_number, VIN, make, model, year) are always
considered complete because they are already owner-confirmed, so
`UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE` reports YES even if secondary fields
are still pending — those pending fields do not block draft generation, only
publication.

## Track C — Isolated sandbox build
1. Hash (`sha256`) every file under production `video`/`site` whose name
   contains one of `UA-0001`..`UA-0008` (or its underscore variant) BEFORE any
   sandbox work.
2. Search `/home/Carix/sandbox2/video` and `/home/Carix/sandbox/video` for the
   newest HTML file whose filename contains `0009` or the VIN; treat it as an
   optional seed reference (copied verbatim into the new sandbox tree for
   comparison, never overwritten or modified in place).
3. Validate any seed HTML structurally (`<html>`, `<body>` present, count
   empty `src=""`/`href=""` attributes, count diagnostic-CTA mentions).
4. Render a self-contained card + diagnostics page under
   `/home/Carix/sandbox_ua0009_task004/video/` using only recovered/evidence
   values, with `Уточняется` for anything irreducibly missing. Exactly one
   diagnostic CTA link is included; no empty media elements are emitted
   (fields with no recoverable value are shown as text placeholders, not as
   broken `<img>`/`<video>` tags).
5. Re-hash the same UA-0001..UA-0008 files AFTER sandbox creation and require
   an exact match; any mismatch is reported as `UA0001_0008_UNCHANGED_AFTER:
   FAIL` and treated as a CRITICAL condition for owner review, even though the
   script's own file operations never touch those paths.
6. `SAFE_FOR_OWNER_VISUAL_REVIEW` is YES only if the sandbox was created AND
   the protected-file hash comparison passed.

## What this script deliberately does NOT do
- Does not execute any production generator/build script.
- Does not import or call any production publishing module.
- Does not reload/restart the web app.
- Does not change `published` status anywhere.
- Does not invent price, color, stage, transmission, or drivetrain values.

## Output contract
The script prints and writes (to the one permitted report file) the mandatory
final block specified in the task, always ending with
`SAFE_TO_PUBLISH_UA0009_NOW: NO` regardless of how good the draft looks —
publication is a separate, later, CRITICAL, owner-approved action after a
green release gate and visual review.
