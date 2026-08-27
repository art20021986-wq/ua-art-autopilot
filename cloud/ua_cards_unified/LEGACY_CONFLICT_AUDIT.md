# LEGACY_CONFLICT_AUDIT.md — TASK_016

## Purpose

Document every known/legacy diagnostic and tracking control class/id
pattern that must be removed from preview copies before the unified
buttons are inserted, to guarantee exactly one of each control.

## Known legacy patterns targeted for removal

| Pattern | Type | Reason |
|---|---|---|
| `class="old-diag"` button | diagnostics | superseded by unified button |
| `class="legacy-diag"` button | diagnostics | superseded |
| `class="diag-old"` button | diagnostics | superseded |
| `id="legacy_diagnostics"` button | diagnostics | superseded |
| `class="old-track"` link | tracking | superseded by unified button |
| `class="legacy-track"` link | tracking | superseded |
| `class="track-old"` link | tracking | superseded |
| `id="legacy_tracking"` link | tracking | superseded |

This list is intentionally conservative and hardcoded. Real production
HTML for UA-0001..UA-0009 has not yet been inspected on PythonAnywhere
by this worker at authoring time; the Gate A run (see `BLOCKED.md`)
must confirm whether additional legacy variants exist. Any variant not
in this table is left untouched and reported, never guessed at.

## Ambiguous anchor handling

If the Gate A run reports more than one candidate insertion point for a
given card, that card is marked FAIL in `progress.json` and
`gate_a_receipt.json`; no automatic guess is made. Owner/ChatGPT should
request a manual anchor decision if that occurs.

## Outcome of this audit

This document is a pre-registered detection ruleset. Its completeness
can only be confirmed after a real Gate A pass produces per-card
diagnostics in `progress.json`. Until that receipt exists, this audit
is PARTIAL / NOT_PROVEN against real production markup.
