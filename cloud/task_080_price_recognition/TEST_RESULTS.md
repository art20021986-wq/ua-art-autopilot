# TASK 080 — verified test results

## Result

- Local independent runner: `56/56 PASS`, exit code `0`.
- GitHub Actions candidate Gate A: `PASS_IN_MEMORY_CANDIDATE`.
- Fresh live whole-file hashes: all matched.
- Fresh active-block hashes: all matched.
- In-memory changed blocks compiled: `9/9`.
- Production, CRM DB, site, and process writes: `NO`.

The dependency-free runner executes every callable named `test_*` in the
three test modules. The same runner is a required step before the live-source
candidate gate; the candidate evidence commit could only run after that step
returned zero.

## Defects caught during independent review

The first parser candidate was rejected at `26/28 PASS` because it did not
recognize the grammatical command `измени цену` and accepted
`стоимость таможни 500`. Both defects were fixed and kept as regressions.

## Covered behavior

- all eight owner formats in typed/voice-transcript parity;
- RU/UA number words, English `price`, NBSP, grouped separators,
  `11,4 тыс.`, `11.4k`, and explicit price-wait input;
- generic price labels target only `cars.price_uah`, never an internal cost;
- negative, zero, overflow, multiple amounts, mixed currencies, year,
  mileage, engine, ETA, container, purchase, logistics, and customs rejection;
- empty fill, filled-field refusal, explicit overwrite, idempotence, undo;
- price + stage history + exactly one audit row in one transaction;
- injected audit and read-back failures roll back all three changes;
- stale CAS, immutable `auto_number`, and two-card concurrency isolation;
- all 13 current cards plus a synthetic future card use the same writer;
- typed text, photo caption, and voice-transcript integration use the shared
  parser; a duplicate Telegram update produces no second write or message;
- no active card asks the owner to open one and performs zero writes;
- old bare-number and narrow-regex price routes are disabled;
- active integration patch refuses source drift and compiles only after exact
  whole-file and function/assignment SHA matches.

## Live read-only audit

The current database snapshot contains 13 cards (`UA-0001`…`UA-0013`):
no duplicate `auto_number`, no missing/empty/non-positive/non-numeric
`price_uah`, and `PRAGMA quick_check=ok`. Existing prices were not changed or
backfilled.

## Release state

`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`. The live CRM is not yet changed.
