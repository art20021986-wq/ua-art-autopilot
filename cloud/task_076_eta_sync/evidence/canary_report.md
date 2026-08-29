# Canary report — TASK 076 (OFFLINE / SYNTHETIC — NOT LIVE)

## Scope

This report covers the offline, synthetic canary exercised against
`fixtures/mock_crm.py` and `fixtures/mock_publisher.py`, simulating the
reported UA-0009/UA-0010/UA-0011 state (11 days / 2026-09-09 for all three,
with UA-0009's/UA-0011's `updated_at` matching the reported page-refresh
times) and then submitting `days=30` for each through
`EtaSyncController.submit()`.

**This is not a run against the real CRM or the real live site.** No
production system was contacted. `production_write=0`, `crm_write=0` for
this report, consistent with canonical shared memory
(`CURRENT_STATUS.production_write="NO"`, `crm_write="NO"`).

## Expected outcome when the offline suite is executed

`python3 cloud/task_076_eta_sync/run_tests.py` is expected to discover and
run the following test modules:

- `tests/test_eta_engine.py` — validation, computation, priority resolution,
  consistency check, description sanitation.
- `tests/test_eta_transaction.py` — happy path, boundary days (0, 1, 30,
  400), invalid days (-1, 401, 5000), injected failures (DB partial write,
  read-back mismatch, queue timeout, publisher failure, rebuild-card
  failure, delayed-rebuild protection), and a protected-row check for
  UA-0001.
- `tests/test_regression_synthetic.py` — the three-card scenario producing
  one consistent 30-day date, the UA-0010 timeout-and-retry scenario, stale
  description removal for all three descriptions, and two consecutive
  deterministic runs producing the same date.

## Two consecutive deterministic canary runs

`test_two_consecutive_deterministic_canary_runs_match` demonstrates that
computing a 30-day ETA from a given base date, and computing it again from
a base date shifted back by exactly 30 days from the first result, yields
the identical `eta_manual` date — i.e. the computation is deterministic and
reproducible, a prerequisite for "two consecutive deterministic canary
runs" matching in a real sandbox/canary environment.

## Verdict

This offline package is submitted as **code + tests only**. Per the
established project pattern (see canonical memory REC-0013 for TASK 021:
"controller independently verified... 41 of 41... in each of 10 complete
suite runs"), the authoritative pass/fail record for this suite should be
produced by an independent controller execution, not self-reported by this
delivery. Until that independent execution is recorded in canonical shared
memory, this canary result is **informational**, not a verified PASS.

Memory markers (must be echoed unchanged):
- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4
