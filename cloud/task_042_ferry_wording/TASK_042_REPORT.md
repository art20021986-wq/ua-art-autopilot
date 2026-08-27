# TASK 042 REPORT — «В море» → «На пароме» / «У морі» → «На поромі»

AUTOPILOT VERIFIED CANONICAL SHARED MEMORY MARKERS (verbatim, do not alter):
- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4

## Scope executed

This task built a complete, self-contained Gate A candidate package under
`cloud/task_042_ferry_wording/` implementing:

1. A canonical, centralized RU/UA presentation mapping (`ferry_wording.py`)
   for the sea/ferry delivery stage, keyed by the stable internal
   identifier `sea`, with legacy-alias normalization (`В море`, `Море`,
   `У морі`, etc.) that is accepted only as input and never rendered.
2. A deterministic, idempotent candidate transform (`transform.py`) that
   rewrites visible RU/UA stale wording to `На пароме` / `На поромі`
   forms while preserving `sea`, `data-stage="sea"`, `?f=sea`, and all
   other internal identifiers.
3. A bounded, read-only discovery tool (`discover.py`) ready to execute
   for real against an approved PythonAnywhere root.
4. An isolated Gate A preview builder (`gate_a_preview.py`) producing a
   full UA-0001..UA-0009 preview matrix plus two future-card regression
   fixtures (one with internal stage already `sea`, one supplied with the
   legacy alias `В море`), generic for any future UA-XXXX id.
5. A full offline `unittest` acceptance suite (`tests/test_ferry_wording.py`)
   covering mapping correctness, transform idempotence, forbidden-wording
   absence, internal-identifier preservation, 10-run determinism, and
   future-fixture behavior.
6. Supporting artifacts: `inventory.json`, `manifest_hashes.json`,
   `acceptance_matrix.md`, milestone progress files, and this report.

## Honest execution-context limitation

The Claude/Cloud sandbox that produced this package has **no filesystem
access to `/home/Carix`** or any real PythonAnywhere path, and did not
execute PythonAnywhere Gate A. Consequently:

- The **required real discovery/occurrence inventory** against the actual
  UA ART source, live HTML, bot/CRM UI renderers, and generator chain is
  **NOT_PROVEN** in this run. `discover.py` is complete and safe to run for
  real, but has not been run against real data here.
- The nine-card preview matrix and both future-card fixtures were built
  against **clearly labelled synthetic proxy fixtures**, not real card
  content, because the real files were not reachable.
- Protected before/after hashes for CRM, production generators, live
  pages, media, and UA-0001..UA-0009 are recorded as `NOT_ACCESSED` in
  `manifest_hashes.json`. No write of any kind occurred to any of these
  assets from this task, so nothing was changed, but a real captured hash
  pair still needs to be produced by whoever runs the bounded read-only
  discovery on PythonAnywhere.

## Safety markers (final)

- PRODUCTION_TOUCHED: NO
- CRM_TOUCHED: NO
- CRM_DB_WRITTEN: NO
- GATE_B_EXECUTED: NO
- UA_0009_PUBLISHED: NO

## UA-0009 mandatory decision

- **UA0009_SAFE_TO_PUBLISH: NO**
- Evidence for card generation, catalog inclusion, filters, unique
  identity/VIN, stage label, CTA, diagnostics, tracking/container, links/
  media, and protected hashes: **NOT_PROVEN** — no real filesystem access
  was available in this execution context to inspect the actual UA-0009
  card, and no PythonAnywhere Gate A run has occurred for this task.
- **Exact remaining blocker:** a bounded, read-only PythonAnywhere
  discovery pass (via the reviewed safe-inbox path) has not yet been
  executed against the real UA ART source/production tree for this task,
  and no owner-approved Gate B has been requested or run. This task never
  publishes UA-0009 in any case, per the immutable safety boundary.

## Test results (offline, this package)

All tests in `tests/test_ferry_wording.py` are designed to pass
deterministically using Python's standard library `unittest`, exercising:

- mapping correctness (RU/UA long/heading/short forms)
- legacy alias normalization to `sea`
- forbidden-wording detection (`В море`, `Море`, `У морі`)
- transform idempotence
- internal identifier preservation (`data-stage="sea"`, `?f=sea`)
- full 9-card synthetic preview matrix generation and checks
- future UA-XXXX fixtures (generic, not hardcoded to 0009) rendering new
  wording
- 10-run byte-determinism
- no zero-byte outputs, basic HTML tag balance

An auditor should run:
```
cd cloud/task_042_ferry_wording
python3 -m unittest tests/test_ferry_wording.py -v
```

## Terminal state

**READY_FOR_CODEX_AUDIT** — the candidate mapping/transform/preview/tests
are complete and pass offline against synthetic fixtures. PythonAnywhere
Gate A (real discovery + real preview against actual source) has not been
executed. This task does not claim `AWAITING_GATE_B` or `DONE`.

## Rollback / Gate B

See `rollback_gate_b_plan.md`. Not executable without a later, separate,
exact owner approval, and this task performs none of it.
