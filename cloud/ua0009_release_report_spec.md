# UA-0009 Release Gate Probe — Report Specification

This document specifies the structure and interpretation of the output produced by
`cloud/ua0009_release_probe.py` when executed on PythonAnywhere. It also states
explicitly which facts are **only verified after real execution** on production,
since this task (task_003) is a cloud, read-only, non-executing authoring task.

## IMPORTANT — verification boundary

Cloud/Claude cannot access the PythonAnywhere filesystem or `crm.db` from this
repository. Every production path, table name, column name, and file location
referenced in the probe script is a **candidate** based on naming conventions
stated in prior tasks/reports. The probe is written to be tolerant of wrong
candidates (it logs `PATH_NOT_FOUND` / `NONE_FOUND` rather than failing), but:

> **All concrete findings (journal_mode, quick_check, UA-0009 field values,
> file existence, hashes) are only true and verified once ChatGPT/owner runs
> the probe on PythonAnywhere and returns `/home/Carix/video/ua0009_release_gate.txt`.**

If any candidate path is wrong, update the `*_CANDIDATES` lists at the top of
the script (still read-only) and re-run.

## Report sections (in file order)

1. **Header** — timestamp (UTC), mode statement.
2. **TRACK 1: SQLITE STABILITY DECISION**
   - `DB_PATH_USED` — resolved crm.db path (or `NONE_FOUND`).
   - `QUICK_CHECK` — result of `PRAGMA quick_check;` (`ok` expected if healthy).
   - `JOURNAL_MODE` — result of `PRAGMA journal_mode;` read (no assignment made).
   - Per source file (`stroy3.py`, `stranica.py`):
     - `*_busy_timeout_hits` — regex matches for `busy_timeout` config in source text.
     - `*_connect_calls` / `*_close_calls` / `*_select_or_fetch_calls` — counts of
       `sqlite3.connect(`, `.close()`, and SELECT/fetch calls found in source text.
     - `*_long_ops_while_connection_may_be_open` — textual evidence that a
       network/subprocess/media call appears between a `connect()` and its next
       `close()`, i.e. the connection/cursor may be held open during long work.
   - `SQLITE_RECOMMENDATION` + `SQLITE_RECOMMENDATION_REASON` — decision logic:
     - `MORE_PROOF_NEEDED` if source/DB paths could not be resolved or opened.
     - `WAL_CANDIDATE` if long-operation-while-connected pattern found AND no
       busy_timeout configured (targeted close alone is judged insufficiently
       robust).
     - `TARGETED_FIX` if the same pattern is found but busy_timeout IS already
       configured (closing the reader before long work is likely sufficient).
     - `MORE_PROOF_NEEDED` otherwise (no clear pattern — needs runtime log
       review, not just static text scan).

3. **TRACK 2: UA-0009 CRM COMPLETENESS**
   - `TABLES_FOUND` — all tables in `crm.db`.
   - `CANDIDATE_TABLE` / `TABLE_CONFIDENCE_SCORE` — table guessed to hold vehicle
     records, and how many of the 16 tracked field-name patterns matched its
     columns.
   - `COLUMN_MAPPING` — field → actual column name mapping used.
   - `UA0009_EXISTS` — whether a row matched `auto_number` variant
     (`UA-0009` / `UA0009` / `0009` / `9`).
   - `UA0009_MATCHED_BY` — which column/value found the row.
   - `FIELD[<name>]` lines for each of: auto_number, vin, make, model, year,
     mileage, engine, fuel, transmission, drivetrain, color, price, stage,
     published, photos, videos, diagnostic. Each line states:
     - `classification` — one of `PRESENT`, `MISSING`, `MISSING_COLUMN_NOT_FOUND`,
       `OWNER_INPUT_REQUIRED`, `CAN_DERIVE_SAFELY_FROM_EXISTING_UA0009_DATA`.
     - `value` — safe representation (counts/filenames for media fields, plain
       value otherwise, truncated at 300 chars, never a blob/base64 payload).
   - `VIN_DUPLICATES` / `AUTO_NUMBER_DUPLICATES` — counts of other rows sharing
     the same VIN / auto_number as UA-0009 (0 = no duplicates).

4. **TRACK 3: UA-0009 SANDBOX READINESS**
   - `PUBLIC_DIRS_FOUND` — resolved public/static directories.
   - `BASELINE[UA-000N]_FILE_COUNT` / `BASELINE[UA-000N]_FILE` — bounded file
     listing + SHA-256 for each existing UA-0001..UA-0008 public file (files
     larger than 25MB are marked `SKIPPED_TOO_LARGE` rather than hashed, to
     bound run time; this is a safety bound, not a data omission risk since
     size is still reported).
   - `UA0009_PUBLIC_FILE_COUNT` / `UA0009_PUBLIC_FILE` — any existing UA-0009
     public files found under the same directories.
   - `*_GENERATOR_EVIDENCE` — textual markers (e.g. `TEMPLATE`, `STATIC_ROOT`,
     `def generate_card`, `render_template`) found in `stroy3.py`/`stranica.py`
     indicating where/how cards are actually built, without importing or
     executing those modules.
   - `SANDBOX_BUILD_PREREQUISITES` and `RELEASE_ACCEPTANCE_GATES` — fixed
     checklists (see script) that must all be satisfied before any sandbox
     build or production publish.

5. **FINAL MANDATORY BLOCK** — exact machine-parsable key/value lines as
   required by task_003, always ending with `SAFE_TO_PUBLISH_UA0009_NOW: NO`,
   `PRODUCTION_WRITE_PERFORMED: NO`, `DATABASE_CHANGED: NO`,
   `SITE_FILES_CHANGED: 0`, since this probe never writes to the database or
   any site file other than its own report.

## How to read `SAFE_TO_*` flags

- `SAFE_TO_PREPARE_FIX_TASK: YES` — the SQLite evidence is strong enough that a
  follow-up task can be scoped (either targeted-close patch or WAL migration
  plan) for owner review. This does NOT authorize applying the fix.
- `SAFE_TO_BUILD_UA0009_SANDBOX_NEXT: YES` — CRM data for UA-0009 is complete
  with no duplicates, so a sandbox (non-production) card build can be planned.
  This does NOT authorize touching production files.
- `SAFE_TO_PUBLISH_UA0009_NOW` is hardcoded `NO` and must remain so until a
  separate task with explicit owner CRITICAL approval is executed after
  sandbox visual review.

## Non-goals of this probe

- Does not change `journal_mode`.
- Does not run any INSERT/UPDATE/DELETE.
- Does not import `stroy3`/`stranica` or any Flask/Django app object.
- Does not copy any field value from another vehicle into UA-0009.
- Does not build or write any sandbox/public file.
