# TASK 101 Report — UA-ORDER-GE-8COUNTRY-GUARD-016 v1.1 FINAL

## Canonical memory markers

- `CONTEXT_BUNDLE_SHA256`: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- `MEMORY_VERSION_READ`: `4`

## What was done

Owner authorized (31.08.2026, quoted command) preparation of a full safe implementation PACKAGE for: Georgian language support, 8-country "Авто под заказ" grid (4x2), country-to-5-models routing on `podbor.html`, and a proof-of-preservation mechanism for all 16 catalog cards. Claude produced 10 deliverable files plus this report under `cloud/task_101_ge_8_countries/`, and updated `cloud/latest_status.md` and `cloud/owner_reply.md`. No production, CRM, public site, or PythonAnywhere system was touched, read, or written by Claude — Claude has no execution access to those systems in this task.

## Result summary

- 8/8 country codes defined (korea, japan, usa, europe, china, canada, uae, georgia), matching owner's 4-top/4-bottom order.
- 40/40 models defined exactly per owner list, with USA and UAE stored as independent arrays per owner instruction.
- Georgian (`ka`) localization dictionary skeleton created with ru/uk/ka keys, a controlled ru-fallback policy, and an explicit list of strings requiring native review before Production (review flags stored as metadata, never inline in displayed text).
- `implementation.patch` is delivered as an explicitly labeled **integration template**, not an applicable diff, because the canonical source files (homepage counter template, `i18n.js`, `.countries-inline` block, `podbor.html`, Telegram WebApp handler) are not present as evidence in this task. No exact "before" context lines were invented.
- `card_guard_manifest.schema.json` specifies a BEFORE/AFTER structure covering all 16 cards individually plus a dedicated, separately-gated `UA-0009 SAFE CHECK` entry, consistent with canonical shared-memory record REC-0005 and the still-open `ua0009_safe_to_publish: NO` status.
- `form_bot_contract.md` defines additive-only, backward-compatible extensions for `canada`, `uae`, `georgia` codes, keeps `s`/deep-link contract intact, and explicitly separates the `georgia` **country** selection from the `В Грузии` **delivery stage**, per task requirement.
- `test_matrix.md` and `evidence.json` are honest and PENDING-by-default: no live check, screenshot, or HTTP call was actually performed in this task; nothing is marked VERIFIED unless it was genuinely produced as static content in this package (JSON validity, schema authoring, etc.).

## Risks identified

1. **Missing canonical source evidence** is the single biggest blocker to turning `implementation.patch` into an applicable diff. Without exact file paths and current SHA-256 hashes for the homepage template, `i18n.js`, `.countries-inline` block, `podbor.html`, and the Telegram WebApp handler, no real patch can be safely generated without risking silent corruption of unrelated code.
2. **Homepage hardcode 13** is a known live bug independent of this task's new features; fixing it correctly requires locating (or creating) a single source-of-truth generator shared by the homepage and catalog page — this must not be solved by inserting a new hardcoded number (e.g. 16) as that would repeat the same bug for UA-0017+.
3. **UA-0009 readiness remains unresolved** at the shared-memory level (`ua0009_safe_to_publish: NO`). This task does not change that; it adds a schema-level gate but does not run it.
4. **Georgian text requires native review** before Production; the four control phrases in this package are best-effort translations, not certified.
5. **Namespace collision risk** between `georgia` (country) and `В Грузии` (stage) is real in typical shared-state implementations; the contract explicitly calls this out, but the actual codebase must be checked for any single shared variable currently used for both concepts.

## Exact next safe step for ChatGPT/Codex

1. Independently audit all 10 files under `cloud/task_101_ge_8_countries/` plus `cloud/latest_status.md` and `cloud/owner_reply.md` for completeness, JSON validity, and adherence to the owner's exact country/model lists.
2. If PASS, open a new task ("Sandbox install") that supplies the canonical source file paths and SHA-256 hashes listed in `baseline_audit.md` and `implementation.patch`, so a real, reviewable diff can be produced.
3. That Sandbox task must independently: (a) produce a real BEFORE card-guard manifest against live/production read-only data, (b) apply the patch only in Sandbox, (c) produce a real AFTER manifest, (d) diff BEFORE vs AFTER against `card_guard_manifest.schema.json`, (e) run the UA-0009 SAFE CHECK gate, (f) run the full `test_matrix.md` with real evidence attached.
4. Only after Sandbox PASS + Canary PASS + all-16 regression PASS + a separate explicit written owner command should any Production write be considered, per REC-0004.

## Prerequisites for the Sandbox install task (checklist for Codex)

- [ ] Canonical path + SHA-256 for homepage counter template/generator
- [ ] Canonical path + SHA-256 for `i18n.js`
- [ ] Canonical path + SHA-256 for `.countries-inline` block template
- [ ] Canonical path + SHA-256 for `podbor.html` (or generator)
- [ ] Canonical path + SHA-256 for Telegram WebApp handler / deep-link parser
- [ ] Canonical path for the single source-of-truth catalog count generator (or explicit decision to create one)
- [ ] Read-only production snapshot access to build the real BEFORE card-guard manifest for UA-0001..UA-0016
- [ ] Native Georgian speaker assigned for string review before any Production step
- [ ] Explicit owner written go-ahead for Sandbox execution (separate from this preparation authorization)

## Final status line

`TASK 101 PACKAGE PASS · 16/16 CARD GUARD SPECIFIED · 8/8 COUNTRIES · 40/40 MODELS · RU/UA/GE · PRODUCTION_TOUCHED: NO`
