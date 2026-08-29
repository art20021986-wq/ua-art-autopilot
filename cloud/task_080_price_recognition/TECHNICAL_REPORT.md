# TASK 080 — technical report

## Root cause

The active voice route sends a transcript through `local_ocr.fields_from_text`
and `ai_fast_schema.fast_text_data`. The first had no sale-price parser; the
second accepted only colon-labelled text and mapped generic `цена` toward
internal purchase/total fields. The live schema whitelist also omitted
`price_uah`. A separate typed-text path used a narrow price regex and even
treated an arbitrary bare number as a price. The wait path then saved the
price and stage history in separate commits. The screenshoted
`Не распознал поле CRM` response follows directly from that combination.

## Candidate correction

One deterministic parser now handles typed text, successful voice transcripts,
photo captions, and explicit price-field input. It always proposes exactly
`cars.price_uah`, normalizes safe digit and RU/UA word forms, performs no FX
conversion, uses no network/LLM after transcription, and rejects competing or
internal-cost contexts.

The integration candidate changes nine active blocks across `cars_ui.py`,
`local_ocr.py`, `ai_fast_schema.py`, and `ai_filter.py`. It removes the legacy
bare-number/narrow-regex bypass, routes generic labels only to `price_uah`,
preserves the explicit overwrite rule, adds caption parity, makes duplicate
updates silent/idempotent, and fixes the existing undefined `override`
variable in the voice response branch.

`crm_price_atomic.write_price` updates `price_uah`, current-stage
`price_history`, `updated_at`, and one audit row in a single SQLite transaction.
It uses fixed SQL, immutable card identity plus CAS, performs read-back inside
the transaction, and rolls everything back on write, audit, read-back, or
commit failure. Voice undo uses the same writer for price restoration.

## Current and future cards

No per-card migration is needed. The correction is shared runtime code, so once
separately deployed it applies to every existing open card and every future
card. The read-only live audit found 13 current cards with valid positive sale
prices and no duplicate numbers, so no existing value was invented, replaced,
or backfilled.

## Verification

- `56/56 PASS` deterministic sandbox/canary tests.
- Fresh GET-only Gate A matched all complete source and active-block hashes.
- Nine transformed active blocks compiled in memory.
- Candidate evidence status:
  `PASS_IN_MEMORY_CANDIDATE / READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
- Production, database, site, and process mutation: `NO`.

## Release boundary

This is a verified release candidate, not a claim that the live bot is fixed.
Installing files and reloading the Telegram process are Gate B operations and
require a separate explicit owner approval.
