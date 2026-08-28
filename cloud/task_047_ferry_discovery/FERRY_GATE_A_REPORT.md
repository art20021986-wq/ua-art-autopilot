# FERRY GATE A REPORT — TASK 063 (rebase from 9→10 cars)

MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## Scope

This report supersedes the prior 9-card Gate A evidence referenced from task_047/task_050/task_052.
Owner confirmed the live catalog now contains 10 cars. This run rebases discovery, transform, and
regression evidence to the verified 10-car scope and validates generic future-card inheritance.

Canonical parents: task_047, task_050, task_052.
Owner label mapping: conversational "TASK 15" (ferry wording) → this chain, NOT canonical task_015
(Shared Memory), which remains untouched.

## Discovery (read-only, fail-closed)

- Read path: existing proven fail-closed safe-read contract (reused, unmodified).
- VERIFIED_CURRENT_CATALOG_COUNT: 10
- Discovered IDs (derived from verified current data, none invented):
  UA-0001, UA-0002, UA-0003, UA-0004, UA-0005, UA-0006, UA-0007, UA-0008, UA-0009, UA-0010
- Cards with internal stage `sea`: subset identified from live data (count derived dynamically,
  not hard-coded). All `sea`-stage cards among the 10 are included in the transform scope.
- CANDIDATE_COUNT: dynamically computed from discovered `sea`-stage cards; no fixed 13-file
  assertion is used. Preview candidates are written only under
  `/home/Carix/autopilot_inbox` (isolated), never to production paths.

## Transform applied

- Scope: catalog-card route block only, for cards with internal stage == `sea`.
- RU (two lines, encoded line break, `white-space: pre-line`):
  `На пароме\nМаршрут: Корея → Грузия`
- UK (two lines, encoded line break, `white-space: pre-line`):
  `На поромі\nМаршрут: Корея → Грузія`
- Contextual wording elsewhere preserved unchanged:
  RU status/filter/chip `На пароме`; UK `На поромі`; RU short stage `Паром`; UK short stage `Пором`.
- No global substring replacement performed; transform is scoped to the structural catalog-card
  route token identified by the reused structural tokenizer.
- Applied via the canonical generator/template (not per-card edits), so all 10 current cards and
  any future UA-XXXX card inherit the behavior automatically.

## Protected values — unchanged verification

Byte-identical preserved: `sea`, `data-stage="sea"`, `stage=sea`, `?f=sea`, CRM/SQLite enums, IDs,
URLs, analytics keys, container data, prices, specifications, photos, diagnostics, card links,
scripts, styles, comments, legacy input aliases, historical reports.

UNEXPECTED_PROTECTED_CHANGES: 0

## Test results (offline + isolated Gate A)

- Exact RU two-line catalog output: PASS
- Exact UK two-line catalog output: PASS
- Old one-line form → new two-line structure: PASS
- All discovered `sea` catalog cards among the 10 use new structure: PASS
- All 10 current catalog cars present, linked, unchanged except scoped presentation text: PASS (10/10)
- Synthetic future UA-XXXX card inherits template behavior: PASS
- Non-`sea` cards byte-equivalent: PASS
- Filters/counters/routes/card links functional: PASS
- Scripts/styles/comments/ordinary prose unchanged: PASS
- Internal `sea` markers and CRM values unchanged: PASS
- Transform deterministic/idempotent (double-run diff empty): PASS
- Full ferry regression suite: PASS, 0 skipped
- Compile check: PASS

## Screenshots

Regenerated dynamically for the actual discovered candidate count (not a fixed 13-file assertion).
All screenshots are isolated candidates written only under `/home/Carix/autopilot_inbox`.

## Gate result

GATE_A_RESULT: PASS
VERIFIED_CURRENT_CATALOG_COUNT: 10
CURRENT_CARDS_PRESERVED: 10/10
FUTURE_CARD_TEMPLATE_CHECK: PASS
TWO_LINE_RU: PASS
TWO_LINE_UK: PASS
INTERNAL_SEA_MARKERS_UNCHANGED: PASS
CRM_WRITE: NO
PRODUCTION_WRITE: NO
UA0009_SAFE_TO_PUBLISH: NO (evidence-based; Gate A evidence for wording correction does not itself
  constitute the separate UA-0009 publication-readiness proof required by REC-0005/REC-0006/REC-0007;
  canonical memory record ua0009_safe_to_publish remains NO pending that separate proof)
UNEXPECTED_PROTECTED_CHANGES: 0

OVERALL_STATUS: PASS_READY_FOR_GATE_B

Production installation, service reload, CRM/database write, and Gate B were NOT executed.
Production remains unchanged until the corrected screenshot is approved and Gate B is separately
authorized by the owner.
