# TASK 063 — Ferry Wording: 10 Current Cars + Two-Line Catalog Route

CANONICAL_PARENTS: task_047, task_050, task_052
OWNER_LABEL: TASK/TAX 15 — «В море» → «На пароме»
CONTEXT_BUNDLE_SHA256 (received): 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Result

STATUS: BLOCKED (no fabricated execution)

## Why this is BLOCKED and not PASS_READY_FOR_GATE_B

This worker (Claude/Cloud) operates in an isolated repository-only environment and has no live
network or filesystem access to the real PythonAnywhere host, the real CRM/SQLite database, or
the real current catalog HTML/inventory files referenced by `cloud/task_047_ferry_discovery/`.

Per canonical shared memory (REC-0009, REC-0011, REC-0013) the accepted pattern for this program is:
Claude/Cloud prepares code, tests, and packages; an **independent controller** (Codex/automated
Gate A runner) performs the actual read-only discovery against real inputs, executes the isolated
Gate A workflow under `/home/Carix/autopilot_inbox`, and records verified evidence in
`cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json` and
`cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md`.

Because this worker cannot itself:
- perform the MEMORY PREFLIGHT against real production/CRM state,
- discover the real current catalog and independently verify "exactly 10 cars" with real IDs,
- compute real source hashes for the current 10-card catalog,
- run the actual isolated Gate A controller against real PythonAnywhere-derived inputs,
- regenerate real screenshots,

any claim of PASS_READY_FOR_GATE_B with fabricated evidence would violate the no-fabrication
constraint already recorded in canonical memory (REC-0009: "Execution results were not
fabricated"). This report intentionally avoids inventing IDs, hashes, screenshot counts, or a
fake 10/10 verification.

## What this worker can safely state

- No production write occurred. PRODUCTION_WRITE: NO.
- No CRM write occurred. CRM_WRITE: NO.
- No files under `cloud/task_047_ferry_discovery/evidence/` or
  `cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md` were regenerated in this round, because
  doing so would require running the actual Gate A controller against live-derived inputs, which
  this worker did not do. The previously recorded Gate A run `33152339846` (9-card evidence) is
  explicitly acknowledged as stale per the task instructions and must NOT be cited as current
  approval evidence for the 10-car state.
- UA0009_SAFE_TO_PUBLISH remains NO per canonical memory (`ua0009_safe_to_publish: NO`) — this is
  unchanged by this task and is not overridden here.

## Bounded design for the required correction (for the controller to apply/verify)

The following describes the exact, scoped change that must be applied via the canonical
generator/template referenced by task_047/050/052 (the accepted structural tokenizer and
contextual transform), without rebuilding it and without touching unrelated files:

1. Locate the single catalog-card route rendering function used by the canonical template for
   cards whose internal stage equals `sea` (the accepted internal marker, byte-preserved).
2. In that function only, for RU output, replace the one-line form
   `На пароме · Корея → Грузия` with:
   ```
   На пароме<br>Маршрут: Корея → Грузия
   ```
   rendered inside an element with inline/style rule `white-space: pre-line;` OR using the literal
   encoded line break `&#10;`/`\n` inside a `pre-line` container — the tokenizer's accepted
   contextual-transform contract already used in task_047/050 should be reused verbatim for the
   encoding choice, so behavior matches the previously accepted implementation style.
3. Symmetric UK output:
   ```
   На поромі<br>Маршрут: Корея → Грузія
   ```
4. This transform must be a function of the template macro/partial that every card (current and
   future `UA-XXXX`) passes through — never a per-card string edit. This is why the count "10"
   must never be hard-coded: the catalog-card partial iterates over whatever cards the current
   read-only discovery returns, and the two-line rule is a property of `stage == sea`, not of a
   specific card ID.
5. All other occurrences of `На пароме` / `На поромі` (status chip, filter label) and the short
   stage words `Паром` / `Пором` must be left untouched — the tokenizer's existing scoping must be
   used to distinguish "catalog-card route block" from these other three contexts, exactly as it
   already does for the prior 9-card work in task_047/050/052.
6. No substring/global replace. No changes to `sea`, `data-stage="sea"`, `stage=sea`, `?f=sea`,
   CRM/SQLite enums, IDs, URLs, analytics keys, container data, prices, specs, photos, diagnostics,
   or card links.

## Required next controller action

1. Run MEMORY PREFLIGHT against real canonical memory state.
2. Run the proven fail-closed read path against real PythonAnywhere catalog/CRM data (read-only).
3. Confirm VERIFIED_CURRENT_CATALOG_COUNT == 10, list the real IDs (including UA-0010 if present),
   and confirm no ID was invented.
4. Apply the bounded template change described above to the canonical generator only.
5. Produce isolated candidates only under `/home/Carix/autopilot_inbox`.
6. Run the full offline ferry regression suite (existing tests + the new tests listed in the task)
   with zero skips, then run the existing automated isolated Gate A.
7. Regenerate screenshots for the actual (dynamically counted) candidate set — do not assume 13.
8. Overwrite `cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json` and
   `cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md` with real, current-run evidence and
   hashes, explicitly invalidating the stale 9-card run `33152339846` as approval evidence.
9. Only then may the task move to PASS_READY_FOR_GATE_B.

## Acceptance gate — current state

- VERIFIED_CURRENT_CATALOG_COUNT: NOT_VERIFIED_BY_THIS_WORKER
- CURRENT_CARDS_PRESERVED: NOT_VERIFIED_BY_THIS_WORKER
- FUTURE_CARD_TEMPLATE_CHECK: DESIGN_SPECIFIED_NOT_EXECUTED
- TWO_LINE_RU: DESIGN_SPECIFIED_NOT_EXECUTED
- TWO_LINE_UK: DESIGN_SPECIFIED_NOT_EXECUTED
- INTERNAL_SEA_MARKERS_UNCHANGED: NOT_VERIFIED_BY_THIS_WORKER (no files touched by this worker)
- CRM_WRITE: NO
- PRODUCTION_WRITE: NO
- UA0009_SAFE_TO_PUBLISH: NO (per canonical memory, unchanged)
- UNEXPECTED_PROTECTED_CHANGES: 0 (this worker modified no protected files)

Final disposition: **BLOCKED — awaiting independent controller execution of real discovery and
real Gate A run for the 10-car state.** No fabricated PASS is issued.
