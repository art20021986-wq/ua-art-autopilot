# TASK 052 REPORT — Remove TASK 050 false-green regressions from ferry Phase 1

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

This round replaces the TASK 050 `transform.py`/`discover.py` with a
re-authored implementation that restores the TASK 047 structural/tokenizer
discipline and safe-read contract, and re-adds the TASK 050 real-UI mappings
correctly, addressing every point in the TASK 052 independent audit:

| Audit item | Fixed by |
|---|---|
| 1. Prose substring corrupted | Matching is only ever against a whole, trimmed text node / attribute value, never `str.find`/regex over the raw document. |
| 2. `<script>` alias corrupted | `handle_data` returns script/style content verbatim before any pattern check. |
| 3. `data-uk` left stale / global rewrite | `data-ru` and `data-uk` are located and rewritten independently, attribute-by-attribute, inside the exact start tag only. |
| 4. Four-span sequence left AMBIGUOUS | Structural sibling tracking (`children_seq`) resolves the exact `Корея/Море/Грузия/Киев` sequence at the parent's end tag. |
| 5. Wrong UK source phrase (`В морі`) | Only the real `У морі` → `На поромі` mapping exists; a regression test asserts a fabricated `В морі` is left untouched. |
| 6. Global `result.find` loops | Removed entirely; replaced by an `html.parser.HTMLParser` subclass with an explicit context stack. |
| 7. Regressed safe reader | `safe_read_file` restores lstat regular/nlink==1, `O_NOFOLLOW`, fstat-before/after identity check, bounded read with `OVERSIZE`/`CHANGED_DURING_READ` BLOCK, full SHA256. |
| 8. Registry accepted arbitrary paths | `discover.py` uses a fixed relative registry (`HTML_CORE_PAGES`, `UA_CARD_PAGES`, `PY_MODULES`, `crm.db`) resolved against a root; the CLI never accepts an argv path — only test functions inject a temp root. |
| 9. `repr()` receipt / partial redaction | CLI emits exactly one `json.dumps(..., sort_keys=True)` receipt; `redact_obj` is applied to the whole structure before serialization, and the final JSON string is re-scanned for secret patterns (falling back to a minimal BLOCKED receipt if any remain). |
| 10. Missing real CRM schema | `check_crm` requires table `cars`, columns `auto_number` and `sea_container`, using `mode=ro` + `query_only` + `quick_check`, with DB identity verified before/after via lstat. |
| 11. `run_discovery` OK with empty inputs | The fixed registry can never be empty; missing core pages, CRM not PASS, any AMBIGUOUS UA-000X target, or zero total occurrences all force `status: BLOCKED`. |

## Deliverables

- `transform.py` — structural, non-global transform with the 052 mapping table.
- `discover.py` — fixed-registry discovery with the restored safe-read contract and real CRM schema check.
- `tests/test_transform.py` — 27 test methods covering the audit's five failing examples plus baseline TASK 047 protections (script/style/comment, entity, ordinary prose) and the new structural contexts (chip, status-pill, etap+tut/krug, four-span, data-ru/data-uk).
- `tests/test_discover.py` — 19 test methods covering the fixed registry, safe-read contract (nlink/symlink/oversize/missing), CRM schema/identity, strict JSON, secret redaction, determinism, and required-marker presence.
- `run_tests.py` — runs the full discovered suite twice from any cwd and reports `RESULT: PASS total_tests_per_run=N` or `RESULT: FAIL`.

## Honesty about verification in this environment

This Claude/Cloud worker environment has no code-execution tool available to
this response channel — only file authoring. The code above was written and
manually traced line-by-line against every audit example and every mandated
test case listed in the task (including re-deriving the exact expected
output string for each of the five audit HTML snippets and each context rule)
to maximize confidence, but **no actual `python3 run_tests.py` invocation was
performed by this worker**, and no PythonAnywhere execution, Gate A, Gate B,
CRM write, or production write of any kind occurred. Per the no-fabrication
rule, this report does not claim a verified pass count; it claims only that
the suite was authored to satisfy every mandatory test named in the task.

**Required next step for Codex/CI**: execute `python3 run_tests.py` (from any
cwd) inside `cloud/task_047_ferry_discovery/` twice, confirm `RESULT: PASS`,
and record the exact test count in the canonical memory before treating this
round as accepted. If any test fails, that is expected review feedback, not
a production incident — nothing here touches PythonAnywhere/CRM/production.

## Safety markers

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

## Status

READY_FOR_CODEX_PHASE1_FINAL_AUDIT. UA0009_SAFE_TO_PUBLISH remains NO. This
is an offline code-authoring deliverable, not a completed production or CRM
discovery run.
