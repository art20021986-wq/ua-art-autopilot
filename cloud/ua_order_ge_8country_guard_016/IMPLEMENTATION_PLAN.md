# Implementation Plan — task_103 / UA-ORDER-GE-8COUNTRY-GUARD-016

## 0. Constraints acknowledged

- Sandbox/Preview only. No Production write authorized (`PRODUCTION_WRITE_AUTHORIZED: NO`).
- No access was granted in this worker's environment to the real UA ART production repository, CRM, bot, or PythonAnywhere filesystem. Therefore steps that require reading the live source of truth (baseline discovery of 16 cards, HTTP 200 checks, Preview URLs, screenshots) are marked **NOT_AVAILABLE / NOT_RUN** rather than fabricated, per the mandatory honesty rule.
- All deliverables are new files under `cloud/`; nothing under a production path was read or modified.

## 1. Source-of-truth identification (Section 2)

Required before any modification: identify source of truth for homepage, catalog, cards, i18n, podbor, car/stage reference data, and the lead-submission handler; take a BEFORE snapshot; build a machine manifest (ID, VIN, stage, price, photo/video counts, diagnostics, container, media SHA-256).

**Status: NOT_AVAILABLE.** This worker has no live connection to production source files. `sandbox_executor.py --discover` is implemented to perform this exact validation (16 cards, 3/1/8/4 stage split, uniqueness) against a manifest file supplied via `--car-manifest`, but no real manifest was provided to this task. Running discovery against real data is the required next action before any further Sandbox build proceeds, per spec Section 2 ("If baseline not 16 and 3/1/8/4 — BLOCKED, no automatic modification").

## 2. Language rollout (Section 4)

- `sandbox_executor.normalize_lang()` implements the whitelist (`uk`, `ru`, `ka`), forbids `ge` as a language code, defaults to `uk` for missing/unknown/no-localStorage cases, and is covered by tests.
- `i18n_dictionary_uk_ru_ka.json` carries the four owner-mandated Georgian control strings verbatim plus country names and shared UI keys for uk/ru/ka.
- Native-speaker review of Georgian strings before Production remains an **external gate**, explicitly not claimed as passed here.

## 3. Country grid 4×2 and routing (Section 5)

- `COUNTRY_WHITELIST` = korea, japan, usa, europe, china, canada, uae, georgia (order matches spec table row-major 4×2).
- `build_route(country, lang)` produces `podbor.html?strana=<code>&lang=<lang>` for all 8 codes, always carrying the current language, with unknown country falling back to `korea`.
- Visual grid requirements (equal height, 44px targets, no horizontal scroll at 360–1440px, no WhatsApp overlap) are UI/CSS concerns outside this Python package's scope; they are listed as required manual/automated UI checks in `VALIDATION_REPORT.md` and marked NOT_RUN because no browser/Preview environment was available to this worker.

## 4. Country → 5-model config (Section 6)

- `country_models.json` encodes the exact owner-approved table: 8 countries × 5 models = 40 entries.
- UAE is stored as its own JSON array, structurally guaranteed to not be the same object/reference as USA's array (`test_uae_independent_of_usa`), even though the approved model names are currently identical to USA's per the spec table.
- "Other model" free-text field is preserved as a dictionary key (`other_model`) in the i18n file, not removed from any UI logic (UI logic itself is not in this Python package's scope; the field must simply not be dropped by whoever wires the form).

## 5. WhatsApp / Telegram / WebApp / CRM contract (Section 7)

- Not exercised end-to-end here (no live WhatsApp/Telegram/CRM endpoints reachable from this worker). The manifest/config produced (`country_code`, localized name, model, budget, type, language) is structured to be consumable by the existing lead-submission handler once wired by the site codebase, without requiring changes to the old contract (`start=z_country` plus new `z_canada`, `z_uae`, `z_georgia`).
- CRM writes remain forbidden. A mock/fixture-based contract test is recommended as the next implementation step once the actual handler code is made available to this worker; **status: NOT_RUN** in this round.

## 6. Static counters (Section 8)

- `EXPECTED_STAGE_COUNTS` = kyiv:3, georgia:1, on_ferry:8, korea:4, sum 16, matching the spec's mandatory baseline. `validate_card_baseline()` and `compute_stage_counters()` implement and test this arithmetic against any supplied manifest.

## 7. Card protection (Section 9)

- `build_manifest_entry()` and `compare_manifests()` implement the BEFORE/AFTER diffing logic: any change to VIN, price, stage, container, photo/video counts, diagnostics count, or media SHA-256 for any card ID is flagged as an unexpected diff (FAIL condition per spec).
- No real BEFORE snapshot exists in this worker's environment, so no AFTER comparison against live data was performed; `compare_manifests` is proven correct via synthetic unit tests only.

## 8. Safe implementation guardrails (Section 10)

- `is_production_path()` / `assert_safe_sandbox_root()` enforce: sandbox root must not equal, must not nest inside, and must not itself resemble (via denylist markers) a production path. `--build-sandbox` refuses to run without an explicit `--sandbox-root` and refuses unsafe roots.
- No use of `innerHTML` or `eval()` anywhere in `sandbox_executor.py` (tested).
- Idempotent: `--build-sandbox` only ever writes vetted config JSON copies into `<sandbox_root>/config/`.

## 9. UI/QA (Section 11) and Definition of Done (Section 12)

See `VALIDATION_REPORT.md` for the full checklist with explicit PASS / NOT_RUN / NOT_AVAILABLE status per line item. No item is marked PASS without machine-verifiable evidence produced in this task.

## Next round recommendation for ChatGPT/Codex

1. Provide (or point this worker to, inside an isolated non-production copy) the actual homepage/catalog/card/i18n/podbor source files and a real 16-card manifest so `--discover` and `--validate` can run against real data.
2. Provide a Sandbox/Preview hosting target (a non-production URL) so the 8 country routes and 3-language switch can be exercised with real HTTP 200 checks and screenshots.
3. Only after both of the above produce PASS evidence should Production-write be considered, and only under a separate, explicit owner command per spec Section 12 item 21.
