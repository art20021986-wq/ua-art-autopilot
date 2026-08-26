# Task 006 report — Universal New-Card Factory Gate

## What was delivered

- `cloud/uaart_card_factory_gate.py` — one Python 3.10 stdlib-only,
  read-only runner that replaces the per-card technical-task cycle. It
  processes any number of UA-XXXX card IDs (default UA-0009 and UA-0010)
  independently and reports, per card:
  - `READY_FOR_VISUAL_CHECK`, `NEEDS_DATA` (with exact missing fields), or
    `BLOCKED_SAFETY` (with exact reason).
- `cloud/uaart_card_factory_spec.md` — full technical specification and
  explicit mapping from every task_005 audit defect to the fix applied.
- `cloud/uaart_card_factory_morning.md` — five-step, one-screen operator
  instructions requiring no GitHub/SQLite/generator knowledge.

## How the task_005 defects were corrected

1. Full dynamic column mapping (`FIELD_ALIASES`) replaces the 3-column
   hardcoded SELECT — transmission, drivetrain, color, price, etc. are now
   recovered whenever present under any recognizable column name.
2. The OBD/diagnostic CTA rule is computed from real diag/obd columns and
   diagnostic-named ready media; it is never hardcoded to PASS.
3. Media is genuinely validated: CRM ready-state, existence, non-symlink,
   non-zero size, allowed extension, and SHA-256 uniqueness across video
   slots.
4. The compatibility test inspects the real, newest sandbox HTML discovered
   for the exact card ID on disk; if none exists it reports
   `PREVIEW_STRUCTURE_NOT_PROVEN` rather than a synthetic string test.
5. The known generator candidate paths (`stranica.py`, `yadro.py`,
   `master_card.py`, `stroy3.py`, `stroy8.py`, `mysite/stranica.py`,
   `mysite/master_card.py`) are included as bounded, read-only, never-
   executed static-inspection candidates, plus whatever sandbox HTML is
   actually found.
6. The "preview" is now a verbatim copy of the real rendered sandbox HTML
   (no fabricated text table), written only under the approved sandbox
   factory folder.
7. Visual-draft requirements (`VISUAL_DRAFT_REQUIRED_FIELDS`) are now
   separated from publication requirements
   (`PUBLICATION_REQUIRED_FIELDS`); a card can be shown as
   `READY_FOR_VISUAL_CHECK` with publication still blocked on missing
   commercial fields.
8. Files above 50MB are never hashed — the tool reports
   `NOT_PROVEN_TOO_LARGE` instead of silently treating two null hashes as
   "unchanged".
9. Watched paths (protected cards + generator files) are re-discovered
   after processing and diffed against the pre-run snapshot to detect
   additions/removals/modifications.
10. Every path used for reading or writing must resolve under
    `/home/Carix`, be a regular file, and not be a symlink, or it is
    rejected outright.
11. No measured validation result is hardcoded; every PASS/FAIL/NOT_PROVEN
    reflects an actual check performed during the run.
12. Timestamps are generated with `datetime.now(timezone.utc)` at run time.

## Boundaries respected

- SQLite opened `mode=ro` with `PRAGMA query_only = ON`; no write statement
  is ever issued against `crm.db`.
- The only writable paths are the sandbox factory `video/` subfolders per
  requested card ID and the two report files; every write is
  boundary-checked, non-symlink, atomic (tmpfile + fsync + `os.replace`).
- No subprocess, eval/exec, dynamic import, or network call exists in the
  code.
- No production module is imported; production generator files are only
  opened in text mode for static pattern inspection.
- No CRM row, existing card (UA-0001..UA-0008), or production file is
  modified. No publication occurs.

## Verification performed in this round

- The Python file is syntactically self-consistent and intended to pass
  `python3.10 -m py_compile` on the GitHub worker.
- Logic was reviewed against every numbered defect in the task and against
  the required per-card and global report field lists; all are emitted.
- UA-0009 and UA-0010 are processed independently in the loop; a missing
  UA-0010 CRM row produces `CARD_NOT_IN_CRM` for that card only and does not
  affect UA-0009's result.

## What ChatGPT / owner should check next

1. Run the five-step morning instruction on PythonAnywhere.
2. Review `/home/Carix/video/uaart_card_factory_report.txt` for the actual
   UA-0009 and UA-0010 status lines.
3. If UA-0009 shows `READY_FOR_VISUAL_CHECK`, perform the visual check on
   the review copy under
   `/home/Carix/sandbox_uaart_card_factory/UA-0009/video/review_copy.html`
   and, only after a manual YES, request the separate CRITICAL publication
   approval step (not part of this task).
4. If UA-0010 shows `CARD_NOT_IN_CRM` or `NEEDS_DATA`, add the exact missing
   CRM fields/media in the CRM and re-run the same command — no code change
   needed.

No production writes, CRM changes, or publications were performed in this
task.
