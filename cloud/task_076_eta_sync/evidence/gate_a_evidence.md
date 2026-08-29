# Gate A evidence — TASK 076

## Status: NOT_EXECUTED (no live/CRM access from this Claude/Cloud sandbox)

This delivery environment has:
- no network path to the PythonAnywhere host,
- no SSH/API credentials for read-only access,
- no copy of the real `crm.db`, `cars_ui.py`, `db.py`, `konteyner.py`,
  `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py`,
- no ability to fetch the live UA-0009/UA-0010/UA-0011 pages or catalogs.

Therefore the following required Gate A items are **not** produced here and
are **not claimed**:

- exact SHA/size of the six source files and `crm.db` before transform;
- `sqlite3 "PRAGMA quick_check;"` result;
- "11 unique published rows, UA-0009 PASS" confirmation;
- actual `status`, `days_to_kyiv`, `eta_manual`, `updated_at` values for the
  three rows as currently stored;
- parsed live HTML for the three cards (dates, footer `updated`, duplicate
  date in description);
- exact full-file SHA of the relevant functions in the six source files.

## What is ready instead

- `workflows/gate_a_readonly.yml`: a manual, GET-only GitHub Actions
  workflow that a controller/owner session with real read-only secrets can
  run. It safely no-ops (exit 0, no failure) when secrets are absent, which
  is exactly the state of this sandbox, and it always runs the fully
  offline synthetic test suite regardless.
- The offline synthetic regression suite in `tests/test_regression_synthetic.py`
  reproduces the *reported symptoms* (stale description date for
  UA-0009-shaped cards, a lost-update scenario matching UA-0010's timeline)
  against in-memory fixtures and proves the release candidate's contract
  holds. This is evidence of the **fix logic**, not of the **live root
  cause** — the live root cause (which exact step: CRM write, read-back,
  queue, publisher, or rebuild) can only be confirmed by running the real
  Gate A workflow against the real system.

## Overall Gate A verdict for this delivery

`FAIL` — real live evidence was not collected, because it could not be
collected from this environment. The package is
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` **only for the offline code
and test layer**; the live audit portion is outstanding and must be run by
a controller/session with actual repo and PythonAnywhere read-only access
before Gate B can even be considered.

Memory markers (must be echoed unchanged):
- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4
