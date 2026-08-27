# FERRY-PHASE1 — Safe wording transform and discovery

Status: READY_FOR_GATE_A_DISCOVERY. This package does not write production,
CRM, cards, generators, schedules, or PythonAnywhere files.

## Result

- Restored the accepted TASK 047 public APIs and all 48 original tests.
- Added structural handling for `chip`, `status-pill`, `etap`, the exact four
  sibling spans `Корея / Море / Грузия / Киев`, bilingual `data-ru` / `data-uk`,
  route headings, and the exact information-page phrase.
- Ordinary prose, longer localized prose, scripts, styles, comments, legacy
  attributes, and tag-looking script strings remain byte-identical.
- Restored fixed `/home/Carix` discovery, verified reads, strict JSON/redaction,
  and real CRM schema support for `cars.auto_number` and `cars.sea_container`.
- Preserved internal stage keys such as `sea`; only user-facing wording changes.

## Verification

Command: `python3 run_tests.py`

- 93 tests per run, two deterministic runs: PASS (75 transform/discovery,
  8 isolated Gate A/controller checks, and 10 bounded generator-context/patch checks).
- Repeated from another current working directory: PASS.
- Exact nine-card sandbox audit: 18 approved replacements, zero ambiguous
  occurrences, every card idempotent, zero changes on a second pass.
- Core-page sandbox audit: 7 approved replacements across index, catalog and
  info; zero ambiguous occurrences; podbor unchanged; all idempotent.

## Safety

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

Next step: read-only Gate A discovery on the exact production registry and
generation of a preview/diff for owner visual approval. No production apply is
authorized by this report.
