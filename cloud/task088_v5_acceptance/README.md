# FINAL v5.0 offline acceptance diagnostics

This directory diagnoses the existing Stage 4 candidate against the approved
UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0. It is **not an active runtime, installer,
Preview Gate, Production receipt or live acceptance result**.

Run from the repository root, with the privately captured exact CRM source:

```sh
python -B cloud/task088_v5_acceptance/audit_v5.py \
  --cars-ui-source /absolute/private/path/cars_ui.py
```

The script writes JSON to stdout. Exit `1` means a demonstrated requirement
failure; exit `2` means a setup/check error. Missing or changed private source
never becomes a PASS. Source hashes identify what was tested. The existing
`patch_cars_ui.py` enforces its exact baseline hash.

The harness reuses the existing test modules' fixture scaffolding, invokes the
actual patched CRM write helper and actual price-sync runtime, and evaluates
independent v5 expectations. It does not run unittest expectations that permit
the older behavior. All DB and HTML writes are inside temporary fixtures. Public
reads and Telegram sends are mocks; sockets are blocked. Existing source files
are read only. Private source contents are never emitted or copied.

Checks:

1. Four distinct conscious GE inputs remain queued for their own completion.
2. `245` requires confirmation before saving or enqueueing.
3. `245000` requires confirmation before saving or enqueueing.
4. A recreated worker automatically resumes a committed claim without reentry.
5. Successful verified publication produces a completion receipt to the operator.

The anomaly checks exercise the current raw-input write helper used directly by
the selected-price message handler. A future UI design with a separate durable
confirmation adapter will need that adapter included in the harness; these
checks are not a universal browser/Telegram UI test. The receipt scenario exposes
that the current event schema cannot carry the initiating operator and that the
successful runtime currently sends no receipt at all. Fake delivery cannot prove
real Telegram delivery, routing or permission checks.

`observed_candidate.json` records this candidate's actual results, not expected
failures treated as success. See `FINDINGS.md` for static issues outside these
five executable checks. A green result here would still require the remaining
v5 checks and real Stage 3/4 acceptance.
