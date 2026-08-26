# Cloud Report — task_003 (UA-0009 Release Gate)

## Scope executed

This task was executed entirely within the `cloud/` repository, in READ_ONLY
mode, with **no access to PythonAnywhere production** from this environment.
Deliverables are a self-contained, tolerant, read-only probe script plus
supporting documentation. The probe has NOT yet been run against real
production data — that must happen on PythonAnywhere per the owner's next
step.

## What was produced

1. **`cloud/ua0009_release_probe.py`**
   - stdlib-only (sqlite3, os, re, hashlib, datetime, traceback) Python 3.10
     script.
   - Opens `crm.db` only via `sqlite3.connect("file:...?mode=ro", uri=True)`.
   - Reads `PRAGMA quick_check;` and `PRAGMA journal_mode;` (read-only pragma
     forms — no `=` assignment, so no journal mode change occurs).
   - Scans `stroy3.py` / `stranica.py` as **plain text** (never imported) for:
     - `busy_timeout` configuration mentions,
     - connect()/close()/SELECT-fetch call counts,
     - textual evidence that long external operations (requests, sleep,
       subprocess, moviepy/ffmpeg, PIL, urlopen) appear between a `connect()`
       and its next `close()` in the source — the concrete signal the owner
       asked for regarding connection-lifetime risk.
   - Produces a `SQLITE_RELEASE_RECOMMENDATION` of `TARGETED_FIX`,
     `WAL_CANDIDATE`, or `MORE_PROOF_NEEDED` using explicit, documented logic
     (see spec doc) — it does **not** guess; if paths can't be resolved it
     honestly reports `MORE_PROOF_NEEDED`.
   - Locates the UA-0009 record by trying `auto_number` variants
     (`UA-0009`, `UA0009`, `0009`, `9`) against a heuristically-identified
     vehicle table (chosen by column-name-pattern scoring across all tables
     in `sqlite_master`), so it does not hardcode a wrong table name.
   - Classifies every required field into `PRESENT` / `MISSING` /
     `OWNER_INPUT_REQUIRED` / `CAN_DERIVE_SAFELY_FROM_EXISTING_UA0009_DATA`.
   - Counts VIN and auto_number duplicates by direct COUNT(*) queries
     (read-only) scoped to the matched value only.
   - For sandbox readiness: walks a bounded set of candidate public/static
     directories (depth-limited, file-count-limited) looking for filenames
     containing `UA-0001`..`UA-0008` and `UA-0009` variants, computing SHA-256
     for files under 25MB (larger files reported as `SKIPPED_TOO_LARGE` with
     size, never trunc-hashed silently).
   - Never prints secrets/tokens/blobs: media/list fields are reduced to
     counts + basenames; any value that looks like a large base64 blob is
     replaced with a placeholder string.
   - The **only** filesystem write anywhere in the script is the single
     output file `/home/Carix/video/ua0009_release_gate.txt` (plus creating
     its parent directory if missing). No database write, no site file write.
   - Ends with the exact mandatory final block format required by the task,
     always fixing `SAFE_TO_PUBLISH_UA0009_NOW: NO`, `PRODUCTION_WRITE_PERFORMED: NO`,
     `DATABASE_CHANGED: NO`, `SITE_FILES_CHANGED: 0`.

2. **`cloud/ua0009_release_report_spec.md`** — full specification of every
   report field/section and how to interpret `SAFE_TO_*` flags, plus an
   explicit **verification boundary** statement: all concrete findings are
   only real once the probe is executed on PythonAnywhere.

3. **This report.**

## Self-test performed by Cloud (static-check only)

Since this environment has no `crm.db`, no `stroy3.py`/`stranica.py`, and no
PythonAnywhere filesystem, Cloud performed the following **static** checks
only (no production access implied or claimed):

- Reviewed the script for `py_compile`-level syntax correctness by manual
  review of all function bodies, brackets, and indentation (Python 3.10
  syntax; f-strings, `match` not used, no walrus-dependent edge cases).
- Verified no import of `stroy3`, `stranica`, Flask, Django, or any
  application-layer module — only `os, re, sys, sqlite3, hashlib, traceback,
  datetime`.
- Verified every `sqlite3.connect(...)` call in the probe passes
  `uri=True` together with a `file:...?mode=ro` string — grepped manually,
  two call sites, both correct.
- Verified no `PRAGMA journal_mode = ...` (assignment) string appears
  anywhere — only `PRAGMA journal_mode;` (read) and `PRAGMA quick_check;`
  (read).
- Verified no `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` SQL
  keywords appear anywhere in the script.
- Verified the only `open(..., "w")` / `os.makedirs(...)` call targets
  `OUTPUT_PATH` / its parent directory; all other `open()` calls are
  `"r"` (read) mode on source files.
- Verified duplicate-count queries are scoped with `WHERE col = ?` using the
  already-matched value (not a full-table dump), and results are counts only.
- Verified media-field formatting never returns raw bytes/blobs — bytes
  objects are replaced with a `<binary N bytes - not printed>` placeholder,
  and long base64-looking strings are replaced with a placeholder.

> **What Cloud explicitly could NOT verify from this environment:** whether
> any of the `DB_CANDIDATES`, `SOURCE_CANDIDATES`, or
> `PUBLIC_DIR_CANDIDATES` paths actually exist on PythonAnywhere, whether the
> guessed vehicle table/column names match the real schema, and therefore
> whether UA-0009 will actually be found. These are stated as open items for
> the next execution round, per the task's own acceptance criterion:
> "production paths are only verified after PythonAnywhere executes the
> probe."

## Recommended next step (for ChatGPT / owner, not performed here)

1. Run `python3 ua0009_release_probe.py` in a PythonAnywhere bash console.
2. If any `*_CANDIDATES` list resolved to `NONE_FOUND`, tell Cloud the real
   path(s) so the script can be corrected (still read-only) — no code needs
   re-authoring for this, only the candidate lists.
3. Return the contents of `/home/Carix/video/ua0009_release_gate.txt`.
4. Cloud/ChatGPT then classify: (a) SQLite fix task scope, (b) which
   `OWNER_INPUT_REQUIRED` UA-0009 fields need to be collected from the owner,
   (c) sandbox build task scope — as separate, smaller tasks, each following
   the same read-only-first, CRITICAL-approval-for-writes discipline.

## Hard prohibitions honored

- No production writes performed or proposed.
- No INSERT/UPDATE/DELETE anywhere in the deliverable.
- No journal_mode assignment/WAL switch performed.
- No restart triggered or requested.
- No publication/regeneration performed.
- No import of UA ART modules.
- No direct UPDATE of UA-0009.
- No copying of data from another vehicle into UA-0009's classification.
