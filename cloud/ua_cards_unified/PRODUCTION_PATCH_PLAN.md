# PRODUCTION PATCH PLAN — TASK 013 (NOT EXECUTED)

This plan describes the exact bounded change that would be proposed for Gate A execution and Gate B publication. Nothing in this plan has been run against production. No CRM write. No WSGI reload.

## Preconditions before any Gate A execution

1. Read-only confirmation of the actual generator source path and function responsible for `/video/UA-XXXX.html`.
2. Read-only export of current CRM fields feeding that generator (sample of UA-0001..UA-0008 rows only, no bulk PII export).
3. A dedicated backup snapshot of all currently published `/video/UA-*.html` files, taken before any write.

## Allowlist (only these paths may ever be touched by an apply run)

- `/video/UA-XXXX.html` (existing cards only, additive block insertion, not full rewrite)
- `/video/UA-XXXX-diag.html` (new file, safe to create if absent)
- `/video/UA-XXXX-track.html` (new file, safe to create if absent)

No other path, template, CRM table, static asset, or config file is in scope. The generator/template responsible for pricing, photos, descriptions, stages, navigation, analytics, CRM, and chat must not be modified.

## Atomicity and backup procedure (planned, not executed)

1. For each card in scope: compute SHA-256 of the current live file (if it exists) and store in a manifest `before_state.json`.
2. Copy current live file to `backup/<timestamp>/UA-XXXX.html.bak` before any write.
3. Render the new content in memory using the pure functions from `START_UA_CARDS_UNIFIED.py`.
4. Write to a temp file in the same directory, `fsync`, then `os.replace` for atomic swap.
5. Compute SHA-256 of the file immediately after write and store in `after_state.json`.
6. Never touch a card whose current file cannot be read/backed-up successfully; skip and log instead of forcing.

## Rollback procedure

1. If any post-write smoke test fails for any single card, restore that card's `.bak` file via the same atomic replace mechanism.
2. Rollback is per-card, never a full-batch destructive rollback that could regress unrelated already-fixed cards.
3. Keep all backups for a minimum retention window agreed with the owner before any deletion.

## Smoke tests required immediately after any real apply (future task, not this one)

- HTTP 200 for `/video/UA-XXXX.html`, `-diag.html`, `-track.html` for every touched card.
- Exactly one occurrence of each button text on the entry page.
- No `href="#"`/empty/javascript:/data: link present anywhere in the three generated pages.
- Visual smoke check at 390/430/768/1366 px (requires human or automated browser check on PythonAnywhere side, out of scope here).
- Confirm UA-0001..UA-0008 pricing/photos/description/stage sections are byte-identical outside the newly inserted button/link block.

## Gate requirement

This plan may only be executed after:
- Gate A: an explicit, exact-phrase operator authorization tied to a specific commit SHA of this candidate, executed manually and observed, not via this GitHub worker.
- Gate B: a separate exact-phrase owner approval bound to TASK_ID `task_013` and the exact `release_manifest_candidate.json` SHA-256 values as they exist AFTER this candidate is committed (not the early `УТВЕРЖДАЮ ПУБЛИКАЦИЮ` phrase, which predates the final bytes).
