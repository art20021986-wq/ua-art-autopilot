# UA-ART Universal New-Card Factory Gate — Specification (task_006)

## Purpose

Replace the per-card, per-task technical cycle with ONE reusable, read-only
diagnostic runner that works for UA-0009, UA-0010, and every future UA-XXXX
card without code changes.

The runner never publishes, never writes to the CRM database, never touches
existing cards UA-0001..UA-0008, and never executes production generator
code. It only reads evidence and reports the truth.

## What changed vs task_005 (audit fixes)

1. **Full field mapping.** Columns are discovered dynamically per table by
   alias matching (`FIELD_ALIASES`), not a hardcoded 3-column SELECT.
   Transmission, drivetrain, color, price, etc. are recovered whenever the
   CRM schema exposes them under any recognizable column name.
2. **OBD/diagnostic rule is computed**, not assumed. It looks for non-empty
   diag/obd columns on related rows or a diagnostic-named ready media file.
   If none exists, the CTA is explicitly marked `CTA_NOT_ALLOWED`.
3. **Media is validated**, not assumed. Every candidate file is checked for:
   CRM ready-state, real existence, non-symlink, non-zero size, allowed
   extension, and (for videos) SHA-256 uniqueness against other video
   slots for the same card.
4. **No synthetic-string "tests".** The HTML validation step parses the
   actual newest sandbox HTML discovered on disk for that exact card ID.
   If no such file exists, the tool reports `PREVIEW_STRUCTURE_NOT_PROVEN`
   instead of inventing a placeholder.
5. **Known generator paths are included** as bounded, read-only,
   non-executed static-inspection candidates, plus whatever sandbox HTML is
   actually discovered for the card.
6. **Faithful preview.** The tool copies the real, already-rendered sandbox
   HTML for the card (verbatim, no code execution) into the sandbox factory
   folder as a review copy. If no real sandbox HTML exists, the tool says so
   plainly instead of drawing a fake ASCII table.
7. **Draft vs publication separated.** `VISUAL_DRAFT_MISSING_FIELDS` (identity
   fields: auto_number, vin, brand, model, year) is checked independently
   from `PUBLICATION_MISSING_FIELDS` (every mandatory commercial field). A
   card can be `READY_FOR_VISUAL_CHECK` while publication remains blocked.
8. **Hash limits respected.** Files above 50MB are never hashed; the tool
   reports `NOT_PROVEN_TOO_LARGE` instead of comparing null hashes and
   calling anything "unchanged".
9. **Before/after drift detection.** A bounded set of watched paths
   (generator candidates + files/dirs whose name contains a protected or
   requested card id, in a small fixed list of directories) is hashed
   before and after the run; any addition, removal, or content change is
   reported.
10. **Path containment enforced.** Every file read or written is required to
    resolve (via `os.path.realpath`) inside `/home/Carix`, be a regular file,
    and not be a symlink, before it is trusted or touched.
11. **No hardcoded PASS.** Every PASS/FAIL/NOT_PROVEN value in the report is
    the result of an actual measurement in this run.
12. **Real UTC timestamps** are generated with `datetime.now(timezone.utc)`
    at run time.

## Scope boundaries (hard-coded, unconditional)

- SQLite is opened `mode=ro` with `PRAGMA query_only = ON`. No write
  statement is ever issued.
- The only paths the tool will ever write to are:
  - `/home/Carix/sandbox_uaart_card_factory/<CARD_ID>/video/*`
  - `/home/Carix/video/uaart_card_factory_report.txt`
  - `/home/Carix/video/uaart_card_factory_report.json`
  Every write is boundary-checked against these exact roots, rejects
  symlinks, and is performed atomically (tmp file + fsync + `os.replace`).
- No `subprocess`, `eval`, `exec`, `importlib`, dynamic import, or network
  call exists anywhere in the code.
- Production generator files are only opened in **text read mode** for
  static pattern inspection (looking for hardcoded `UA-0001..UA-0008`-style
  literal ranges). They are never imported or executed.

## Per-card algorithm (applies identically to any UA-XXXX)

1. Validate ID matches `^UA-\d{4}$`.
2. Look up rows in every CRM table that has a column recognizable as
   `auto_number` equal to the ID.
3. If none found → `CARD_NOT_IN_CRM` (does not block other cards).
4. If more than one row found → report exact table/rowid evidence as a
   duplicate classification; continue using the first as primary.
5. Map all whitelisted fields present under any recognized column name.
6. Cross-check VIN against other tables; if the same VIN appears under a
   different auto_number, flag `VIN_CONFLICT_WITH:<other id>` and block for
   safety.
7. Collect media/diagnostic evidence from every row (in any table) whose
   auto_number or VIN column matches this card. Classify each media item as
   ready/pending/rejected/unknown from its own status column.
8. Validate every "ready" media candidate file: existence, non-symlink,
   non-zero size, allowed extension, and (for videos) hash uniqueness.
9. Evaluate the diagnostic CTA rule from real diag/obd column values or a
   diagnostic-named ready media file.
10. Locate the newest sandbox HTML whose filename contains the exact card ID
    under a small fixed set of directories; validate viewport meta, exactly
    one chat block, no duplicate diagnostic CTA, and no empty `src`/`href`.
11. If sandbox HTML exists, copy it verbatim as the faithful review copy and
    hash it 10 times to prove static determinism. If it does not exist,
    report `PREVIEW_STRUCTURE_NOT_PROVEN`.
12. Classify the card as `READY_FOR_VISUAL_CHECK`, `NEEDS_DATA`, or
    `BLOCKED_SAFETY`, and separately report whether every publication field
    is present (informational only — this tool never authorizes
    publication).

## Global safety algorithm

- `PRAGMA quick_check` on the CRM database.
- SHA-256 (or size/mtime fallback with `NOT_PROVEN` when the file is too
  large) of the database file before and after the run.
- Watched-path snapshot before and after the run, covering UA-0001..UA-0008
  named files and the known generator files, to prove nothing outside scope
  changed.
- Static generator inspection for hardcoded `UA-0001..UA-0008`-style
  literal ranges (used as the future-card compatibility signal, since no
  production code is executed).

## Extending to future cards

Run the exact same command with the new card ID(s) as arguments:

```
python3.10 /home/Carix/uaart_card_factory_gate.py UA-0011 UA-0012
```

No code change is required. The algorithm is identical for every card.
