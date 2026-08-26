# UA-0009 — Conditional Publication Plan (documentation only)

This file is documentation, not an executable patch. It will only be acted on
after every gate below passes and the owner gives a separate, explicit
CRITICAL approval. Nothing here authorizes any write to production now.

## Required gates, in order

1. `cloud/ua0009_finish_runner.py` produces a live report with:
   `SAFE_FOR_OWNER_VISUAL_REVIEW: YES` and no FAIL/NOT_PROVEN on
   `SQLITE_QUICK_CHECK`, `DATABASE_UNCHANGED`, `UA0001_0008_UNCHANGED`,
   `PROTECTED_SHARED_FILES_UNCHANGED`, `HTML_VALIDATION`,
   `SANDBOX_10_RUNS`, `UA0010_SYNTHETIC_NEW_CARD_TEST`.
2. Owner supplies only the fields still listed in
   `UA0009_OWNER_INPUT_REQUIRED` from that report (e.g. transmission,
   drivetrain, color, price, status) — nothing else is re-asked.
3. Owner opens the sandbox card/diagnostics pages and replies an explicit
   **YES** (not silence, not "looks fine probably").
4. A **separate** production payload is generated from the exact verified
   sandbox output of step 1 — never from an ad-hoc rebuild.
5. Before that payload may be applied: a fresh crm.db backup exists, an
   explicit file whitelist for this publish is produced and reviewed,
   a rollback rehearsal is performed in a scratch copy, automated checks
   pass, and a fresh before/after diff shows zero unexpected changes
   outside the whitelist.
6. Owner gives one separate, explicit **APPROVE PUBLISH UA-0009** command.
   This is the one CRITICAL action gate; nothing before this step touches
   production.
7. Atomic publication is performed (single commit/replace, not partial
   file-by-file), followed immediately by HTTP status, mobile, desktop,
   catalog listing, card page, and diagnostics-page checks.
8. Any single FAIL in step 7 triggers immediate rollback to the pre-publish
   backup and a STOP report; no partial/half-published state is left live.

## Smallest expected production whitelist

- CRM row(s) for UA-0009 identified by the exact `table`/`rowid` from the
  live duplicate-evidence report — `TO_BE_RESOLVED_FROM_LIVE_REPORT`.
- The production card HTML/template path for UA-0009 — `TO_BE_RESOLVED_FROM_LIVE_REPORT`
  (only provable once the generator/source location is confirmed in the
  live report; not guessed here).
- Any catalog/listing index file that enumerates published cars, if such a
  file exists — `TO_BE_RESOLVED_FROM_LIVE_REPORT`.

No path is asserted beyond what the live report can prove. Guessing paths
here would risk an unsafe publish whitelist later, which this plan
explicitly forbids.
