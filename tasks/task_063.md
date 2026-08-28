# TASK 063 — FERRY WORDING: 10 CURRENT CARS + TWO-LINE CATALOG ROUTE

STATUS: GATE_A_PASS / WAIT_OWNER_APPROVAL
OWNER_REQUEST: «Сейчас у нас уже в каталоге 10 машин. Поднять историю, внести корректировки и в работу по TASK 15».
OWNER_LABEL: TASK/TAX 15 — «В море» → «На пароме»
CANONICAL_PARENTS: task_047, task_050, task_052
MODE: SMALL_CORRECTION / AUTOMATED ISOLATED GATE_A
MEMORY_PREFLIGHT: REQUIRED
PRODUCTION_WRITE: NO
CRM_WRITE: NO

## Canonical history binding

Do not overwrite `tasks/task_015.md`: canonical TASK 015 is the approved SHARED MEMORY task.
The owner's conversational label «TASK 15» for ferry wording maps to the existing ferry chain
`task_047 → task_050 → task_052` and its `FERRY_GATE_A_REPORT.md`.

The previous Gate A evidence covered 9 cards and 13 HTML candidates. It is now stale because
the owner confirms that the live catalog contains 10 cars and requests a catalog-copy correction.

## Exact correction

1. Discover the current catalog and CRM read-only. Require exactly 10 current catalog cars.
   Derive the actual IDs from verified current data; include UA-0010 when verified. Never invent an ID.
2. Do not hard-code “10” into visible UI or generator business logic. The catalog count must remain
   data-derived, and all future UA-XXXX cards must inherit the same template behavior.
3. For every catalog card whose internal stage remains `sea`, render the public route as exactly two
   separate visual lines:

   RU:
   ```text
   На пароме
   Маршрут: Корея → Грузия
   ```

   UK:
   ```text
   На поромі
   Маршрут: Корея → Грузія
   ```

4. Replace the current one-line catalog form such as
   `На пароме · Корея → Грузия` only in the catalog-card route block. Use an explicit encoded
   line break plus `white-space: pre-line`, so desktop and mobile do not depend on wrapping width.
5. Apply through the canonical generator/template, not by editing only the currently affected cards.
   Existing 10 cards and every future card must inherit it automatically.
6. Outside the catalog-card route block, preserve the accepted contextual wording:
   - RU status/filter/chip: `На пароме`;
   - UK status/filter/chip: `На поромі`;
   - RU short stage: `Паром`;
   - UK short stage: `Пором`.
7. Preserve ordinary prose, scripts, styles, comments, legacy input aliases and historical reports.
   Never perform a global substring replacement.
8. Preserve byte-identically all internal values and interfaces:
   `sea`, `data-stage="sea"`, `stage=sea`, `?f=sea`, CRM/SQLite enums, IDs, URLs,
   analytics keys, container data, prices, specifications, photos, diagnostics and card links.

## Reuse, do not rebuild

Reuse the accepted structural tokenizer, safe read contract, contextual transform, tests, Gate A
controller and evidence format under `cloud/task_047_ferry_discovery/`.
Make only the bounded changes needed for:
- 10 current cars;
- generic future-card coverage;
- the exact two-line catalog route;
- dynamic preview candidate counting.

Do not create a clean-room replacement and do not delete prior regression coverage.

## Mandatory tests

- exact RU and UK two-line catalog output;
- existing one-line catalog form becomes the two-line structure;
- all current discovered `sea` catalog cards use the new structure;
- all 10 current catalog cars remain present, linked and unchanged except scoped presentation text;
- a synthetic future UA-XXXX card inherits the same template behavior;
- non-`sea` cards remain byte-equivalent;
- filters, counters, routes and card links remain functional;
- scripts/styles/comments/ordinary prose stay unchanged;
- internal `sea` markers and CRM values stay unchanged;
- deterministic/idempotent transform;
- compile and existing full ferry regression suite pass with no skipped tests.

## Execution

1. Perform MEMORY PREFLIGHT and audit current ferry artifacts.
2. Read current PythonAnywhere inputs only through the proven fail-closed read path.
3. Rebase the verified current discovery scope from 9 to 10 cars; keep the catalog-card transform generic for future UA-XXXX cards.
4. Produce isolated candidates only under `/home/Carix/autopilot_inbox`.
5. Run offline tests, then the existing automated isolated Gate A.
6. Regenerate screenshots for the actual candidate count dynamically; no fixed 13-file assertion.
7. Update evidence and report current source hashes. Old 9-card hashes are not valid approval evidence.
8. Finish only as `PASS_READY_FOR_GATE_B` or `BLOCKED` with exact evidence.

## Deliverables

Modify only the necessary existing files under `cloud/task_047_ferry_discovery/`, plus:

- `cloud/task_047_ferry_discovery/TASK_063_REPORT.md`
- `cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json` through the Gate A workflow
- `cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md` through the Gate A workflow
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

## Acceptance gate

PASS requires:

- VERIFIED_CURRENT_CATALOG_COUNT: 10
- CURRENT_CARDS_PRESERVED: 10/10
- FUTURE_CARD_TEMPLATE_CHECK: PASS
- TWO_LINE_RU: PASS
- TWO_LINE_UK: PASS
- INTERNAL_SEA_MARKERS_UNCHANGED: PASS
- CRM_WRITE: NO
- PRODUCTION_WRITE: NO
- UA0009_SAFE_TO_PUBLISH: evidence-based YES/NO
- UNEXPECTED_PROTECTED_CHANGES: 0

Gate A passed in run `33152339846`; production installation, service reload, CRM/database write and Gate B were not executed.
Production remains unchanged until the corrected screenshot is approved and Gate B is separately authorized.

