# TASK_070 — Rollback Plan

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope of this Gate A package

This package is an ISOLATED CANDIDATE only. No production file was
modified:
  - Production `trace_zhurnal.py` — NOT TOUCHED.
  - Production `db.py` / `cars_ui.py` — NOT TOUCHED.
  - Production `crm.db` — NOT TOUCHED (no writes, no reads of the real DB).

Because nothing in production changed, there is **nothing to roll back**
in production as a result of this delivery.

## Rollback procedure for a FUTURE controlled rollout (Gate B, after
owner approval)

If/when this candidate is merged into production under a future Gate B
approval, the rollout procedure MUST include:

1. Before touching `trace_zhurnal.py`:
   - `cp trace_zhurnal.py trace_zhurnal.py.bak.<timestamp>`
   - `sha256sum trace_zhurnal.py > trace_zhurnal.py.sha256.before`
2. Apply the candidate `trace_zhurnal.py` (observer-only version).
3. `sha256sum trace_zhurnal.py > trace_zhurnal.py.sha256.after`
4. Deploy `db_writer_070.py` alongside, without wiring it into
   `cars_ui.py` yet (dark launch), and run the Gate A test matrix against
   a COPY of `crm.db`, never the live file.
5. If any test fails, or `PRAGMA quick_check` != `ok`, or card counts
   change, or UA-0009 / synthetic UA-XXXX fail:
   - `cp trace_zhurnal.py.bak.<timestamp> trace_zhurnal.py`
   - verify `sha256sum trace_zhurnal.py` matches `trace_zhurnal.py.sha256.before`
   - restart the bot process
   - confirm no queued writes were dropped (`DurableQueue070.size()` before
     and after must match)
6. Only wire `db_writer_070.py` into `cars_ui.py` call sites after a
   successful 10-minute canary AND a successful 60-minute soak against a
   staging copy, with owner's written `PASS_READY_FOR_GATE_B` approval.

## Automatic self-check before enabling in any environment

- `PRAGMA quick_check` must return `ok`.
- Card count before == card count after.
- UA-0009 test card must PASS the full field matrix.
- A synthetic future card `UA-XXXX` must PASS the same matrix.
- Restarting the writer process must not lose or duplicate any pending
  queue entry.
