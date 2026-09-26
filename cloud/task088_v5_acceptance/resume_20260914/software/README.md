# PR 114: resumed software evidence, 2026-09-14

The 443 previously recorded unique offline checks were reproduced successfully
against candidate commit `e146c2ea8c28033050b49ccbebb33aa5276c8788`.
This is software and captured-source evidence, not live Preview, live CRM,
Production authorization, deployment, or Stage 4 acceptance.

| Suite | Tests | Failures | Errors | Skips |
| --- | ---: | ---: | ---: | ---: |
| Public price protection | 348 | 0 | 0 | 0 |
| Private captured-source fixtures | 95 | 0 | 0 | 0 |
| Unique target checks | 443 | 0 | 0 | 0 |

All expected-failure and unexpected-success counts are also zero. The current
unmodified `cloud/ua_ge_price_protection/gate.py` independently completed PASS
for its 348 tests. These duplicate public executions are not added to the 443
unique checks. The seven separate workflow-contract failure events are recorded
under `workflow/`; none is hidden or treated as PASS by this report.

## Binding and capture integrity

The 82-entry source inventory exactly matches the historical candidate:
`18fc3c2ffb16df204cdd7318f550fbffa0a2169da3be57ff0d2bc88b1855b5c7`.
All source hashes remained unchanged throughout this test run.

The existing private routing capture was found at the exact path recorded in
`CONTINUATION_20260914_108_BROWSER_CASES.json`. Its manifest hash is
`80caa235053ad81550415b162060f4d77661967fc8ed97fb4fef0d5aff87db7b`.
All 65 recorded files matched their manifest hashes before and after execution.
The capture contains 18 published records and seven explicitly recorded missing
legacy resources. These are historical capture properties, not fresh server
observations. Preview capture tests correctly keep the incomplete offline build
at `NOT_PASSED`; they do not manufacture its missing media or linked pages.

Private source content and CRM records were not copied into this evidence.
Test application credentials were not inherited. Test writes occurred only in
temporary local fixtures; no browser, live server, CRM or Production action was
performed by this software workstream.

## Evidence files

- `software_checks_final.json`: corrected evaluation of all 28 per-file runs.
- `raw/`: original stdout/stderr and machine-readable per-file test results.
- `source_binding.json`: exact candidate/source and historical-report binding.
- `capture_integrity_before.json`, `capture_integrity_after.json`: all recorded
  capture hashes and unchanged-state verification.
- `workflow/actual_price_gate.json`, `workflow/actual_price_gate.log`: actual
  unmodified public gate execution.
- `workflow/`: separate workflow-contract reproduction and diagnosis.
- `reproduce_historical.py`: test coordinator, with corrected expected counts.

The initial coordinator transposed the expected counts of two private test
files: `test_private_source.py` has 11 and `test_captured_pages.py` has 6.
Both actual runs passed, and the combined historical count was correct.
`historical_443_results.json` preserves the initial coordinator's honest FAIL
on that bookkeeping mismatch. `software_checks_final.json` records the exact
correction and the original report hash. No actual failed test was removed,
no source/test expectation was changed, and no rerun was needed to correct
this report mapping.

## Gates this workstream does not close

The installer's 24 required Preview categories still need actual observations:
all published cars, home, catalog, full cards, RU/UA/GE, language switching,
UA/GE prices, missing GE, desktop/mobile, links, buttons, VIN, photos,
specifications, additional specification, stages, counters, protected unrelated
content, source generation, and independent DB readback. Browser and live-server
workstreams must supply their own evidence; this folder makes no claim about
their current completion.

The final Preview contract must bind the exact task, candidate manifest,
published codes, independent DB hashes, schema, system inventory and current
source files. Its observations must be no older than 30 minutes when the
verifier runs. Gate B, writer exclusion, fresh quota/inventory, verified complete
backup, exact canonical request/claim/transaction/authorization binding,
Production postchecks, persistent authenticated control reading, real repeated
CRM price updates and operator receipts remain separate operational gates.
Previously closed Stage 1 and Stage 2 were not reinstalled.
