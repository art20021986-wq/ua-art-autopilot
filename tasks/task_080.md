# TASK 080 — CRM-PRICE-RECOGNITION-006 v1.0

OWNER_DIRECTIVE: `CRM не разбирает стоимость автомобиля ни голосом, ни текстом. Исправить для всех текущих и будущих карточек автоматически.`

## Scope and safety

- Mode: focused GET-only audit -> BACKUP design -> SANDBOX/CANARY -> release candidate.
- Production, crm.db, public site, Telegram process reload, and Gate B writes are forbidden.
- Runtime LLM tokens for field extraction: exactly 0. Use deterministic parsing only.
- Keep this task focused; do not re-audit unrelated CRM/site subsystems.
- Do not interrupt, replace, or regenerate TASK 077/078/079 outputs.
- Do not create or duplicate any card. An update is allowed only for the explicitly open card resolved by immutable integer `cars.id` / `auto_number`.
- Do not invent or backfill missing historical prices. Existing values remain unchanged unless the owner supplies an explicit price for that card.

## Proven defect

Evidence in `cloud/task_065/evidence/voice_path.json` shows:

1. `cars_ui.catch_message` sends active-card voice text through
   `local_ocr.fields_from_text` and `ai_fast_schema.fast_text_data`.
2. `local_ocr.fields_from_text` has no sale-price parser.
3. `ai_fast_schema.labeled_text_data` only accepts colon-labelled lines and maps
   generic `цена` to `price_total/price_buy`, while the real CRM sale-price
   field used by `cars_ui` is `price_uah`.
4. Therefore phrases such as `Стоимость автомобиля 11 400 долларов` can reach
   the “Не распознал поле CRM” branch shown by the owner.
5. A second legacy text path has its own narrow regex, so voice and text do not
   share one canonical parser.

These anchors are evidence only. Gate A must GET the fresh live
`cars_ui.py`, `local_ocr.py`, `ai_fast_schema.py`, `ai_filter.py`, and
the active price writer before building a patch. Record whole-file and active
function SHA-256 values. Refuse to patch on any mismatch or duplicate active
definition.

## Required behavior

1. Build one shared deterministic function for typed text, voice transcript,
   photo caption, and explicit price-field input. All paths must return the same
   normalized result.
2. Canonical public sale-price target is exactly `cars.price_uah` (the current
   live CRM field labelled “Цена продажи”). Generic phrases
   `цена`, `стоимость`, `стоимость автомобиля`, `цена машины`,
   `ціна`, `вартість авто`, and equivalent sale-price wording must never
   write `price_total`, `price_buy`, `cost_total`, `cost_purchase`, or
   any other internal cost field.
3. Accept safe owner formats, including:
   - `Стоимость автомобиля 11 400 долларов`
   - `цена машины 11400 $`
   - `цена авто: 11 400 USD`
   - `ціна авто 11 400 доларів`
   - `стоимость авто одиннадцать тысяч четыреста долларов`
   - `ціна авто одинадцять тисяч чотириста доларів`
   - `цена 11,4 тыс. долларов` / `11.4k USD`
   - bare digits only while the explicit UI wait field is already
     `price_uah`.
4. Normalize spaces/NBSP, common thousand separators, decimal-thousand suffixes,
   and supported Russian/Ukrainian number words. Store one positive integer.
   Do not convert currencies and do not infer an exchange rate.
5. Outside an explicit `price_uah` wait, require clear sale-price intent.
   A year, mileage, engine size, VIN fragment, ETA, container number, purchase
   cost, logistics cost, customs cost, or arbitrary bare number must not become
   the sale price. Ambiguous currency or multiple competing amounts must fail
   closed with one clear retry message.
6. Both an explicitly typed instruction and a successful voice transcription
   must use this same parser. Text and voice parity is mandatory.
7. Existing open-card rules remain:
   - no active card -> ask to open a card; zero writes;
   - empty price -> fill it;
   - filled price -> overwrite only when the message contains explicit change
     intent such as `измени/исправь/замени/поменяй/скорректируй` or the user
     is inside the explicit price edit UI;
   - duplicate Telegram update -> no second write/history entry/message.
8. Price persistence must follow the current safe atomic writer contract:
   sale price + price history + audit in one bounded operation and exactly one
   logical commit. Do not reintroduce the old
   `update_card_field -> remember_price` double/triple-commit path. If the
   required safe writer is not active, report the dependency and prepare an
   integration candidate; do not silently use a known locking path.
9. After a verified write, read back the same `cars.id`, show the recognized
   value and immutable `auto_number`, and emit exactly one success response.
   On parsing/write/read-back failure: zero partial change and one concise
   failure response.
10. The fix is global code, not per-card data: it must work immediately for
    every existing card and every future card. Include a read-only audit of all
    current cards for duplicate IDs and invalid/missing sale prices, but never
    replace an existing price without explicit source data.
11. Preserve every unrelated field, photos, videos, VIN, description, status,
    ETA, container, publication state, design, and card count byte/row
    semantically. Site publication is outside this task.
12. Keep interaction fast: deterministic parse target <=50 ms; no network and
    no AI call after voice transcription.

## Mandatory sandbox/canary tests

- The eight required formats above in typed and voice-transcript modes.
- Russian and Ukrainian number words, NBSP, `11 400`, `11,400`,
  `11.400`, `11,4 тыс`, and `11.4k`.
- Existing cards UA-0001 through the highest current `auto_number`, plus a
  newly created synthetic future card, all through the same function.
- Empty-field fill, protected non-price fields, explicit overwrite,
  non-explicit overwrite refusal, undo/idempotent duplicate handling.
- No active card -> zero writes and no new card.
- Negative/zero/overflow, two competing amounts, year-only, mileage-only,
  engine-only, ETA-only, container-only, and internal-cost wording -> reject.
- Exact assertion that generic sale-price wording writes only `price_uah`.
- Exactly one price-history entry and one audit entry on success; injected
  lock/write/read-back failure -> rollback/no partial data/no traceback.
- Concurrent requests for two different card IDs do not cross-write.
- In-memory patch compiles only against the freshly audited function/file
  hashes and fails closed otherwise.
- Regression: price display, existing text fields, photo intake, voice
  watchdog semantics from TASK 078, and card count remain unchanged.

## Deliverables

Create `cloud/task_080_price_recognition/` containing:

- sanitized live GET audit and exact SHA/function anchors;
- shared deterministic price parser;
- narrow fail-closed integration patcher;
- sandbox/canary tests and literal test results;
- backup/rollback and prepared manual Gate B plan;
- concise technical report explaining the root cause and coverage for current
  and future cards.

Also update `cloud/latest_status.md` and `cloud/owner_reply.md` in the
mandatory repository format.

The result may be only:

- `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`, or
- a precise `FAIL_CLOSED_...` / dependency blocker.

Never claim the live CRM is fixed until a later separately authorized Gate B
has completed with postcheck evidence.
