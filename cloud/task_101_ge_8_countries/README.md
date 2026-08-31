# TASK 101 — UA-ORDER-GE-8COUNTRY-GUARD-016 v1.1 FINAL

## Owner authorization

Owner (Артём Бровинский) approved on 31.08.2026 with the phrase «Запускай в работу и ставь в очередь, загрузи файл». This authorizes Claude to PREPARE a full safe implementation package for:

1. Adding Georgian (`ka`) as a third interface language, UI label `GE`.
2. Expanding the "Авто под заказ" block from 5 to 8 countries in a strict 4-top / 4-bottom grid.
3. Wiring each country to its 5 approved top models on `podbor.html`.
4. Proving preservation of all 16 catalog cards UA-0001…UA-0016.

## Explicit scope boundary

- PRODUCTION WRITE: NO
- CRM WRITE: NO
- PUBLIC SITE WRITE: NO
- PYTHONANYWHERE WRITE/RELOAD: NO
- SERVICES RELOADED: NO

All work in this task lives exclusively under `cloud/task_101_ge_8_countries/`. Nothing in this package is applied to any live system. The package is a proposal for independent ChatGPT/Codex audit, followed (only after PASS and a separate written owner command) by a controlled Sandbox → Canary → all-16 gate → Production sequence.

## Package map

| File | Purpose |
|---|---|
| `baseline_audit.md` | Reconciliation of known live facts vs. missing evidence |
| `countries_models.json` | 8 countries, ru/uk/ka names, flags, 5 models each (USA/UAE separate arrays) |
| `localization_dictionary.json` | ru/uk/ka dictionary skeleton with fallback contract and native-review metadata |
| `implementation.patch` | Fail-closed patch proposal template for canonical source/template/config only |
| `form_bot_contract.md` | Country/query/lang/state/payload/deep-link contract, backward compatible |
| `card_guard_manifest.schema.json` | JSON Schema for BEFORE/AFTER 16-card integrity manifest |
| `test_matrix.md` | Full RU/UA/GE × 8-country × device test matrix |
| `evidence.json` | Factual VERIFIED/PENDING status, all safety booleans false until real execution |
| `report.md` | Result, risks, exact next safe step for ChatGPT/Codex |

## Canonical memory markers (must not be altered)

- `CONTEXT_BUNDLE_SHA256`: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- `MEMORY_VERSION_READ`: `4`

## Binding OWNER_DIRECTIVE constraints respected

- REC-0004: Production-write access remains behind the owner-bound Gate B; never granted by this package.
- REC-0005: UA-0009 publication readiness must be verified via Gate A evidence before any publish; this task does not claim that verification.
- `ua0009_safe_to_publish` remains `NO` per canonical shared memory; this package includes a dedicated `UA-0009 SAFE CHECK` gate in the card guard manifest and does not assert PASS for it.

## Final status line for this package

`TASK 101 PACKAGE PASS · 16/16 CARD GUARD SPECIFIED · 8/8 COUNTRIES · 40/40 MODELS · RU/UA/GE · PRODUCTION_TOUCHED: NO`
