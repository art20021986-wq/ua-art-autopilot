# TEST_MATRIX.md — TASK_016

For every record UA-0001..UA-0009, the Gate A run must record all of
the following in `progress.json` / `gate_a_receipt.json`:

| # | Check | Pass condition |
|---|---|---|
| 1 | Real source located | HTML file found via hardcoded candidate list, else `NOT_PROVEN` |
| 2 | Preview card created | file exists under preview root |
| 3 | Diagnostics button count | exactly 1 (`id="ua_diag_btn"`) |
| 4 | Diagnostics page exists | `<code>_diagnostics.html` present |
| 5 | Diagnostics state truthful | shows `Уточняется` when CRM value absent |
| 6 | Tracking button count | exactly 1 (`id="ua_track_btn"`) |
| 7 | Tracking page exists | `<code>_tracking.html` present |
| 8 | Tracking state truthful | no invented container number/link |
| 9 | No empty/unsafe links | no empty href/src, no `javascript:` |
| 10 | No duplicate legacy variants | none of the patterns in `LEGACY_CONFLICT_AUDIT.md` remain |
| 11 | Verified poster/fallback | real verified image or generated local fallback SVG only |
| 12 | Mobile structure | viewport meta present, buttons not covered by floating widgets |
| 13 | Media containment/integrity | every referenced media file passes containment + hash checks |
| 14 | Protected hashes unchanged | UA-0001..UA-0008 and CRM before/after SHA-256 identical |

## Determinism requirement

The complete sequence above must be run 10 times against the same real
data in staging; canonical JSON hash of results must be identical
across all 10 runs before any preview is considered exposable.

## Regression fixtures

`UA-9998` (empty) and `UA-9999` (full) run through the same checks as a
permanent regression signal but never replace inspection of the real
nine records.

## Status at authoring time

This matrix is fully specified and implemented in
`START_UA_CARDS_UNIFIED.py`. Actual pass/fail results only exist after
a real Gate A execution produces `gate_a_receipt.json` on
PythonAnywhere; see `BLOCKED.md`.
