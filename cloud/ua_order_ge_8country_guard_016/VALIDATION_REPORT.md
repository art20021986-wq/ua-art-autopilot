# VALIDATION_REPORT — task_103 / UA-ORDER-GE-8COUNTRY-GUARD-016

Context markers (canonical shared memory, unmodified):
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## 1. Files prepared and their purpose

| File | Purpose | Status |
|---|---|---|
| README.md | Package overview | CREATED |
| IMPLEMENTATION_PLAN.md | Section-by-section plan mapped to spec | CREATED |
| sandbox_executor.py | Fail-closed CLI (self-test/discover/build-sandbox/validate/report) | CREATED, self-test PASS (offline) |
| test_sandbox_executor.py | Offline unittest suite | CREATED |
| country_models.json | 8 countries × 5 models whitelist config | CREATED, PASS against internal validator |
| i18n_dictionary_uk_ru_ka.json | uk/ru/ka dictionary incl. 4 KA control strings | CREATED, PASS against internal validator |
| BEFORE_AFTER_MANIFEST_SCHEMA.json | Manifest schema for BEFORE/AFTER card diffing | CREATED |
| CHANGED_FILES.md | Enumeration of all created files | CREATED |
| ROLLBACK_POINT.md | Rollback description/procedure | CREATED |

## 2. Preview links UA/RU/GE

**NOT_AVAILABLE.** No Sandbox/Preview hosting endpoint was provided to or reachable by this worker in this round. No URL is claimed.

## 3. Preview links for 8 countries

**NOT_AVAILABLE** — same reason as above. Route strings are proven correct by unit test (`build_route`) for all 8 whitelisted country codes, e.g. `podbor.html?strana=canada&lang=ka`, but no live URL exists to click.

## 4. Table of 40 models

| Country | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Korea | Kia K5 | Hyundai Sonata | Hyundai Tucson | Kia Sportage | Hyundai Santa Fe |
| Japan | Nissan Note | Toyota Aqua | Mercedes-Benz B-Class | Toyota Prius | Раритетні авто 1980–1990-х років |
| USA | Tesla Model Y | Tesla Model 3 | Ford Escape | Nissan Rogue | BMW X3 |
| Europe | Volkswagen Golf | Volkswagen Tiguan | Audi Q5 | Škoda Octavia | Renault Megane |
| China | BYD Song Plus | Volkswagen ID.4 | BYD Yuan Plus (Atto 3) | Zeekr 001 | BYD Seal |
| Canada | Lexus RX 350 | Lexus RX 500 | Lexus TX | Toyota Tacoma TRD Pro | Toyota Tacoma Trailhunter |
| UAE | Tesla Model Y | Tesla Model 3 | Ford Escape | Nissan Rogue | BMW X3 |
| Georgia | Ford Fusion / Fusion Hybrid | Toyota Camry | Volkswagen Jetta | Toyota RAV4 / RAV4 Hybrid | Subaru Forester |

Source: `country_models.json`, verified by `test_country_models_config` tests (5 models/country, 40 total, UAE array object-distinct from USA). **STATUS: PASS (offline config validation only).**

## 5. Screenshots / visual evidence

**NOT_RUN.** No browser or Preview environment was available to this worker. UI grid requirements (4×2 layout, 44px targets, hover/focus/active states, no horizontal scroll at 360/375/390/430/768/1024/1440px, no WhatsApp overlap, Georgian Mkhedruli rendering) require an actual rendering environment and remain explicitly NOT_RUN.

## 6. 16/16 HTTP 200 and UA-0009 SAFE CHECK

**NOT_RUN.** No live site endpoint was reachable. The guard logic (`validate_card_baseline`, stage counters 3/1/8/4, UA-0009 presence) is implemented and proven correct against synthetic manifests only (`TestCardBaseline`, `TestManifestComparison`). Running it against the real 16-card dataset requires a real manifest supplied via `--car-manifest`, which was not available in this round.

Per canonical shared memory: `ua0009_safe_to_publish: NO`. This task does not change or contest that status; it does not touch UA-0009 or any other live card.

## 7. BEFORE/AFTER counters

- Expected baseline (per spec, hard-coded in `sandbox_executor.EXPECTED_STAGE_COUNTS`): Kyiv 3, Georgia 1, On the ferry 8, Korea 4, total 16.
- No live BEFORE snapshot was taken because no production source was reachable. **STATUS: NOT_AVAILABLE.**
- The arithmetic and duplicate-detection logic itself is unit-tested and PASS against synthetic 16-card fixtures.

## 8. SHA-256

**NOT_RUN.** No real media files were accessible to this worker to hash. `sha256_of_file()` is implemented and available for use once real media paths in an isolated sandbox copy are supplied.

## 9. WhatsApp, Telegram, WebApp, CRM

- Contract fields (`country_code`, localized country name, model, budget, type, text/link, language, `source`/URL) are documented in the implementation plan and reflected in the i18n/config structure.
- New start-param codes `z_canada`, `z_uae`, `z_georgia` are specified in `IMPLEMENTATION_PLAN.md` as additions alongside the existing `start=z_country` contract; no existing codes were altered.
- End-to-end checks (Safari/Chrome → WhatsApp, Telegram WebApp `sendData`, Telegram link fallback, single CRM lead without duplicate, correct country/model, UTF-8 Georgian) are **NOT_RUN** — no live WhatsApp/Telegram/CRM endpoint or mock harness target was available to exercise in this round. CRM writes remain forbidden regardless.

## 10. Limitations of this round

1. No access to the real production/Sandbox copy of the site, catalog, cards, i18n files, podbor page, or lead-submission handler was available to this worker.
2. No browser/Preview rendering environment was available; all UI/visual acceptance criteria are NOT_RUN.
3. No live CRM/WhatsApp/Telegram endpoints were available for contract testing; only the data contract is documented.
4. Georgian strings still require native-speaker sign-off before Production per spec Section 4 (external gate, not attempted here).

## 11. Rollback point

See `ROLLBACK_POINT.md`. No production or existing repository file was modified; rollback is trivial (delete/ignore the `cloud/ua_order_ge_8country_guard_016/` directory) since nothing outside `cloud/` was touched.

## 12. Final line

Because live/Preview checks (Sections 5, 6, 7, 8, 9, 11 of this report) are NOT_RUN / NOT_AVAILABLE, the honest final status per spec Section "Финальный отчёт" is:

**SANDBOX PACKAGE READY · LIVE/PREVIEW CHECKS PENDING · PRODUCTION WRITE: NO**
