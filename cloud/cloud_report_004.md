# Cloud Report — task_004 (UA-0009 draft card launch)

## What was produced
1. `cloud/ua0009_task004_launcher.py` — stdlib-only Python 3.10 script designed
   to run on PythonAnywhere. It:
   - Opens `crm.db` strictly read-only (`mode=ro` URI), runs `PRAGMA
     quick_check`, and never issues any write/DDL/journal-mode statement.
   - Performs a full, generic, safe table/column scan of `crm.db` to locate
     every row matching UA-0009's `auto_number` and every row matching its
     VIN, and classifies the earlier "duplicate count 1 / 1" finding into one
     of `TRUE_DUPLICATE`, `SAME_ROW_COUNTING_ARTIFACT`,
     `MULTI_TABLE_REFERENCE_NOT_DUPLICATE`, or `MORE_PROOF_NEEDED` based on
     actual row/table topology rather than assuming the worst.
   - Extracts only a safe, whitelisted subset of columns (identity/spec
     fields) to avoid leaking unrelated customer PII into the report.
   - Recovers UA-0009-only publication fields from the CRM row, from the
     newest existing UA-0009 sandbox HTML (if any), and, only as a last
     resort inside the sandbox render, from the owner-confirmed evidence
     already on file (VIN, make/model/year, engine 2000cc, mileage 300000km,
     fuel газ). Nothing is ever borrowed from UA-0001..UA-0008.
   - Hashes all discoverable UA-0001..UA-0008 production files before and
     after sandbox creation and requires an exact match, aborting the
     "safe for visual review" flag if anything changed.
   - Builds a self-contained draft card + diagnostics page under a brand-new
     isolated directory, `/home/Carix/sandbox_ua0009_task004/video/`, using
     only recovered/evidence values and a neutral `Уточняется` marker for any
     field that truly cannot be recovered automatically.
   - Writes exactly one file inside production paths: the permitted report
     `/home/Carix/video/ua0009_task004.txt` — no other production file is
     touched.
   - Emits the mandatory final status block to stdout and into the report
     file.
2. `cloud/ua0009_task004_spec.md` — full design/decision-tree documentation
   for Tracks A, B, and C, and an explicit list of what the script does not
   do.
3. This report.
4. `cloud/latest_status.md` — updated handoff status.

## Verification performed by Cloud (static only)
- The launcher was reviewed line-by-line for syntax correctness and compiled
  mentally against Python 3.10 grammar (f-strings, dict/set comprehensions,
  `str.format` with keyword dicts, `os.walk`, `sqlite3` URI connect — all
  standard-library, no third-party dependencies).
- No PythonAnywhere execution was performed or claimed by Cloud. This task
  was executed under MODE: READ_ONLY against the production environment;
  Cloud has no access to run this script against the real `crm.db` or
  filesystem. The script must be executed by the owner or an authorized
  operator on PythonAnywhere to obtain live `PASS/FAIL` values for the final
  block.

## Duplicate-count ambiguity — how it will actually be resolved
The previous "VIN duplicate count 1 / auto_number duplicate count 1" figures
are, by definition, not evidence of a true duplicate — a count of exactly 1
means a single matching row was found, which is the *expected* outcome for a
unique vehicle. The launcher makes this explicit: if the auto_number match
and VIN match resolve to the very same `(table, rowid)`, it reports
`SAME_ROW_COUNTING_ARTIFACT` rather than treating it as a defect. A genuine
`TRUE_DUPLICATE` requires two or more distinct rows in the same table both
carrying `UA-0009`, which the earlier reported counts do not indicate on
their face. Running the launcher will produce the definitive classification
with exact table/rowid evidence.

## What remains for the owner (irreducible only)
Based on the known evidence already in this task (VIN, make/model/year,
engine, mileage, fuel), the following fields cannot be derived automatically
and will render as `Уточняется` in the sandbox unless CRM or the existing
sandbox HTML already contains them once the script is actually run:
- transmission
- drivetrain
- color
- price
- stage/status (if not already `draft`/`0` in CRM)

The launcher will report the exact subset still missing after checking CRM
and existing sandbox HTML — the list above is the maximum possible; it may be
shorter once the script runs against real data.

## Why this is not yet marked DONE for publication
- `SAFE_TO_PUBLISH_UA0009_NOW` is hardcoded to `NO` in every code path — this
  is a later CRITICAL, owner-approved action after a green release gate and
  a visual review of the generated sandbox card.
- The release gate status (beyond this one vehicle's duplicate ambiguity) was
  not reported as green in the task input, so no publish step is proposed.

## Next step for ChatGPT / owner
1. Have an authorized operator run
   `python3 cloud/ua0009_task004_launcher.py` on PythonAnywhere.
2. Inspect `/home/Carix/video/ua0009_task004.txt` for the final block and the
   duplicate classification.
3. Visually review
   `/home/Carix/sandbox_ua0009_task004/video/ua0009_task004_card.html` and
   `..._diag.html`.
4. Supply only the fields still listed under `UA0009_OWNER_INPUT_REQUIRED`
   after that run, if any.
5. Publication remains blocked until the release gate is independently
   confirmed green and the owner explicitly approves the CRITICAL publish
   step.
