# TASK 080 — Backup / Rollback Plan (prepared, not executed)

## Pre-conditions before any Gate B attempt
1. Controller performs live Gate A GET of `cars_ui.py`, `local_ocr.py`,
   `ai_fast_schema.py`, `ai_filter.py`, and the active price-writer module,
   and records whole-file + active-function SHA-256 for each.
2. Controller takes a full byte-for-byte backup copy of each of those files
   plus a full `crm.db` backup (file-level copy, not a live write) timestamped
   before any change.
3. Controller feeds the recorded hashes into
   `cloud/task_080_price_recognition/src/patcher.py` as the `expected_hashes`
   manifest. `patcher.run()` must return `ALL_TARGETS_VERIFIED_PATCH_ELIGIBLE`
   before any patch content is applied.

## Patch shape (candidate, to be finalized only after Gate A hashes exist)
- Add `price_parser.py` (this file, unchanged) as a new module imported by
  `cars_ui.py` and `local_ocr.py`.
- Replace the narrow regex path in `local_ocr.fields_from_text` and the
  colon-label price mapping in `ai_fast_schema.labeled_text_data` with a
  single call to `price_parser.parse_sale_price_message(text, in_price_uah_wait=...)`.
- The caller in `cars_ui.catch_message` must call this once per message
  (typed or voice-transcribed), and only proceed to the atomic writer when
  `result.ok` is True.
- The write itself must go through whatever safe atomic writer contract is
  currently active in the live CRM (sale price + price history + audit in
  one bounded commit). If Gate A discovers that no such atomic writer is
  active, and only the legacy `update_card_field -> remember_price` double
  commit path exists, this task must report that dependency and stop —
  it must NOT silently reuse the legacy locking path (per task rule #8).

## Rollback plan
- Because no live file has been modified in this round, there is nothing to
  roll back yet.
- For the eventual Gate B round: keep the pre-patch backup copies of every
  touched file and a `crm.db` snapshot. If any canary check fails post-patch
  (duplicate write, wrong field written, missing history/audit row, wrong
  auto_number in the read-back), restore the exact backed-up file bytes and
  restart only the process that was reloaded for the canary, per the
  owner's existing controlled-reload procedure. No schema change is part of
  this task, so no migration rollback is needed.

## Explicit non-actions in this round
- No production file was written.
- No crm.db row was written.
- No Telegram process was reloaded.
- No card was created or duplicated.
- No Gate B was executed.
