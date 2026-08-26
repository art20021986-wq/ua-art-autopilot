# UA-0009 FINISH RUNNER — SPEC (task_005)

This document explains the design of `cloud/ua0009_finish_runner.py` and how it
satisfies every hardening requirement from task_005. It supersedes the
task_004 prototype, which is NOT reused as-is.

## 1. Write boundary

Only two locations may ever be written:

- `/home/Carix/sandbox_ua0009_finish/video/*` (sandbox card + diagnostics preview)
- `/home/Carix/video/ua0009_finish_report.txt` and `.json` (exact filenames only)

Every write goes through `assert_writable_target()` which:

- resolves the real path (`os.path.realpath`) and requires it to be inside one
  of the two allowed roots (exact match or root + separator prefix),
- walks every path component from target to filesystem root and refuses if
  any component is a symlink,
- refuses to overwrite anything that is not a plain regular file.

All writes use `atomic_write_bytes/text`: write to a temp file in the same
directory, `flush()`, `os.fsync()`, then `os.replace()` onto the final name.
This guarantees no partial/corrupt file is ever visible under the final name.

## 2. CRM access

`crm.db` is opened with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`
followed by `PRAGMA query_only=ON`. The only statements ever executed are:

- `PRAGMA quick_check`
- `PRAGMA table_info("<validated_identifier>")`
- `SELECT rowid, <validated_columns> FROM "<validated_table>" WHERE ... = ?`
  with values passed as bound parameters, never string-interpolated.

Table/column identifiers are validated against `^[A-Za-z_][A-Za-z0-9_]*$`
before being quoted and used; values (UA-0009, VIN) are always passed as
bound parameters. No INSERT/UPDATE/DELETE/DDL statement exists anywhere in
the code.

Only minimal, non-PII columns are ever selected: the matched auto_number /
vin / published / status-like columns and `rowid`. No customer name, phone,
price negotiation notes, or other PII columns are read.

## 3. Duplicate classification

All tables are scanned; for each, columns that look like `auto_number` or
`vin` are located and a bound-parameter SELECT is issued. Results are
classified:

- no rows -> `MORE_PROOF_NEEDED` (blocks)
- single table, single rowid, one row -> `NO_DUPLICATION_SINGLE_ROW`
- single table, single rowid, duplicate SELECT rows -> `SAME_ROW_COUNTING_ARTIFACT`
- single table, multiple distinct rowids -> `TRUE_DUPLICATE` (blocks)
- multiple tables -> `MULTI_TABLE_REFERENCE_NOT_DUPLICATE`

`TRUE_DUPLICATE` and `MORE_PROOF_NEEDED` always set
`SAFE_FOR_OWNER_VISUAL_REVIEW = NO`.

## 4. Field recovery

Only UA-0009's own matched rows contribute values; nothing is copied from
UA-0001..UA-0008. Known confirmed facts (auto_number, VIN, make, model,
year, fuel, engine, mileage) are pre-seeded from the owner-confirmed facts in
the task. Missing fields (transmission, drivetrain, color, price, status)
are auto-detected as missing and marked `Уточняется`, and listed in
`UA0009_OWNER_INPUT_REQUIRED`. `UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE` is
`NO` whenever any of those remain unresolved — it is never a hardcoded
constant.

## 5. Protected-file re-discovery

Protected files are *not* limited to filenames containing "UA-0001".."UA-0008".
The runner first looks for `/home/Carix/video/release_gate_manifest.json`
(an explicit, owner/ChatGPT-maintained whitelist of shared protected files).
If that manifest is absent, it falls back to a single, non-recursive listing
of `/home/Carix/video` filtered to UA-0001..UA-0008 filenames, and honestly
records `PROTECTED_SHARED_FILES_UNCHANGED = NOT_PROVEN` when no manifest and
no matching files were found, rather than claiming PASS.

Before/after manifests capture existence, symlink status, size, mtime, and
sha256 (bounded to 64MB files to keep the job light). The comparison detects
modifications, additions, deletions — not just "file still there".
`crm.db` is included in this same before/after comparison and hashed too, so
`DATABASE_UNCHANGED` is evidence-based, never asserted blindly.

## 6. New-card compatibility (Phase C)

- The generator source (if found at one of a short, explicit candidate list)
  is read as **text only** — never imported, never executed — and scanned for
  patterns suggesting a hardcoded 1–8 range.
- A synthetic `UA-0010` record is built using the exact same pure rendering
  function used for UA-0009, proving the fix is not special-cased.
- If no generator source can be found, the runner does **not** claim PASS;
  it marks `generator_not_hardlimited` false and this feeds into
  `SAFE_FOR_OWNER_VISUAL_REVIEW = NO` with an explicit reason.

## 7. Sandbox determinism (Phase D)

The sandbox HTML is produced by a pure function of the recovered fields
(no wall-clock timestamps, no random IDs in the markup). It is rendered 10
times and compared via normalized SHA-256; only 10/10 identical hashes pass.
All field values are passed through `html.escape()` before insertion. No
untrusted seed HTML is ever opened as an executable page — this runner does
not read or serve any pre-existing HTML file as a preview; it only renders
from escaped CRM-recovered text.

The diagnostics section is included **only** if real UA-0009-specific OBD
evidence was found; since the safe column-selection deliberately does not
fetch speculative OBD columns (to avoid over-broad reads / PII risk), the
current implementation conservatively omits diagnostics and records this
honestly in the report rather than fabricating a report or link.

## 8. Faithful preview limitation (rule 13)

This runner cannot safely prove a byte-faithful copy of the current
production template without reading production generator/template code,
which is only inspected as text if present. If the generator cannot be
located, the sandbox is still produced (clearly marked SANDBOX ONLY /
DO NOT PUBLISH) but `SAFE_FOR_OWNER_VISUAL_REVIEW` is forced to `NO` and the
exact blocker ("generator source not found") is written into the report.

## 9. Forbidden operations — verified absent

Grep-level self-check performed during authoring; the script contains no
`subprocess`, `os.system`, `shell=True`, `eval(`, `exec(`, `socket`,
`urllib`, `requests`, WSGI reload calls, or dynamic `importlib` of any
production module.

## 10. CPU guard

An optional file `/home/Carix/video/cpu_limit_signal.txt` may contain a
percentage. If present and >= 85, the runner stops immediately with
`DEFERRED_CPU_LIMIT` and writes only the two allowed report files. If
absent, it proceeds and reports `CPU_LIMIT_NOT_PROVEN` internally rather than
inventing a PASS.
