# Form / Bot / CRM Contract Proposal — TASK 101

Status: PROPOSAL ONLY. No bot, CRM, or PythonAnywhere code is modified by this task. This document defines the contract a future Sandbox task must implement and test before any Production change.

## 1. Country codes

Whitelist (exactly 8, stable, lowercase, ASCII):

`korea, japan, usa, europe, china, canada, uae, georgia`

- `canada`, `uae`, `georgia` are NEW additions in this task.
- The other 5 codes are UNCHANGED from current production behavior.
- Any code outside this whitelist must safely resolve to `korea` (unchanged fallback rule).

## 2. Namespace separation: country vs. delivery stage

- `georgia` as a **country** selection (`strana=georgia`) refers only to the country-of-origin pool of models for the order-form flow on `podbor.html`.
- `В Грузии` / "in Georgia" as a **delivery stage** on the catalog refers to a car's physical logistics stage and is a completely separate state variable/enum in the catalog pipeline.
- These two concepts MUST use distinct field names in any shared payload, e.g. `order_country` vs. `catalog_stage`, and must never be read from or written to the same key.

## 3. Query parameters (podbor.html)

- `strana` — one of the 8 whitelisted codes. Missing/invalid → `korea`.
- `lang` — one of `ru`, `uk`, `ka`. Missing/invalid → `ru` (existing default rule, extended with `ka`).
- Existing params (budget, type, free-text) are preserved unchanged in name and semantics.

## 4. Client-side state

- `selectedCountry` (order_country) is independent of any `selectedStage` used elsewhere in the app.
- Changing `selectedCountry` must NOT reset already-entered `budget`, `type`, or free-text fields.
- Changing `selectedCountry` must repopulate exactly 5 model options for that country from the source-of-truth `countries_models.json` equivalent.
- "Другая модель / Інша модель / სხვა მოდელი" (other model) free-text field remains available regardless of country and is passed exactly once in the final payload (never duplicated with the selected model).

## 5. Submission payload (Telegram WebApp)

Existing fields (UNCHANGED contract):

- `s` — country code field (existing behavior extended to accept `canada`, `uae`, `georgia` in addition to the 5 existing codes).
- model, budget, type, free-text description — unchanged field names and semantics.

New/extended fields proposed (additive only, no removal or rename of existing fields):

- `lang` — one of `ru`, `uk`, `ka` (extends existing `ru`/`uk`-only acceptance).
- `country_label` — the localized country display name in the current `lang`, for human-readable CRM/Telegram display alongside the stable `s` code.

## 6. Deep-link contract

- Existing pattern `z_<country>` is preserved.
- New deep-links to support: `z_canada`, `z_uae`, `z_georgia`.
- Parser must accept all 8 codes and must not break on any previously working `z_korea`, `z_japan`, `z_usa`, `z_europe`, `z_china` link.

## 7. Duplicate-submission prevention

- One submission = one CRM entry, unchanged existing idempotency mechanism (e.g. existing submit-lock / one-shot token) must be reused, not reimplemented, so behavior for existing countries is unaffected.

## 8. Encoding

- All Georgian (`ka`) text in the payload must be transmitted as UTF-8 without truncation; the bot/CRM ingestion layer must be verified (in the future Sandbox task) to store and display multi-byte UTF-8 Georgian text intact, not just ASCII-safe strings.

## 9. Backward compatibility summary

| Aspect | Old behavior | New behavior | Compatible? |
|---|---|---|---|
| Country whitelist | 5 codes | 8 codes (5 old + 3 new) | YES — old codes untouched |
| Fallback country | korea | korea | YES — unchanged |
| Language whitelist | ru, uk | ru, uk, ka | YES — old langs untouched |
| Default language | ru | ru | YES — unchanged |
| Deep-link pattern | z_<country> | z_<country> (+3 new values) | YES — pattern unchanged |
| Payload field `s` | 5 values | 8 values | YES — additive |
| Payload field `lang` | ru/uk only | ru/uk/ka | YES — additive |

## 10. What this task explicitly does NOT do

- Does not modify the live bot code.
- Does not modify CRM schema or CRM data.
- Does not deploy or reload any service.
- Does not test against a live Telegram bot or live CRM instance.
