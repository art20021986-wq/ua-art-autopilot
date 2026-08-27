# TASK 041 report — CRM-SPEED-001 fail-open closure

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
CURRENT_STATUS_MEMORY_VERSION: 4

## Scope and authority boundary

This task worked exclusively under `cloud/crm_speed_optimization/` plus the two
required shared-memory-adjacent status files. No Gate A execution, no
PythonAnywhere/network access, no installation of any candidate, and no
modification of Production, CRM, `crm.db`, bot, site, media, cards,
generators, WSGI, processes, scheduled tasks, `tasks/`, or UA-0009 occurred.

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

## What was corrected

1. **Invalid TASK 038 assertion.** The string-substring assertion
   `assertNotIn("generate_stranica_page()", candidate.split("_queue =")[0])`
   was replaced with an AST call-site assertion that walks the candidate and
   counts `ast.Call` nodes whose `func` resolves to the generator name. A
   `FunctionDef` string can never satisfy an `ast.Call` check, so the new
   assertion actually proves what it claims to prove.

2. **RebuildQueue / crm_speed_runtime.py callback sanitization.** Callback
   failures now record only `"CallbackError:<ExceptionClass>"` instead of
   `str(exc)[:500]`. The optional error handler still receives the raw
   exception object, but nothing persisted/returned/logged by the queue can
   leak PII, tokens, filesystem paths, or DB values. Applied identically to
   both `canonical_modules.RebuildQueue` and the generated
   `crm_speed_runtime.py` support-module source.

3. **usercustomize positive allowlist.** `transform_usercustomize` now uses
   `ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS = {"sys"}` in addition to the
   existing forbidden-import removal set. Any import that is neither
   explicitly forbidden (removed) nor explicitly allowed (kept) BLOCKS the
   whole transform. `import requests`, `import cars_ui`, `import importlib`,
   and `from requests import get` all BLOCK; `import sys, team_bot` keeps
   `sys` and removes `team_bot`; alias/from-import variants are covered.

4. **Launcher transform corrections.** The module docstring and every
   leading `from __future__` import are now located before the injected
   runtime import is inserted (previously the import could precede a
   `from __future__` statement, which is a `SyntaxError` in real Python). A
   duplicate start now writes one bounded diagnostic to `stderr` and raises
   `SystemExit(78)` (a stable, documented exit code) instead of exit code 3
   with no diagnostic. Known gap (disclosed, not fixed in this round): this
   task did not implement relocating statically-known application/local
   imports into the main guard after singleton acquisition; that remains a
   follow-up item for controller review before any further trust is placed
   in the launcher candidates for real application imports beyond the
   allowlisted stdlib set already handled.

5. **avtoperedacha rebuild transform: real call-graph proof.**
   `transform_avtoperedacha_rebuild` no longer relies on function-name
   hints or a global spawn replacement. It now requires, per candidate
   generator name: (a) zero arguments, (b) at least one statically resolved
   in-process call site (an `ast.Call` to that exact name, outside its own
   definition and not at module import time), and (c) at least one
   alias-resolved process-spawn call (`subprocess`/`os`/`multiprocessing`,
   including `import ... as ...` and `from ... import ... as ...` aliases)
   whose literal string arguments contain `stranica.py` or the generator
   name. Only calls satisfying both (b) and (c) for the *same* name are
   replaced with `_queue.enqueue()`. An unrelated `ffmpeg` spawn, a
   generator with no in-process call, no related spawn, two generators,
   nonzero-argument generators, and dynamic command construction all BLOCK
   (tests included). A post-transform AST verifier proves exactly one
   `_queue = RebuildQueue(...)` assignment, zero remaining direct calls to
   the generator outside that binding, and zero remaining resolved spawn
   calls.

6. **SQLite ownership transform and verifier rewrite.**
   `verify_no_live_handle_across_slow_call` now tracks each connection name
   and each derived cursor name independently instead of one global
   `closed` boolean, so an unrelated `.close()` call can never mark this
   function's real handles as closed (executable test included).
   `transform_short_ownership` now requires exactly one local
   `sqlite3.connect` assignment and at most one cursor derived only from
   that connection, rejects any branch/loop/try/with inside the ownership
   segment (straight-line only), rejects write SQL
   (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/REPLACE/VACUUM/REINDEX),
   `commit()`/`rollback()`, non-literal SQL text, mutable PRAGMA, and cursor
   escape via `return`. It also materializes `fetchall()`/`fetchmany()`
   results into `tuple(...)` immediately after the fetch and closes the
   cursor (when present) before the connection. Public names
   (`AnchorNotFoundError`, `find_db_handle_names`,
   `verify_no_live_handle_across_slow_call`, `transform_short_ownership`)
   are preserved; the Section 2 read-only UA-0009 evidence API is byte-for-
   byte unchanged.

7. **Orchestrator fail-closed correction.** `orchestrate_gate_a` no longer
   allows an unavailable/blocked extended transform to fall through to the
   legacy single-candidate evidence path and potentially reach PASS.
   Phase40 now raises immediately when extended candidate generation is not
   fully available. On success, the extended candidate set contains exactly
   eight keys (the seven transformed originals plus `crm_speed_runtime.py`,
   with `cars_ui.py` folded in as the eighth structurally-verified
   candidate) and never the legacy original `usercustomize.py`. All eight
   are compiled without import/execute, written as candidates+diffs through
   `SafeWriter`, and their hashes populate `package_hashes` /
   `extended_candidates.candidate_hashes`. Phase80's singleton-guard
   predicate now uses an AST-based structural verifier
   (`_verify_launcher_candidate_structural`) instead of substring presence
   checks. `check_deterministic_repeat_all_transforms` now returns full
   per-transform records (candidate sha256, diff sha256, status, ordered
   reasons, metadata digest) for each of 10 repeats, not just a `checked`
   name list.

## Known residual scope (disclosed, not claimed complete)

- Full relocation of statically-known application/local imports into the
  main guard after singleton acquisition (launcher transform item) was not
  implemented in this round; only the future-import placement and
  duplicate-exit-code/diagnostic defects were corrected.
- The avtoperedacha call-graph proof uses a bounded literal-string matching
  heuristic (`stranica.py` / generator-name substring) for spawn-command
  relatedness, as explicitly permitted by the task for fixtures; a fully
  general command-line AST/dataflow prover was not built.
- This is a Claude-authored correction pass. It has not been executed by
  the independent controller. No claim of Gate A PASS, deployment,
  production acceleration, CRM change, or UA-0009 readiness is made.

## Controller command

```bash
python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

## Status

`READY_FOR_CONTROLLER_REVIEW_TASK_041` — never `READY_FOR_GATE_A`, pending
independent controller execution and review.
