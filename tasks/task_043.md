# TASK 043 — CORRECT TASK 042 AND EXECUTE REAL READ-ONLY FERRY-WORDING GATE A

OWNER REQUEST: «Полная автоматическая замена текста “В море” на “На пароме” во всей системе UA ART. 9 карточек и все будущие».
PARENT_TASK: task_042
MODE: CORRECT_CANDIDATE / REAL_PYTHONANYWHERE_READ_ONLY_DISCOVERY / ISOLATED_GATE_A / NO_PRODUCTION_WRITE
MAX_ROUNDS: 4
MEMORY_PREFLIGHT: REQUIRED.

## Independent Codex audit of TASK 042

Verified commit: 1bb04f1f73714c20e367dd05cbbdb6142995c815.

The committed files compile and the standard-library suite reports:

- 19 tests;
- 19 PASS;
- 0 FAIL.

This is not sufficient acceptance. The suite exercises synthetic proxy fragments only. No real UA-0001..UA-0009 HTML, CRM row, generator, bot renderer, container link, diagnostics link, media file, protected hash or public preview was inspected.

Exact independently reproduced defects:

1. transform.apply_transform("Автомобиль в море уже 20 дней") returns "Автомобиль На пароме уже 20 дней". This is grammatically wrong and proves indiscriminate case-insensitive replacement.
2. transform.apply_transform("Море волнуется, паром в порту") returns "Паром волнуется, паром в порту". Ordinary prose is corrupted.
3. transform.apply_transform('<script>const legacy = "В море";</script>') rewrites the legacy input alias inside JavaScript, defeating the requirement to retain backward-compatible input aliases.
4. gate_a_preview.py gives every UA-0001..UA-0009 the same invented internal stage sea. It therefore does not validate the real nine-card stage matrix or catalog counts.
5. discover.py accepts an arbitrary root, recursively scans up to 5000 files, follows symlinked directories, has no exact source allowlist, no no-follow descriptor reads, no TOCTOU identity proof, no secret redaction, no duplicate suppression and no contextual classification. It explicitly says redaction is absent. It is not approved for live PythonAnywhere use.
6. transform.py applies global regexes to arbitrary source text. It does not parse visible HTML text/approved attributes, does not distinguish scripts/styles/input aliases/history/ordinary prose, and is not integrated with any proven real generator anchor.
7. contains_forbidden uses substring matching and cannot distinguish visible status labels from legitimate prose.
8. Gate A output uses non-atomic writes in a local package directory; it has no real PythonAnywhere preview/report allowlist, protected before/after hashes, rollback of partial output, manifest binding or receipt.
9. No real candidate patch for stranica.py, yadro.py, master_card.py, catalog/main renderers, BOT CRM renderers or any other discovered canonical source was produced.
10. UA0009_SAFE_TO_PUBLISH=NO is honest and must remain NO until real evidence passes.

TASK 042 must not advance to Gate B.

## Immutable safety boundary

- Production write: FORBIDDEN.
- CRM write and crm.db mutation: FORBIDDEN.
- Live UA-0001..UA-0009 edits: FORBIDDEN.
- UA-0009 publication: FORBIDDEN.
- WSGI reload, bot/service restart, scheduled-task changes and Gate B: FORBIDDEN.
- Do not execute/import production generators.
- Filtered GitHub -> PythonAnywhere safe-inbox transfer is allowed.
- Real bounded read-only discovery on PythonAnywhere is allowed.
- Isolated Gate A writes are allowed only under exact task-specific preview/report/staging roots:
  - /home/Carix/video/preview/task-043-ferry-wording/
  - /home/Carix/video/reports/task-043-ferry-wording/
  - /home/Carix/autopilot_runs/task_043_ferry_wording/
- Reject symlinks, hardlinks where identity cannot be proven, path escapes and any target outside these roots.
- Before/after SHA-256 for crm.db, real generators, live pages, media and UA-0001..UA-0009 must remain byte-identical.
- Preserve internal stage key sea, data-stage="sea", ?f=sea, CSS/API/analytics/database identifiers and container/tracking logic.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## 1. Replace unsafe global regex with contextual transforms

Do not transform arbitrary text.

For HTML candidates:

- parse structurally with Python 3.10 standard-library-safe logic or a reviewed dependency already proven available;
- change only visible text nodes and approved presentation attributes such as data-ru, data-uk and specific meta/JSON-LD display fields whose exact anchors are inventoried;
- never rewrite script bodies, style bodies, URLs, IDs, internal values, input aliases, historical evidence or unrelated prose;
- distinguish long status, heading and short timeline forms;
- RU outputs: «На пароме · Корея → Грузия», «На пароме: Корея → Грузия», «Паром»;
- UA outputs: «На поромі · Корея → Грузія», «На поромі: Корея → Грузія», «Пором».

For Python/templates/bot renderers:

- first discover exact file SHA and exact unique structural anchors;
- build a file-specific candidate transform or AST/token-safe transform;
- retain legacy aliases as accepted inputs;
- change only presentation constants/branches proven to render user-facing output;
- ambiguous or multiple anchors BLOCK; never guess.

Mandatory negative tests:

- «Автомобиль в море уже 20 дней» is either preserved as ordinary prose or changed only by an explicitly classified, grammatically correct context rule;
- «Море волнуется» remains unchanged;
- «Отдых на море» remains unchanged;
- JavaScript/Python legacy alias input tables retain «В море» / «У морі»;
- script/style bodies remain byte-identical;
- internal sea markers remain byte-identical.

## 2. Harden exact read-only discovery

Replace discover.py with a fail-closed PythonAnywhere tool.

It must:

- require the real account root /home/Carix and reject arbitrary roots/path variants;
- use a hardcoded bounded candidate file/dir registry based on known architecture, including exact likely generator and UI files only when present: stranica.py, yadro.py, master_card.py, cars_ui.py, team_bot.py, avtoperedacha.py, db.py, run_all.py, start_safe.py, approved video/site/public roots and UA-0001..UA-0009 pages;
- never recursively scan the whole account;
- cap files, bytes, lines, matches and output;
- lstat, reject symlink/non-regular/nlink != 1, no-follow open where supported, fstat identity before/after and stable SHA;
- open crm.db via SQLite URI mode=ro, PRAGMA query_only=ON, PRAGMA quick_check, exact UA-0001..UA-0009 query only;
- never ATTACH, VACUUM, mutate PRAGMA, write SQL or expose unrelated rows;
- redact entire lines containing secret/token/password/api-key/authorization/private-key/credential patterns and token-like shapes;
- emit exactly one strict JSON object, duplicate-key safe, with no other stdout noise;
- classify each occurrence as USER_FACING_STATUS, USER_FACING_SHORT_STAGE, LEGACY_INPUT_ALIAS, INTERNAL_IDENTIFIER, ORDINARY_PROSE, HISTORICAL_REPORT_OR_TEST_FIXTURE or AMBIGUOUS;
- include bounded sanitized context, file SHA, unique anchor evidence and intended action;
- deduplicate overlapping substring matches;
- BLOCK on unresolved AMBIGUOUS occurrences needed for a patch;
- capture real stage/card identity, catalog membership, diagnostics/tracking/container evidence for UA-0001..UA-0009 without exposing secrets or unrelated customer data.

## 3. Build real isolated Gate A

Use the discovery receipt as the only source of candidate anchors.

Create faithful isolated preview copies of:

- real main page;
- real catalog;
- real UA-0001..UA-0009 pages;
- relevant info/tracking/diagnostic pages that repeat the stage;
- BOT CRM presentation candidates as non-executed source diffs;
- proven canonical future-card generator/template candidates as non-executed source diffs.

Gate A must:

- never modify live inputs;
- copy only verified contained files needed for the preview;
- apply contextual candidate transforms to copies;
- use atomic temp + fsync + replace only inside allowed Gate A roots;
- clean incomplete staging on failure;
- generate twice and prove byte identity, plus 10-run canonical hash determinism;
- provide manifest, receipt, per-file diff, occurrence inventory, protected before/after hashes, per-card matrix and public safe preview/report URLs;
- verify public HTTP 200 only for preview/report URLs, never use this as proof of production change;
- stop at AWAITING_GATE_B when fully PASS.

## 4. Real nine-card and future-card acceptance

For each UA-0001..UA-0009, record actual evidence:

- source page path/SHA;
- real internal stage value;
- real RU/UA visible output before and candidate after;
- catalog inclusion/count and filter behavior;
- card chip;
- «Где машина сейчас» step;
- route/progress legend;
- container/tracking link unchanged;
- diagnostics link/count/state unchanged;
- CTA unchanged;
- media/local links unchanged;
- no forbidden visible status wording;
- protected source/live hashes unchanged.

Do not label all nine as sea. Cards in Kyiv, Georgia or Korea must remain their real stage and must not receive a ferry current-status pill. Their route legend may change the stage label only where the UI design contains the generic ferry step.

Future coverage must use the real discovered canonical generator candidate and at least two synthetic regression inputs:

- internal sea;
- legacy alias «В море».

No hardcoded maximum UA-0009.

## 5. Controller and automatic execution

Claude has no direct /home/Carix filesystem. Therefore deliver a reviewed GitHub Actions controller/workflow under cloud/task_043_ferry_wording/ that Codex can audit and install.

Follow the already hardened PythonAnywhere controller patterns in the repository. The controller must:

- accept only account Carix and www.pythonanywhere.com or eu.pythonanywhere.com;
- read PYTHONANYWHERE_API_TOKEN from environment and never print it;
- verify safe-inbox sync manifest binds exact script hashes;
- run only the exact read-only discovery and isolated Gate A commands;
- never call production write, WSGI reload, bot restart or Gate B endpoints;
- poll exact receipt paths;
- validate strict JSON, hashes, paths, bounds, absence of secrets and safety flags;
- clean temporary triggers/outputs in finally;
- write only task_043 evidence/report paths back to GitHub;
- include offline fake-API tests for PASS, safely BLOCKED, timeout, malformed/duplicate JSON, wrong SHA/path, secret leakage and cleanup.

Do not claim real Gate A was executed merely because the controller/template exists. Finish this Claude round at READY_FOR_CODEX_CONTROLLER_AUDIT unless independently verifiable real receipts are already supplied.

## 6. Mandatory independent-test targets

At minimum prove:

- the four ordinary-prose/script negative regressions above;
- visible-node/approved-attribute-only transforms;
- legacy alias input preservation;
- exact internal marker preservation;
- nine actual card IDs are required in real receipt;
- real stage distribution is not invented;
- catalog identity/count preservation;
- container/diagnostics/CTA/media invariants;
- future real-generator candidate;
- exact root/source allowlists;
- symlink/hardlink/path escape/TOCTOU/oversize blocks;
- secret-line redaction and final-output secret scan;
- DB read-only exact nine-card scope;
- atomic preview writes and rollback;
- 10-run deterministic output;
- protected before/after hashes;
- UA-0009 explicit readiness decision;
- no production, CRM, Gate B or publication action.

Use standard-library unittest; no pytest/pip dependency.

## 7. Deliverables

Create under cloud/task_043_ferry_wording/:

- README.md;
- corrected contextual mapping/HTML transform;
- hardened read-only discovery tool;
- real Gate A builder/runner;
- PythonAnywhere controller;
- reviewed workflow template;
- standard-library tests;
- TASK_043_REPORT.md;
- independent-audit response table covering all ten TASK 042 defects;
- exact operator/controller instructions;
- rollback/Gate B plan (non-executable without later exact approval).

Update cloud/latest_status.md and cloud/owner_reply.md.

## Honest finish states

- READY_FOR_CODEX_CONTROLLER_AUDIT — corrected package/tests complete, real controller not installed/run.
- READY_FOR_REAL_GATE_A — controller independently audited and installable, but real run not yet executed.
- AWAITING_GATE_B — only after real read-only discovery and complete isolated Gate A receipt PASS.
- BLOCKED — exact factual reason.

Do not claim 100%, live-site completion or UA-0009 publication readiness without real evidence.