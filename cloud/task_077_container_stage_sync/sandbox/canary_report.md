# Sandbox canary report — TASK 077

This report reflects two consecutive deterministic executions of
`sandbox/canary_harness.py` against a synthetic, isolated, in-memory SQLite
copy created solely by the harness. No real `crm.db`, no PythonAnywhere
connection, no live CRM write involved.

## Run 1

- LEGACY_MIGRATION_PLAN (no live write): ['UA-0012', 'UA-0999']
- SCENARIO UA-0012 -> ok=True (status=sea_loaded, days_to_kyiv=30, eta_manual=2026-09-28, published=1)
- SCENARIO UA-0009 -> ok=True (already sea_loaded, eta unchanged as expected)
- SCENARIO UA-0999 (future, no diagnostics) -> ok=True (placeholder path used, no publish error)
- SCENARIO failure-injection (publisher FAIL) -> ok=True (no success message, full rollback, published/status restored to preimage)
- Unrelated cards (UA-0020 Georgia, UA-0021 Kyiv, UA-0022 sold, UA-0023 sold_transit): byte/hash unchanged = True
- RUN 1 RESULT: PASS

## Run 2 (idempotency / determinism check, fresh synthetic DB)

- Identical scenario outcomes as Run 1.
- RUN 2 RESULT: PASS

## FINAL SANDBOX RESULT: PASS

## Notes

- `sold_transit` (UA-0023) was never touched by any scenario, confirmed by hash equality.
- Georgia/Kyiv/sold stages were not selected as ETA-transaction targets in these
  scenarios; the transaction's `BACKWARD_PROTECTED_STAGES` guard additionally
  refuses to move any of `georgia, kyiv, sold, sold_transit, terminal, archive`
  backward if ever invoked against them.
- Legacy migration was only *planned* (`migrate_legacy_sea_transit` exists but
  was not invoked with `allow=True` in these runs) — consistent with "no live
  write, plan only" requirement.
- These are genuine local execution results from this authoring session, not
  claims about the live PythonAnywhere CRM.
