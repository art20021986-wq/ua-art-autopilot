# TASK 080 — CRM-PRICE-RECOGNITION-006 v1.0 — Technical Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Root cause (per prior evidence + this task's design review)
1. `cars_ui.catch_message` routes both typed text and voice-transcribed text
   through `local_ocr.fields_from_text` and `ai_fast_schema.fast_text_data`.
2. `local_ocr.fields_from_text` has no sale-price parser at all.
3. `ai_fast_schema.labeled_text_data` only understands strict `label: value`
   lines and, even when it does match a price-like label, it maps generic
   `цена`/`стоимость` wording onto `price_total`/`price_buy` — internal cost
   fields — never onto `price_uah`, which is the field `cars_ui` actually
   displays and edits as "Цена продажи".
4. Because of (2) and (3), natural phrasing such as
   `Стоимость автомобиля 11 400 долларов` matches nothing usable and the
   message falls through to the "Не распознал поле CRM" branch, for both
   voice and typed text.
5. A second legacy text-only regex path exists, narrower still, so voice and
   text do not share one canonical parser — violating the parity requirement.

## Fix design delivered in this round
- `src/price_parser.py`: one pure, deterministic function
  `parse_sale_price_message(text, in_price_uah_wait)` used by every input
  path (typed, voice transcript, caption, explicit price_uah field). It:
  - recognizes the required sale-price phrasings in RU/UA;
  - normalizes NBSP, space/comma/dot thousand grouping, `тыс`/`k` decimal
    suffixes, and a RU/UA number-word lexicon;
  - always targets `price_uah` and never `price_total`/`price_buy`/
    `cost_total`/`cost_purchase`;
  - fails closed on ambiguous currency/amount, competing amounts, and any
    competing internal-cost / year / mileage / engine / VIN / ETA /
    container wording;
  - accepts bare digits only when `in_price_uah_wait` is True;
  - exposes `is_explicit_change_intent` so the caller can apply the existing
    fill-vs-overwrite rule without re-implementing intent detection.
- `src/patcher.py`: a narrow, hash-gated integration tool that will only
  ever apply the wiring patch once given genuine live Gate A SHA-256
  anchors for the whole file and the specific active function being
  replaced, with an explicit duplicate-definition check. With no hashes
  supplied (this round), it always fails closed.

## What was NOT done in this round, and why
- No live GET of `cars_ui.py`, `local_ocr.py`, `ai_fast_schema.py`,
  `ai_filter.py`, or the active price writer was performed: this delivery
  channel has no network/tool access to the CRM host.
- No SHA-256 anchors of live code were computed, so no in-memory patch was
  constructed against real files — only the parser and patcher candidates
  were authored.
- No read-only audit of existing cards for duplicate IDs / invalid or
  missing sale prices was performed, for the same reason.
- No pytest run of `tests/test_price_parser.py` was executed by an actual
  interpreter in this channel; `TEST_RESULTS.md` records a manual
  desk-check trace instead and asks the controller to execute the real
  suite.
- No atomic price writer contract was verified as currently active; this
  remains an explicit open dependency per rule #8 of the task.

## Result
`FAIL_CLOSED_NO_LIVE_GATE_A_ACCESS_IN_THIS_DELIVERY_CHANNEL`

This is not a claim that the CRM defect is fixed. It is a prepared,
self-contained candidate (parser + hash-gated patcher + tests + rollback
plan) that is ready for a controller with live GET access to complete Gate A
and execute the real test suite, after which a separately authorized Gate B
can be requested. Production, crm.db, the public site, and the Telegram
process were not touched in any way during this task.
