# TASK 084 — UA-0011-KOREA-CARD-RESET-001 v1.0

## Scope of this run

This worker (Claude/Cloud) has NO live network access to the production CRM, PythonAnywhere,
or any database holding UA-0011 (Hyundai SONATA 2018, VIN KMHE341DBKA544289). Therefore the
"fresh read-only live audit" step of Gate A cannot be executed inside this environment. No live
field values, no live media manifest, and no live SHA hashes were fetched, and none are fabricated
in this report.

What this run DOES deliver, ready for the Codex controller (which has the credentialed execution
path used in prior tasks such as TASK 021) to run against the real CRM:

1. A read-only fetch script (`gate_a_fetch_ua0011.py`) that pulls the UA-0011 record and computes
   a SHA-256 fingerprint of every field except status/container/eta, plus the full media manifest,
   without writing anything back.
2. A pure, side-effect-free sandbox transform (`sandbox_transform.py`) implementing the exact
   target delta from the owner directive: `status -> kr_bought`, container field -> empty,
   arrival/ETA field -> empty, everything else (including media) byte-identical.
3. Root-cause guards (`guards.py`) that the controller can wire into the real stage-change /
   writer pipeline so that:
   - CRM stage change is the only source of the publicly shown stage,
   - container/ETA can never be persisted while status is `kr_bought`,
   - a catalog write is blocked until media mapping/sync for that card is complete,
   - re-applying the same transform twice produces an identical result (idempotent).
4. A renderer root-cause fix (`renderer_fix.py`) that removes the narrow text-only fallback
   template and always renders the full unified card template (photo + full info block), simply
   omitting a sub-block when a specific field is absent, instead of switching to a stripped-down
   template. This is the structural fix requested in directive item 7.
5. An offline test suite (`tests/test_gate_a_sandbox.py`) that runs entirely against synthetic
   fixtures (`fixtures/ua_cards_fixture.json`) standing in for UA-0001..UA-0011, executed 10 times
   in a loop to prove: 0 duplicates, 0 drift, 0 unexpected changes, and that UA-0009 stays blocked
   from publication per Shared Memory record REC-0007/REC-0006 (`ua0009_safe_to_publish: NO`).

## Why this is BLOCKED for Gate A sign-off, not a technical failure

Gate A explicitly requires "Получить свежую строку UA-0011 ... без записи" (fetch a fresh live
row, read-only). That step needs live CRM credentials/network access this worker does not have.
Fabricating field names, current container number, current status, or media manifest values would
violate the fail-closed rule ("При любом несовпадении — fail-closed без частичной записи") and the
rule against inventing data. Therefore the honest outcome is: **tooling and guards are complete
and test-proven offline; the live audit step and therefore full Gate A PASS/BLOCKED verdict on
real UA-0011 data must be produced by the controller execution path that holds real credentials**,
the same pattern already used and accepted for TASK 021 (see Shared Memory REC-0013).

## Explicit guarantees

- No production write attempted or proposed.
- No CRM write attempted or proposed.
- No PythonAnywhere execution attempted or proposed.
- No TASK 082 logic ("На пароме"/ferry status for UA-0011) is reused; this package treats any
  code path that would set UA-0011 to a ferry/on-the-way stage as **superseded and fail-closed**
  (see `guards.py: reject_superseded_task_082_ferry_status`).
- All fixture data is synthetic placeholder data except the already-task-disclosed VIN, used only
  to prove offline guard logic; no real customer PII, no photos, no database blobs are embedded.

## Files in this package

- `gate_a_fetch_ua0011.py` — read-only live fetch script (requires real credentials to run; not run here).
- `sandbox_transform.py` — pure sandbox delta transform + idempotency helper.
- `guards.py` — permanent guards described in the directive.
- `renderer_fix.py` — root-cause renderer fix (no narrow fallback template).
- `tests/test_gate_a_sandbox.py` — offline synthetic-fixture test suite (10 repeated runs).
- `fixtures/ua_cards_fixture.json` — synthetic fixture data for UA-0001..UA-0011.
- `before_after_matrix.md` — target delta matrix; "before" column marked NOT-CAPTURED pending real Gate A fetch.
