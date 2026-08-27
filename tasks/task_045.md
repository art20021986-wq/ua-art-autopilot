# TASK 045 — CLOSE TASK 043 SAFETY/SEMANTIC DEFECTS AND DELIVER AN EXECUTABLE REAL GATE A CONTROLLER

OWNER REQUEST: «Полная автоматическая замена текста “В море” на “На пароме” во всей системе UA ART. 9 карточек и все будущие».
PARENT_TASKS: task_042, task_043
MODE: CORRECT_EXECUTABLE_CANDIDATE / NO_PRODUCTION_WRITE
MAX_ROUNDS: 4
MEMORY_PREFLIGHT: REQUIRED.

## Independent Codex audit

Audited commit: a26fcb836337cb8f2591aa963d10d4752b5174c1.

Exact independent command:

python3 -m py_compile transform.py discover.py gate_a.py controller.py run_tests.py tests/test_transform.py tests/test_discover.py tests/test_gate_a.py tests/test_controller.py
python3 run_tests.py

Exact result:

- 45 tests;
- 44 PASS;
- 1 FAIL.

Failing test:

test_discover.TestDiscover.test_classification_of_occurrence

The fixture HTML is '<span>В море</span>'. discover.py passes the whole source line to classify_text(), so it is classified ORDINARY_PROSE instead of USER_FACING_STATUS/SHORT_STAGE. The current discovery would miss real UI labels and can false-green Gate A.

TASK 043 must not be installed or executed on PythonAnywhere.

## Additional independently verified defects

### A. Semantics and contextual transform

1. ANCHOR_MAP maps standalone «В море» to «Паром». The owner requested «В море» → «На пароме». Standalone status pill/chip must become «На пароме». Only standalone short route/timeline label «Море» becomes «Паром».
2. The old short form «Море» is absent from ANCHOR_MAP. This repeats the original TASK 040 defect and leaves the known short label unchanged.
3. The equivalent Ukrainian short route label must become «Пором» only in Ukrainian presentation context.
4. transform_html uses one lang for the entire document and therefore cannot correctly transform both data-ru and data-uk attributes on the same bilingual page. Attribute language must be selected from the attribute name, not the page default.
5. The parser claims byte-for-byte preservation but reconstructs end tags and has incomplete handling of raw start tags, single-quoted attributes, void elements and mixed RU/UA content. Prove exact preservation for every non-target byte or replace the approach with a raw-token/span patcher that only changes exact approved spans.
6. Context must distinguish:
   - status exact «В море» → «На пароме»;
   - short step exact «Море» → «Паром»;
   - long/heading route forms;
   - legacy aliases inside Python/JavaScript/config input tables — preserved;
   - ordinary prose — preserved.

### B. Real-source registry and discovery

7. CANDIDATE_REGISTRY uses unproven paths video/public/index.html, video/public/catalog.html and video/public/UA-XXXX.html. Known UA ART paths are under /home/Carix/video/, including /home/Carix/video/index.html, /home/Carix/video/katalog.html, /home/Carix/video/info.html, /home/Carix/video/podbor.html and /home/Carix/video/UA-0001.html…UA-0009.html. The tool must probe only an explicit bounded list of exact known candidates under /home/Carix/video, /home/Carix/site and proven generator/UI files; it must record which exact candidates exist.
8. The registry omits the known short label «Море», known stage route contexts, diagnostic/tracking companion pages and relevant main/catalog/card sources.
9. safe_read does not fstat after reading, does not prove size/mtime/identity remained stable after read and hashes only the truncated prefix. Truncation must BLOCK, never be accepted as a complete SHA.
10. Parent directory symlink/identity and path containment are not proven.
11. The script can raise and print a traceback instead of exactly one strict JSON BLOCKED receipt.
12. CRM query hardcodes cars(id, stage), does not safely discover real schema aliases and collects no real container/tracking/diagnostics/CTA/catalog evidence.
13. CRM/database before/after hashes and file identity are not proven.
14. Secret output scan/redaction must apply to the final serialized object, not only matched source lines.

### C. Gate A builder

15. Source reads use ordinary open after isfile/islink and have TOCTOU/symlink-parent risks.
16. build_gate_a is not bound to a signed/hashed discovery receipt and accepts arbitrary source_root/candidate_relpaths.
17. Atomic writes can overwrite a pre-existing preview file; rollback then deletes it instead of restoring it.
18. Directory fsync, destination descriptor identity and exact output allowlist are not proven.
19. determinism_check can return true for an empty/missing candidate set.
20. No mandatory exact identity set UA-0001..UA-0009, real stage distribution, catalog count, container/tracking/diagnostics/CTA/media invariants, public preview HTTP checks or protected after-hash verification exists.
21. No real generator/template candidate diff exists.

### D. Controller/workflow

22. controller.py has no real PythonAnywhere API client. It is a FakeAPI-oriented placeholder.
23. assert_command_allowed is a denylist. Any arbitrary dangerous command not containing the small forbidden token list is accepted. Commands must match one of two exact immutable full command strings/argv values, byte-for-byte.
24. receipt_path is arbitrary. It must be one exact allowlisted path per command.
25. _validate_receipt accepts missing safety fields and even an empty JSON object. All task/status/safety/path/hash/card fields must be mandatory with exact values.
26. verify_manifest is not called by run_discovery/run_gate_a and accepts an unstructured arbitrary dictionary instead of validating the real safe-inbox manifest format.
27. No exact sync-manifest path, remote script SHA binding, stale receipt defense, cleanup of remote output, API endpoint allowlist or receipt provenance exists.
28. run_gate_a is only an alias of run_discovery and does not enforce a different exact command/receipt schema.
29. workflow_template.yml is disabled and contains “real api_client wiring goes here”. It is not executable.
30. Tests do not cover exact commands, exact remote paths, real manifest format, cleanup, API endpoint allowlist, missing safety fields, empty receipt, wrong task, stale receipt, wrong nine-card set, or zero production endpoints.

## Immutable safety boundary

- Production, CRM and crm.db writes: FORBIDDEN.
- Live UA-0001..UA-0009 edits: FORBIDDEN.
- UA-0009 publication: FORBIDDEN.
- WSGI/bot/service restart, scheduled-task mutation and Gate B: FORBIDDEN.
- GitHub -> PythonAnywhere filtered safe-inbox transfer: ALLOWED.
- Exact bounded read-only discovery: ALLOWED after independent Codex audit.
- Isolated Gate A writes only to:
  - /home/Carix/video/preview/task-045-ferry-wording/
  - /home/Carix/video/reports/task-045-ferry-wording/
  - /home/Carix/autopilot_runs/task_045_ferry_wording/
- All production inputs must remain byte-identical by before/after SHA-256.
- Preserve internal sea, data-stage="sea", ?f=sea, APIs, analytics, CSS identifiers and DB enums.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## 1. Correct exact presentation mapping

Canonical contextual mapping:

| Context | Old RU | New RU | Old UA | New UA |
|---|---|---|---|---|
| status/chip/filter | В море | На пароме | У морі | На поромі |
| long | В море · Корея → Грузия | На пароме · Корея → Грузия | У морі · Корея → Грузія | На поромі · Корея → Грузія |
| heading | В море: Корея → Грузия | На пароме: Корея → Грузия | У морі: Корея → Грузія | На поромі: Корея → Грузія |
| short route/timeline | Море | Паром | Море | Пором |

For bilingual attributes, data-ru always uses RU mapping and data-uk always uses UA mapping in the same pass.

Visible fallback text uses the document/page language proven by html lang or the exact source convention; ambiguous «Море» without a proven language/context BLOCKS rather than guesses.

Mandatory exact regression fixtures must include the one-line structures actually observed in UA ART, including nested HTML where a whole source line is not equal to the label.

Prove ordinary prose, scripts, styles, comments, legacy alias tables, URLs, IDs and all non-target bytes remain unchanged.

## 2. Correct real path/source discovery

Use a fixed registry of exact candidates, no account-wide recursion. It must include when present:

- /home/Carix/video/index.html
- /home/Carix/video/katalog.html
- /home/Carix/video/info.html
- /home/Carix/video/podbor.html
- /home/Carix/video/UA-0001.html … /home/Carix/video/UA-0009.html
- exact /home/Carix/site equivalents only from an explicit list;
- exact card-specific diag/track companion candidates from an explicit bounded naming list;
- /home/Carix/stranica.py
- /home/Carix/yadro.py
- /home/Carix/master_card.py
- /home/Carix/cars_ui.py
- /home/Carix/team_bot.py
- /home/Carix/avtoperedacha.py
- /home/Carix/db.py
- /home/Carix/run_all.py
- /home/Carix/start_safe.py
- /home/Carix/crm.db

Parse HTML structurally for visible nodes and data-ru/data-uk. Parse Python/JS/template contexts without executing/importing them and preserve legacy input aliases.

All reads must use containment + parent checks + lstat + nofollow descriptor + fstat before/read/after, nlink==1, bounded complete reads, stable identity/size/mtime and full-file SHA. Oversize or concurrent change BLOCKS.

The script must always emit exactly one strict JSON object, including errors. No traceback/noise.

Discover the real CRM schema from a bounded alias allowlist read-only; require exact nine UA IDs and return only sanitized fields needed for stage, catalog identity, container/tracking, diagnostics and CTA checks. Quick-check and DB before/after identity/SHA are mandatory.

## 3. Correct discovery classification

Do not classify entire HTML source lines.

Inventory each exact occurrence with:

- file and full-file SHA;
- structural context/tag/attribute or source-literal context;
- exact old value;
- language;
- presentation form (status/long/heading/short);
- classification;
- intended candidate action;
- bounded sanitized context;
- unique stable anchor or AMBIGUOUS.

Overlapping substring matches must be deduplicated. Every occurrence of «В море», «У морі» and standalone short «Море» in approved current source files must be classified. Any required AMBIGUOUS occurrence blocks Gate A.

## 4. Correct Gate A binding and invariants

Gate A must accept only a validated discovery receipt with exact task ID, timestamp freshness, full input hashes and exact candidate paths.

Require the exact real card ID set UA-0001..UA-0009. Never invent all stages as sea.

Before any output:

- verify all source/DB hashes equal discovery;
- verify exact destination roots and no symlink/path race;
- snapshot any existing task-045 output for rollback or require a fresh empty run directory.

Use atomic fd-safe writes, fsync file and directory, and restore pre-existing task output on failure.

Generate two complete staging trees and compare byte-for-byte, then 10 canonical builds. Empty or incomplete sets fail.

Verify:

- real main/catalog/nine cards;
- real stage distribution preserved;
- catalog identity/count/filter;
- status/chip and generic route labels;
- RU and UA variants;
- container/tracking/diagnostics/CTA/media unchanged;
- future canonical generator candidate diff plus synthetic sea/legacy inputs;
- production/database/generator/live-page hashes unchanged;
- exact safe public preview/report URLs return HTTP 200.

## 5. Deliver a real exact-allowlist PythonAnywhere controller

Implement a standard-library PythonAnywhere API client using urllib with:

- account exactly Carix;
- host exactly www.pythonanywhere.com or eu.pythonanywhere.com;
- token only from PYTHONANYWHERE_API_TOKEN, never logged;
- exact documented API endpoints required for one temporary always-on/scheduled trigger and exact safe-inbox file reads/deletes;
- no generic arbitrary endpoint method exposed to orchestration;
- full timeout/rate-limit/auth handling and cleanup in finally.

The controller must internally construct commands. No caller-supplied command string.

Allow exactly two byte-identical commands:

1. one read-only discovery command for the exact safe-inbox task-045 script and fixed receipt path;
2. one isolated Gate A command bound to the exact discovery receipt/manifest and fixed Gate A receipt path.

No shell metacharacters or arbitrary paths/args. Require exact command equality before the API call.

Validate /home/Carix/autopilot_inbox/_sync_manifest.json using its real repository format and bind exact committed SHAs for every remote script.

Receipts must reject duplicate keys and require, not merely optionally inspect:

- exact task ID/mode/status;
- production_touched NO;
- crm_touched NO;
- crm_db_written NO;
- gate_b_executed NO;
- ua_0009_published NO;
- exact receipt path and fresh nonce/timestamp;
- exact script/manifest/input/output hashes;
- exact allowed roots;
- exact nine-card set;
- no secrets/PII/unrelated CRM rows;
- discovery/Gate A-specific evidence.

Empty/missing fields always BLOCK.

Always remove only the exact remote temporary trigger and exact task receipt path in finally. Never touch any other remote path.

Write locally only exact evidence/report files under cloud/task_045_ferry_wording/evidence/.

## 6. Deliver an installable reviewed workflow template

The workflow template must be complete, not pseudocode:

- workflow_dispatch only;
- permissions contents: write;
- concurrency cancel-in-progress false;
- checkout full history;
- Python 3.11;
- run py_compile + full unittest before controller;
- run exact controller with PYTHONANYWHERE_API_TOKEN;
- commit only exact task-045 evidence/report paths;
- reject unexpected staged paths;
- bounded fetch/rebase/push, no force;
- no production/Gate B/reload/restart action.

Do not install it in .github/workflows in this Claude round. Finish READY_FOR_CODEX_CONTROLLER_AUDIT.

## 7. Mandatory tests

All prior TASK 043 tests plus:

- the previously failing '<span>В море</span>' classification;
- standalone status «В море» → «На пароме»;
- standalone short «Море» → «Паром»;
- data-ru and data-uk corrected simultaneously;
- one-line real-shaped HTML;
- single- and double-quoted attributes;
- void elements, uppercase/end-tag preservation and unchanged non-target bytes;
- ambiguous «Море» language/context blocks;
- real path registry exactness (katalog, no video/public invention);
- oversize/truncated/parent symlink/hardlink/TOCTOU blocks;
- strict JSON on every error;
- CRM alias discovery, exact nine set, quick_check and SHA/identity unchanged;
- Gate A rejects receipt/hash mismatch, stale receipt, missing card, empty candidate set;
- rollback restores pre-existing output;
- exact controller commands and receipt paths only;
- arbitrary harmless-looking shell command rejected;
- empty receipt/missing flag/wrong task/wrong nine set/stale nonce rejected;
- manifest real-format/hash binding;
- API endpoint allowlist and zero production endpoints;
- cleanup on PASS/BLOCKED/timeout/malformed/auth/rate limit;
- complete workflow static assertions.

Use standard-library unittest only; no skipped/expected-failure and no background traceback.

## Deliverables

Create under cloud/task_045_ferry_wording/:

- corrected transform;
- corrected discovery;
- bound Gate A;
- real PythonAnywhere API client/controller;
- installable workflow template;
- full unittest suite;
- run_tests.py;
- TASK_045_REPORT.md;
- exact audit response table for defects 1–30;
- operator instructions;
- non-executable Gate B/rollback plan.

Update cloud/latest_status.md and cloud/owner_reply.md.

Honest finish: READY_FOR_CODEX_CONTROLLER_AUDIT. Do not claim real Gate A or production completion in this round. UA0009_SAFE_TO_PUBLISH remains NO.