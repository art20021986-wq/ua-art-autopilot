# UA-ORDER-GE-8COUNTRY-GUARD-016 — Sandbox Package

Spec code: UA-ORDER-GE-8COUNTRY-GUARD-016 (v1.2 FINAL)
Task: task_103
Mode: SANDBOX / PREVIEW ONLY — no production write performed or authorized by this package.

## Purpose

This package prepares (in Sandbox only) the infrastructure required to:

1. Add Georgian (`ka`) as a third interface language alongside Ukrainian (`uk`, default) and Russian (`ru`).
2. Expand "Auto under order" from 5 to 8 countries: Korea, Japan, USA, Europe, China, Canada, UAE, Georgia — arranged 4x2.
3. Provide a single whitelist-based country/model configuration (8 countries × 5 models = 40 total), with UAE stored as an independent array (not a reference/alias to USA, even though the approved model list is currently identical).
5. Provide safety tooling (`sandbox_executor.py`) that guards the existing 16 production cards (UA-0001…UA-0016) from any accidental modification, and that refuses to write to anything resembling a production path.

## Files in this package

| File | Purpose |
|---|---|
| `README.md` | This file. |
| `IMPLEMENTATION_PLAN.md` | Step-by-step plan mapped to the spec sections and Definition of Done. |
| `sandbox_executor.py` | Stdlib-only, fail-closed CLI tool: `--self-test`, `--discover`, `--build-sandbox`, `--validate`, `--report`. Default (no flags) runs `--self-test` and performs no writes. |
| `test_sandbox_executor.py` | Executable unittest suite covering language/country whitelists, default `uk`, 40-model config, UAE independence, routes, KA UTF-8 control strings, unsafe-innerHTML absence, static counters (3+1+8+4=16), production-path deny, sandbox-path guard, manifest comparison, and rollback readiness. |
| `country_models.json` | Canonical whitelist config: 8 countries × 5 owner-approved models each (uk/ru/ka names for countries). |
| `i18n_dictionary_uk_ru_ka.json` | uk/ru/ka dictionary including the four owner-mandated Georgian control strings, country names, and shared UI keys. |
| `BEFORE_AFTER_MANIFEST_SCHEMA.json` | JSON Schema describing the machine manifest fields (ID, VIN, stage, price, photo/video counts, diagnostics, container, media SHA-256) used for BEFORE/AFTER comparison of the 16 cards. |
| `VALIDATION_REPORT.md` | Full evidence report: what ran, what is NOT_RUN/NOT_AVAILABLE, and why. |
| `CHANGED_FILES.md` | Enumeration of every file this task created. Zero existing production/site files were touched. |
| `ROLLBACK_POINT.md` | Description of the rollback point and rollback test procedure. |

## What this package explicitly does NOT do

- It does not connect to, read from, or write to any UA ART production site, CRM, bot, or PythonAnywhere path.
- It does not fabricate Preview URLs, screenshots, or live HTTP 200 results.
- It does not run a runtime translation service; all `ka` strings are static, pre-approved dictionary entries pending native-speaker sign-off per spec section 4.
- It does not modify UA-0001…UA-0016 data, media, or CRM records — no such data was supplied to or accessed by this worker; the card-guard logic operates purely on manifests supplied via `--car-manifest` for testing/demonstration.

## Canonical shared-memory markers

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

Production write remains forbidden (`production_write: NO`, `ua0009_safe_to_publish: NO` per canonical memory) until an explicit, separate owner command authorizes it.
