# UA-0011 Before/After matrix — TASK 084

VIN: `KMHE341DBKA544289` | Card: `UA-0011` | Hyundai SONATA 2018

## Live audit status

**NOT CAPTURED.** This worker has no live credentials/network path to the production
CRM. The columns below marked `NOT-CAPTURED (pending controller Gate A fetch)` must be
filled in by running `gate_a_fetch_ua0011.py` from the controller execution environment
that holds real CRM credentials, exactly as was done for TASK 021 (Shared Memory REC-0013).

| Field | Exact CRM field name | Before (live) | After (target per owner directive) |
|---|---|---|---|
| Stage/status | NOT-CAPTURED (pending controller Gate A fetch) | NOT-CAPTURED | `kr_bought` ("В Корее") |
| Container number | NOT-CAPTURED (pending controller Gate A fetch) | NOT-CAPTURED | empty / NULL |
| Arrival date / ETA | NOT-CAPTURED (pending controller Gate A fetch) | NOT-CAPTURED | empty / NULL, not computed |
| All other fields | — | fingerprinted via SHA-256 by `gate_a_fetch_ua0011.py`, values not altered | byte-identical to before |
| Media manifest | — | full ordered list captured by fetch script | byte-identical to before; first item confirmed as UA-0011's own cover photo |

## What IS proven in this run (offline, synthetic fixtures)

Using `fixtures/ua_cards_fixture.json` (synthetic stand-in data, not real CRM data) the
same transform/guard/renderer code that would run against the real record was executed
10 times in `tests/test_gate_a_sandbox.py`:

- Target delta correctness: PASS (status/container/date change exactly as specified, nothing else changes).
- Idempotency over 10 reruns: PASS (0 drift after first application).
- 10 full sandbox runs across all 11 synthetic cards: PASS (0 duplicates, 0 drift, 0 unexpected changes).
- Full-template renderer used for every card, never the narrow fallback: PASS.
- UA-0011 (post-reset) renders with cover photo first and full info block, omitting only the
  two intentionally emptied fields: PASS.
- UA-0009 publication guard stays at `NO`: PASS.
- Superseded TASK 082 ferry-status write attempt for UA-0011: rejected (fail-closed): PASS.

## Verdict

**GATE A: BLOCKED-PENDING-LIVE-FETCH.** No fail — a genuine access-scope limitation.
Tooling, guards, renderer fix, and offline test evidence are complete and ready. The live
fetch/audit and therefore the final live before/after matrix and PASS/BLOCKED verdict on
real UA-0011 data must be produced by the controller execution path holding real CRM
credentials. `PRODUCTION_TOUCHED: NO` in all cases.
