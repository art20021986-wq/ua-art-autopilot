# TASK 042 — UA ART: FULL AUTOMATIC DISPLAY REPLACEMENT «В море» → «На пароме»

OWNER REQUEST: «Полная автоматическая замена текста “В море” на “На пароме” во всей системе UA ART. 9 карточек и все будущие».
MODE: SANDBOX_GATE_A / AUTOMATIC_PIPELINE / NO_PRODUCTION_WRITE
MAX_ROUNDS: 4
PARENT_TASK: task_040 (queue-safe reissue; the original run was cancelled before checkout by GitHub pending-run replacement).\nDEPENDS_ON: task_041 must finish or reach a safe terminal state; the workflow queue must preserve task order.
PROJECT_SCOPE: UA-0001..UA-0009 and every future UA-XXXX card.
MEMORY_PREFLIGHT: REQUIRED.

## Objective

Replace every user-facing Russian delivery-stage label based on «В море» with the approved wording «На пароме» throughout UA ART, and make the replacement permanent for all future cards by correcting the canonical rendering/generator path.

The correct Ukrainian user-facing equivalent is «На поромі».

This task must fix the source of future output, not merely patch the nine current HTML files.

## Immutable safety boundary

- Production write is forbidden in this task.
- CRM and /home/Carix/crm.db writes are forbidden.
- Do not edit live UA-0001..UA-0009 pages.
- Do not publish UA-0009.
- Do not reload WSGI, restart bots/services, change scheduled tasks, or execute Gate B.
- GitHub -> PythonAnywhere filtered safe-inbox transfer is allowed.
- A bounded read-only PythonAnywhere discovery and isolated Gate A preview are allowed only through the already reviewed safe path.
- Gate A may write only to a new isolated preview/report/staging namespace dedicated to task_042.
- Preserve before/after SHA-256 for CRM, production generators, live site/card pages, media, and UA-0001..UA-0009. All must remain byte-identical.
- Any unexpected protected change blocks the task.
- Internal stage identifiers must remain stable: sea, data-stage="sea", ?f=sea, CSS class names, analytics keys, API/database enums and existing container/tracking logic must not be renamed unless a proven compatibility layer requires it.
- Do not migrate stored CRM data in Gate A. Prefer a centralized display mapping that remains compatible with legacy stored values.

Required final safety markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Required discovery

Perform bounded, read-only discovery of the exact real source paths under /home/Carix. Search the approved source set, current public HTML, preview/templates, bot/CRM UI renderers, and generator chain for exact and grammatical display variants, including:

- В море
- В море:
- В море ·
- в море
- Море
- Море:
- У морі
- У морі:
- у морі

Also identify already-correct occurrences:

- На пароме
- на пароме
- Паром
- На поромі
- на поромі
- Пором

Classify every occurrence before changing a candidate:

1. USER_FACING_STATUS — must use «На пароме» / «На поромі».
2. USER_FACING_SHORT_STAGE — must use «Паром» / «Пором».
3. LEGACY_INPUT_ALIAS — keep only as accepted backward-compatible input; never render it back to users.
4. INTERNAL_IDENTIFIER — preserve, for example sea and data-stage="sea".
5. ORDINARY_PROSE — review grammatically; do not blindly corrupt legitimate phrases unrelated to the delivery-stage label.
6. HISTORICAL_REPORT_OR_TEST_FIXTURE — preserve only when the old wording is intentionally asserted as forbidden input/history; document why.

Discovery must produce a deterministic occurrence inventory with file, bounded line/anchor, class, intended action, and SHA-256. Secret-bearing lines must be redacted.

## Canonical future-card behavior

Implement one centralized, tested presentation mapping for the sea/ferry stage.

It must:

- accept stable internal key sea;
- accept proven legacy display/input aliases for backward compatibility, including «В море», «Море», and «У морі» where the real system currently receives them;
- render Russian long label «На пароме · Корея → Грузия» or the exact context-appropriate approved form;
- render Russian heading «На пароме: Корея → Грузия» where a colon heading is used;
- render Russian short label «Паром» in timelines/progress legends;
- render Ukrainian long label «На поромі · Корея → Грузія» or the matching context form;
- render Ukrainian heading «На поромі: Корея → Грузія»;
- render Ukrainian short label «Пором»;
- never render «В море», «Море» as the current-stage label, «У морі», or stale mixed-language equivalents;
- preserve filters, counts, URLs, tracking/container behavior and stage selection;
- be idempotent: applying the transform twice produces byte-identical candidates;
- be deterministic across at least 10 repeated builds.

Correct the real canonical generators/templates/renderers found by discovery, including future-card paths. Do not assume names; prove exact anchors before transformation. Ambiguous or multiple competing renderers must be reported and resolved in the candidate without importing/executing production modules.

## Required UI surfaces

The Gate A candidate must cover every real applicable surface found, at minimum:

- main page stage card and stage count;
- catalog filter button;
- catalog card status pill;
- UA-0001..UA-0009 card status chip;
- «Где машина сейчас» current-step text;
- route/timeline/progress legend;
- RU/UA data attributes and visible fallback text;
- relevant SEO title/description/OpenGraph/structured-data text if the status appears there;
- tracking/diagnostics companion pages if they repeat the stage;
- BOT CRM buttons, menus, card editor, summaries or notifications that display the stage;
- generators, templates and constants used by future UA-XXXX cards;
- tests/validators so stale wording fails closed.

Do not change unrelated prose merely because it contains the noun «море».

## Real nine-card and future-card Gate A matrix

Create faithful isolated previews for UA-0001..UA-0009 using read-only real evidence.

For each card record:

- real source found or exact NOT_PROVEN reason;
- internal stage key/value before;
- Russian visible output;
- Ukrainian visible output;
- catalog output;
- card output;
- timeline/progress output;
- container/tracking behavior unchanged;
- diagnostics behavior unchanged;
- no forbidden visible wording;
- links/media remain valid;
- source/live hashes unchanged.

Also keep at least two clearly synthetic regression fixtures:

- one future card whose internal stage is sea;
- one future card supplied with a proven legacy alias such as «В море».

Both future fixtures must render the new wording and preserve filtering by sea. The implementation must be generic for UA-XXXX and must not contain a hardcoded upper limit of 0009.

## Acceptance tests

All tests must use Python standard library where practical and run offline against candidates/fixtures.

Mandatory assertions:

1. Every UA-0001..UA-0009 preview is generated and checked.
2. Future UA-XXXX fixtures render «На пароме» / «На поромі».
3. No visible Russian output contains exact status label «В море» or short current-stage label «Море».
4. No visible Ukrainian output contains stale status label «У морі».
5. Legacy aliases remain accepted only as inputs and normalize to internal sea.
6. sea, data-stage="sea", ?f=sea and filter behavior remain unchanged.
7. Catalog counts and nine-card identity set remain unchanged.
8. Existing UA-0001..UA-0008 remain protected; UA-0009 is not published.
9. Container/tracking and diagnostics links/counts are unchanged except for cache-busting bytes proven unrelated to content, if any.
10. Syntax/HTML structure checks pass.
11. Candidate transform is idempotent.
12. Ten builds are byte-deterministic.
13. No zero-byte files, symlinks, path escapes, arbitrary recursion, secrets, or unsafe URLs.
14. CRM quick_check passes read-only and CRM bytes/hash remain unchanged.
15. Production generators/pages/media before and after hashes are identical.
16. Forbidden-word scan distinguishes intentional legacy input fixtures/tests from user-visible output.
17. A test fails if a future generator reintroduces the stale wording.

## Progress and online evidence

Produce evidence-backed milestone reports only after each checkpoint is actually reached:

- 20%: memory preflight, real-source discovery and occurrence inventory;
- 40%: canonical mapping and exact candidate transforms prepared;
- 60%: UA-0001..UA-0009 preview matrix built;
- 80%: future-card, idempotence, 10-run, protected-hash and regression tests passed;
- 100%: only if the complete Gate A candidate passes and a reachable safe preview/report exists.

Maintain a compact machine-readable progress JSON and owner-facing Russian status under cloud/task_042_ferry_wording/ plus cloud/latest_status.md and cloud/owner_reply.md.

Do not claim 100% from code generation alone. If PythonAnywhere Gate A has not run, the maximum honest status is READY_FOR_GATE_A or BLOCKED.

## UA-0009 mandatory decision

The final report must explicitly include:

- UA0009_SAFE_TO_PUBLISH: YES or NO;
- evidence for card generation, catalog inclusion, filters, unique identity/VIN where available, stage label, CTA, diagnostics, tracking/container, links/media, and protected hashes;
- the exact remaining blocker if NO.

This task never publishes UA-0009.

## Deliverables

Create a self-contained task package under cloud/task_042_ferry_wording/ containing:

- README.md;
- bounded read-only discovery/inventory tool;
- deterministic candidate transform or patch builder;
- Gate A preview builder/runner;
- tests covering the nine real cards and future UA-XXXX;
- occurrence inventory;
- before/after manifest and protected hashes;
- per-card acceptance matrix;
- milestone progress reports;
- TASK_042_REPORT.md;
- rollback/Gate B plan that is not executable without a later exact owner approval.

Update cloud/latest_status.md and cloud/owner_reply.md in the mandatory repository format.

## Finish states

Valid terminal states:

- READY_FOR_CODEX_AUDIT — candidate and offline tests complete, PythonAnywhere Gate A not yet executed;
- AWAITING_GATE_B — only after the full bounded Gate A passes and safe preview/report evidence is reachable;
- BLOCKED — with exact factual blockers.

Never state that the live website, CRM, bot, nine cards, or future generator has been changed until a later separately authorized Gate B is executed and verified.