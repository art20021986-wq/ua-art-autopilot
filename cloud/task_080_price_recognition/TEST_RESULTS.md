# TASK 080 — Independent parser test results

## Controller run

Date: 2026-08-29 UTC  
Runner: Codex controller, local Python interpreter  
Command shape: import the test module and execute every callable named `test_*` (the runtime did not include pytest; no dependency was installed).

## First run — rejected

Result: `26/28 PASS`.

Two defects were found independently:

1. `измени цену на 12000` returned `NO_SALE_PRICE_INTENT` because the parser accepted only nominative `цена`, not the grammatical form `цену`.
2. `стоимость таможни 500` was incorrectly accepted as a vehicle sale price because the blocker matched `таможен...` but not `таможни`.

This first candidate was not accepted.

## Corrected run

The parser was narrowed/extended to:

- recognize Russian and Ukrainian grammatical forms of sale-price labels;
- block every `тамож...` / `митн...` internal-cost form;
- reject negative numeric amounts, including `минус`, `мінус`, and minus-sign variants;
- preserve the canonical target field `price_uah`.

Additional regression tests were added for those cases.

Literal result:

```text
RESULT 30/30 PASS
```

Exit code: `0`.

Coverage includes all eight required owner formats, RU/UA number words, NBSP and grouped separators, `11,4 тыс.`, `11.4k`, explicit price-wait bare digits, inflected price commands, negative/zero/overflow, competing amounts, protected year/mileage/engine/ETA/container contexts, internal purchase/logistics/customs costs, explicit overwrite intent, canonical `price_uah`, and the deterministic performance bound.

## Remaining gate

This proves the standalone parser only. Live Gate A, exact hash-gated integration, current-card read-only audit, and verification of the atomic price writer are still required. Production/CRM/site/process writes remain `NO`.
