# Frozen gallery candidate: fresh offline acceptance

The actual unmodified software gate, every private captured-source suite and
the required maintenance discovery were rerun against the gallery fix.

| Scope | Result |
| --- | --- |
| Current public software gate | 351/351 PASS |
| All private captured-source tests | 95/95 PASS |
| Combined price software checks | 446/446 PASS |
| Required maintenance discovery | 183/183 PASS |

All failures, errors, skips, expected failures and unexpected successes in the
price suites are zero. Maintenance returned exact `OK`, with no failures,
errors or skips. Test counts were observed from actual results, not forced to
match expectations. The three added public gallery regressions account for
the change from the historical 443 to the current 446 price checks.

Builder SHA256:
`0137d0077ef485679feea238b579b629f8c281542ca28a7277b769d5a7b8fa02`

Current source manifest SHA256:
`eab94e62b58e95a3a6c219a4a9a206cfdb8eda4b1192deb107f358358b8da5f7`

Source hashes were unchanged throughout the run. The existing private routing
capture's 65 recorded files matched their manifest hashes before and after;
private source bytes and CRM rows were not copied into these artifacts. The
capture manifest remains
`80caa235053ad81550415b162060f4d77661967fc8ed97fb4fef0d5aff87db7b`.

This folder contains offline software/captured-source results. It does not
claim fresh server data, browser acceptance, real CRM operations, Production
publication or Stage 4 completion. The historical 443 report remains unchanged
and applies to its earlier source manifest.

`PUBLIC_GATE.json` and the raw gate logs show the actual current gate run.
`raw/private_*.json` and corresponding logs preserve all eight private suites.
`MAINTENANCE.json` and its raw logs preserve the actual required discovery.
`SOURCE_BINDING_BEFORE.json` and `FINAL_CURRENT_CANDIDATE_RESULTS.json` record
exact source binding, all command results and unchanged-input verification.
`run_current_candidate.py` records the coordinator used. All subprocesses
received stripped environments and disposable temporary fixture storage.
