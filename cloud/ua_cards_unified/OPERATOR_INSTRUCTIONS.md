# UA Cards Unified — Operator Instructions (Gate A only)

## Scope

This package performs **Gate A** local validation of UA card data only.
It never writes to production, never calls PythonAnywhere, and never
performs Gate B (production application). Gate B requires a separate,
explicit owner approval outside this repository/package.

## Layout

```
cloud/ua_cards_unified/
  common.py            shared constants/helpers (paths, banned IDs)
  preflight.py          read-only audit (run first, or via launcher)
  runner.py             Gate A validation of each card
  manifest_builder.py   combines preflight + run results into manifest.json
  launcher.py            no-argument restricted entrypoint (runs all 3 stages)
  data/input_cards/      put real card *.json files here (NOT synthetic UA-0001..UA-0008)
  output/                generated locally: preflight_report.json, run_log.json,
                         manifest.json, cards/*.json
  tests/test_pipeline.py unit tests using temp directories only
```

## How to run

1. Place real card JSON files (schema: `card_id`, `title`, `payload`) into
   `cloud/ua_cards_unified/data/input_cards/`.
2. From the `cloud/ua_cards_unified/` directory, run:

   ```
   python launcher.py
   ```

   The launcher takes **no arguments**. Passing any argument aborts
   immediately (exit code 2) without running anything.

3. Review the generated files under `output/`:
   - `preflight_report.json` — read-only audit findings.
   - `run_log.json` — per-card validation results and overall gate_status.
   - `manifest.json` — final combined gate_status and blocking_reasons.

## Gate semantics

- `gate_status: BLOCKED` — at least one problem was found (missing/invalid
  card, banned synthetic id, zero cards, preflight failure). No further
  action is taken automatically.
- `gate_status: AWAITING_GATE_B` — every discovered card passed Gate A
  validation. This is a **status label only**; it does not trigger any
  write to production or PythonAnywhere. Advancing to Gate B is a separate
  manual step that requires explicit owner approval and is outside this
  package's code.

## Safety guarantees enforced in code

- `BANNED_SYNTHETIC_IDS` in `common.py` = `UA-0001` .. `UA-0008`. Any card
  using one of these IDs is rejected at both preflight and runner stages.
- No file in this package makes network calls, imports `requests`/`urllib`
  for outbound calls, or references PythonAnywhere credentials/URLs.
- `preflight.py` never modifies input cards; it only reads them and writes
  its own report file.
- A single failing card blocks the **entire batch** — the pipeline never
  reports partial success as AWAITING_GATE_B.

## Running the tests

```
python -m unittest cloud/ua_cards_unified/tests/test_pipeline.py -v
```

All tests operate on temporary directories only; they never touch
`data/input_cards/` or any production system.
