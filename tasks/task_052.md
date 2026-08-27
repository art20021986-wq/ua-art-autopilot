# TASK 052 — REMOVE TASK 050 FALSE-GREEN REGRESSIONS FROM FERRY PHASE 1

OWNER REQUEST: replace «В море» with «На пароме» across all 9 UA ART cards and all future cards.
PARENT_TASKS: task_047, task_050
MODE: PRECISE_BASELINE_RESTORE_AND_EXTENSION / NO_PRODUCTION_WRITE
MAX_ROUNDS: 3

## Independent audit: TASK 050 is NOT accepted

Commit audited: 7afe14977fe31f6ce0d28f2fbf45be3fb9aa1b5d.

python3 run_tests.py reports 32/32 PASS twice, but manual executable checks prove false-green behavior:

1. <p>Автомобиль В море уже 20 дней</p>
   becomes <p>Автомобиль На пароме уже 20 дней</p>.
2. <script>const legacy="В море";</script>
   becomes <script>const legacy="На пароме";</script>.
3. <div data-ru="В море" data-uk="У морі">В море</div>
   leaves data-uk stale and globally changes other text.
4. <div style="display:flex"><span>Корея</span><span>Море</span><span>Грузия</span><span>Киев</span></div>
   remains unchanged and only records AMBIGUOUS.
5. Ukrainian map incorrectly uses «В морі» instead of the actual «У морі».
6. transform_html globally calls result.find("В море") over arbitrary HTML; it is not structural and rewrites prose/scripts/styles/comments/legacy aliases.
7. discover.py regressed safe reading: ordinary exists/islink/open replaces the prior lstat + O_NOFOLLOW + nlink + size + fstat before/after full-read contract.
8. discover.py removed the fixed /home/Carix registry and accepts arbitrary path lists.
9. discover.py serializes receipt with repr(), not strict JSON; secret redaction is applied only to a side string while original receipt fields remain unredacted.
10. read_crm_verified allowlists do not include verified real schema evidence from TASK 049: table cars, identity auto_number, container sea_container.
11. run_discovery can be OK with empty paths/empty ids and missing required real inputs.

## Exact trusted baselines to recover, not rewrite from scratch

From commit 8d0b37bd62416e8587dd2dddef4ecedca6ddfe52:

- cloud/task_047_ferry_discovery/transform.py blob SHA 90c336c7dcd9da7cb8da77faf36ff31a866afa1c
- cloud/task_047_ferry_discovery/discover.py blob SHA 6626995ed7fb26f4c0664a49b5d9f7237609c65c

Restore their structural tokenizer, script/style protection, fixed registry and safe read contract first. Then add the TASK 050 real UI contexts without weakening those invariants.

Do not preserve TASK 050's global regex/find loops or regressed file reader.

## Safety

No PythonAnywhere execution. No production/CRM/database/site/card/generator write. No UA-0009 publication, restart, schedule change or Gate B.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Correct transform requirements

Use structural token/span processing outside script/style/comment only.

Exact mappings:

- status: В море -> На пароме; У морі -> На поромі;
- long: В море · Корея → Грузия -> На пароме · Корея → Грузия;
- heading status: В море: ... -> На пароме: ...;
- route heading: Море: Корея → Грузия -> Паром: Корея → Грузия;
- info: Море Корея → Грузия — около 60 дней -> Паром Корея → Грузия — около 60 дней;
- short proven RU: Море -> Паром;
- short proven UK: Море -> Пором.

Handle data-ru and data-uk independently in one pass.

Recognize real exact contexts:

- class chip;
- status-pill;
- class etap tut with nested krug;
- exact four sibling spans Корея / Море / Грузия / Киев even without classes;
- data-ru/data-uk;
- exact info phrases.

Never replace a substring inside longer prose. Preserve scripts, styles, comments, ordinary prose and legacy alias/config tables byte-identically.

Any target-like standalone «Море» outside proven context remains unchanged and is AMBIGUOUS.

Preserve all non-target bytes. Add exact executable regressions for the four audit examples above.

## Correct discovery requirements

Restore fixed registry relative to exact /home/Carix:

- video/index.html, video/katalog.html, video/info.html, video/podbor.html;
- video/UA-0001.html through UA-0009.html;
- explicit site equivalents and bounded diag/track candidates;
- stranica.py, yadro.py, master_card.py, cars_ui.py, team_bot.py, avtoperedacha.py, db.py, run_all.py, start_safe.py;
- crm.db.

No environment-selected arbitrary production root in CLI. Test functions may inject a temp root explicitly.

Restore and retain:

- containment and parent symlink checks;
- lstat regular/nlink==1;
- O_NOFOLLOW;
- fstat before and after;
- stable dev/inode/size/mtime_ns;
- complete bounded read, oversize/truncation/change BLOCK;
- full SHA only.

Refactor that same verified reader to optionally return raw bytes internally for structural inventory; never serialize raw bytes.

HTML inventory uses corrected structural transform in ANALYZE mode, not active global replacement. Python inventory uses AST/tokenize without import/execute.

Always emit exactly one strict json.dumps receipt from CLI. Never repr. Redact occurrence contexts before insertion. Scan final JSON; if secret-like material remains, emit a minimal BLOCKED receipt without original evidence.

Overall BLOCKED if required core pages are missing/blocked, CRM is not PASS, any required target is AMBIGUOUS, exact nine IDs are absent, or zero source occurrences are found.

## Real CRM schema contract

Incorporate verified evidence:

- table: cars;
- UA identity column: auto_number;
- container column: sea_container.

Use bounded aliases only when exact known columns are absent, and ambiguity blocks.

Require exact ids UA-0001..UA-0009, exactly one row each. Return sanitized stage/container/tracking/diagnostics/CTA fields only when present from an allowlist.

Use SQLite mode=ro, query_only, quick_check and verified full DB identity/SHA before and after. No writes/ATTACH/VACUUM/mutable PRAGMA.

## Tests: preserve and expand, never delete coverage

Restore all 48 TASK 047 tests plus TASK 050 additions. Add the four exact audit regressions.

Mandatory:

- ordinary mixed-case phrase preserved;
- script alias preserved;
- data-ru and data-uk both corrected;
- real four-span sequence corrected;
- «У морі» corrected;
- all script/style/comment/history tests;
- fixed registry;
- O_NOFOLLOW/nlink/oversize/TOCTOU;
- strict JSON and secret redaction;
- real cars/auto_number/sea_container fixture;
- exact nine required; empty inputs block;
- run_tests.py succeeds from another cwd;
- two full deterministic test runs.

No skipped/expected failure. Report exact test count and command.

## Deliverables

Modify/create exactly:

- `cloud/task_047_ferry_discovery/transform.py`
- `cloud/task_047_ferry_discovery/discover.py`
- `cloud/task_047_ferry_discovery/tests/__init__.py`
- `cloud/task_047_ferry_discovery/tests/test_transform.py`
- `cloud/task_047_ferry_discovery/tests/test_discover.py`
- `cloud/task_047_ferry_discovery/run_tests.py`
- `cloud/task_047_ferry_discovery/TASK_052_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Finish READY_FOR_CODEX_PHASE1_FINAL_AUDIT. Do not claim real PythonAnywhere discovery/Gate A/production completion. UA0009_SAFE_TO_PUBLISH remains NO.