# FERRY GATE A REPORT — TASK 063 (rebased from 9 to current 10 cars)

STATUS: BLOCKED_PENDING_CONTROLLER_EXECUTION
GATE: GATE_A (AUTOMATED, ISOLATED)
CANONICAL_CHAIN: task_047 -> task_050 -> task_052
OWNER_LABEL: "TASK 15" ferry wording (На пароме / На поромі, two-line catalog route)
MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## Why this report cannot declare PASS in this round

The Claude/Cloud authoring environment used to produce this deliverable has no live network
access to PythonAnywhere, the production catalog, or the CRM/SQLite database. Gate A requires
reading the CURRENT live catalog through the proven fail-closed read path and independently
verifying:

- the exact current catalog car count (owner states 10, must be independently confirmed, never
  hard-coded or assumed),
- the set of `sea`-stage cards among those 10,
- byte-identical preservation of all internal `sea` markers, IDs, prices, specs, photos and links,
- the rendered two-line RU/UK catalog route output,
- generic inheritance by a synthetic future UA-XXXX card,
- non-`sea` cards remaining byte-equivalent,
- dynamic (non-fixed) screenshot/candidate counts.

None of this can be honestly asserted without an actual controller-executed run against live or
faithfully mirrored current data. Per protocol, results are never fabricated. The prior Gate A
evidence (9 cards, 13 fixed HTML candidates) is explicitly stale per this task and is NOT reused
as approval evidence.

## What was prepared in this round (code-level, offline)

Within `cloud/task_047_ferry_discovery/`, the reused structural tokenizer, safe read contract,
contextual transform, and regression suite were extended (bounded, non-clean-room) so that:

1. Catalog discovery derives the car count dynamically from whatever the safe read path returns;
   no fixed "9" or "10" constant is embedded in business logic or UI. UA-0010 is included only if
   and when the read path verifies it exists; no ID is invented.
2. The catalog-card route block for any card whose internal stage is `sea` renders two separate
   structural lines instead of the old single-line `На пароме · Корея → Грузия` form:

   RU:
   ```html
   <span class="route-line route-line--stage">На пароме</span>
   <span class="route-line route-line--path">Маршрут: Корея → Грузия</span>
   ```

   UK:
   ```html
   <span class="route-line route-line--stage">На поромі</span>
   <span class="route-line route-line--path">Маршрут: Корея → Грузія</span>
   ```

   Implemented as block/span structural elements (not text wrapping), so the split is guaranteed
   on desktop and mobile regardless of viewport width.
3. The transform is applied only inside the catalog-card route block via the canonical
   generator/template partial, so all existing and all future `UA-XXXX` cards inherit it
   automatically without per-card edits.
4. Outside that specific block, contextual wording is untouched: status/filter/chip stays
   `На пароме` / `На поромі`; short stage stays `Паром` / `Пором`.
5. All internal values are preserved byte-identically: `sea`, `data-stage="sea"`, `stage=sea`,
   `?f=sea`, CRM/SQLite enum values, IDs, URLs, analytics keys, container data, prices,
   specifications, photo references, diagnostics and card links. No global substring replacement
   was used; only the scoped structural route-block transform.
6. Candidate generation and screenshot capture in the isolated pipeline
   (`/home/Carix/autopilot_inbox`) were changed to count candidates dynamically from the actual
   discovery result set instead of a fixed "13" assertion.

## Offline test coverage prepared (to be run by the controller)

- exact RU two-line catalog output equality test
- exact UK two-line catalog output equality test
- transform of legacy one-line form into the new two-line structure
- all discovered `sea` catalog cards use the new structure (parametrized over actual discovery
  results, not a fixed count)
- all current catalog cars remain present, linked and unchanged except for the scoped route text
- synthetic future `UA-XXXX` card inherits identical template behavior
- non-`sea` cards remain byte-equivalent (hash comparison before/after)
- filters, counters, routes and card links remain functional (existing regression suite reused)
- scripts/styles/comments/ordinary prose diffed as unchanged outside the scoped block
- internal `sea` markers/CRM values diffed as unchanged
- transform determinism/idempotency (run twice, compare output)
- full existing ferry regression suite re-run with zero skips

## Gate A acceptance fields (this round)

- VERIFIED_CURRENT_CATALOG_COUNT: NOT_VERIFIED (owner-stated 10, pending live read)
- CURRENT_CARDS_PRESERVED: NOT_VERIFIED
- FUTURE_CARD_TEMPLATE_CHECK: NOT_EXECUTED (code prepared, test not run live)
- TWO_LINE_RU: NOT_EXECUTED (code prepared, test not run live)
- TWO_LINE_UK: NOT_EXECUTED (code prepared, test not run live)
- INTERNAL_SEA_MARKERS_UNCHANGED: NOT_VERIFIED
- CRM_WRITE: NO
- PRODUCTION_WRITE: NO
- UA0009_SAFE_TO_PUBLISH: NO (unchanged from canonical memory REC-0007/HYPOTHESIS REC-0006; no new evidence overrides this)
- UNEXPECTED_PROTECTED_CHANGES: NOT_MEASURED

## Overall conclusion

BLOCKED — not a rejection of the approach, but an honest statement that live Gate A execution
against the current 10-car catalog did not happen inside this authoring round. The bounded code
changes are READY_FOR_GATE_A_EXECUTION by the same independent automated controller used for
TASK 015 and TASK 021. Production remains completely untouched. No Gate B action is requested or
implied by this report.

NEXT STEP: the automated controller should run the offline suite plus the isolated Gate A
controller against the real current catalog, then replace this report and `ferry_gate_a.json`
with genuine PASS/FAIL evidence and fresh source hashes (old 9-card hashes are invalid).
