# TASK 046 — CRM-SPEED-001 split closure A: rebuild AST and SQLite ownership

## Purpose

TASK 044 failed before commit only because the Claude response reached the configured 128000 output-token ceiling. This is the first bounded continuation. Fix only the rebuild AST transformer and SQLite ownership subsystem. Do not work on launcher relocation or the Gate A orchestrator in this task; those will be handled in a separate continuation after controller audit.

Use the current `main` versions as the baseline. Preserve all public APIs and every unrelated implementation section.

## Immutable safety boundary

Work only under `cloud/crm_speed_optimization/` plus `cloud/latest_status.md` and `cloud/owner_reply.md`. Claude authors every implementation change.

Do not execute Gate A, access PythonAnywhere/network, install candidates, or modify Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Tests must be offline and temporary-directory-only. Do not modify `tasks/`.

Required markers in report/status/reply:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

Return complete files only and keep the response bounded. Do not return unchanged test suites or unrelated package files.

## Controller evidence from TASK 041

The exact immutable snapshot `65e1b53e71492bebd3b7405a44d04af41e91847a` compiled, but full discovery was 230 PASS / 11 FAIL / 2 ERROR. The two root causes in this task are:

1. `transform_avtoperedacha_rebuild` rewrites only `Expr(Call)`. Fixtures use `return generate_stranica_page()`, so the direct call survives and the transformer blocks itself.
2. `find_cursor_names` recognizes `cur = conn.cursor()` but not `cur = conn.execute(...)`; cursor escape is missed and cursor close is not generated.

Fix causes, not assertions. Preserve all strong negative tests.

## A. Parent-aware rebuild transformation

In `candidate_transforms.transform_avtoperedacha_rebuild`:

- require exactly one zero-argument generator candidate, at least one exact direct in-process call, and at least one alias-resolved literal related spawn containing `stranica.py`;
- unrelated ffmpeg/other spawn, dynamic command construction, ambiguity, two targets, nonzero generator args, no direct call, or no related spawn must remain BLOCKED;
- classify every direct generator call and every resolved spawn call by immediate parent/context before modifying the tree;
- support only:
  - standalone `Expr(Call)` -> standalone `_queue.enqueue()`;
  - exact `Return(Call)` -> `return _queue.enqueue()`;
- any relevant call used in assignment, another call argument, boolean/arithmetic expression, condition, comprehension, await, yield, decorator/default, or any other context must BLOCK rather than guess;
- exclude the generator definition body from trigger replacement, but reject recursion or dynamic dispatch;
- replace every supported in-process and related-spawn trigger;
- insert exactly one `_queue = RebuildQueue(generator_function_object, lock_path)` after the generator definition; callback must be a function object, never a call;
- preserve docstring/future-import validity and remove only spawn imports that are truly unused after transformation;
- post-transform AST proof must establish:
  - zero direct generator calls outside its own definition,
  - zero resolved spawn calls,
  - exactly one `_queue` assignment,
  - exact callback identity,
  - no module-level enqueue/callback execution,
  - candidate compiles.

The existing TASK 038 positive fixture and TASK 041 aliased-subprocess fixture must return OK. Do not weaken their assertions.

## B. SQLite exact ownership and exception safety

Rewrite only Section 1 of `sqlite_ownership.py`; preserve the separate canonical read-only UA-0009 evidence API and all public names.

- recognize a cursor assigned by either `cur = conn.cursor()` or `cur = conn.execute(literal_readonly_sql, ...)`, owned by that exact locally-created connection;
- require exactly one local connection and at most one exact cursor;
- reject return/pass/store/alias/closure escape of connection or cursor, including `return cur`;
- reject caller-owned handles, multiple connections/cursors, branch/loop/try/with in the ownership segment, writes, commit/rollback, mutable PRAGMA, nonliteral or uncertain SQL, and slow work while a handle is open;
- add `timeout=2` exactly once without altering other connect arguments;
- before generated `try`, initialize owned names safely (`conn = None`, and `cur = None` when present);
- generated `finally` must guard closes with `is not None`, close cursor first, then connection, on success and every exception path;
- remove/reconcile original closes for tracked names so there is no double-close or later close after slow work;
- materialize `fetchall`/`fetchmany` as an immutable tuple of immutable row-tuples before close, preserving SQL text, parameters, result variable use and return;
- the verifier must track each exact owned connection/cursor independently and prove both closed before every slow call.

Runtime fake connection/cursor tests must cover success, connect failure, execute failure and fetch failure. They must prove no `UnboundLocalError` or exception masking, cursor-before-connection close order, timeout exactly once, original SQL/parameters, immutable rows and no double close.

## Tests

Add one compact focused file `test_task_046_ast_sqlite.py`. Do not copy existing suites into it. It must cover:

- Expr and Return positive contexts;
- alias-spawn positive;
- unsupported call-use contexts BLOCK;
- unrelated/dynamic/ambiguous/no-direct/no-spawn negatives;
- `conn.execute` cursor discovery and `return cur` BLOCK;
- guarded close order and tuple-of-tuples;
- the four runtime exception paths;
- preservation of existing public APIs.

Run offline:

```bash
python3 -m py_compile cloud/crm_speed_optimization/*.py
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

No skip, expected failure, background exception, or weakened legacy test is allowed.

## Deliverables — exactly these seven files

1. `cloud/crm_speed_optimization/candidate_transforms.py`
2. `cloud/crm_speed_optimization/sqlite_ownership.py`
3. `cloud/crm_speed_optimization/test_task_046_ast_sqlite.py`
4. `cloud/crm_speed_optimization/TASK_046_REPORT.md`
5. `cloud/latest_status.md`
6. `cloud/owner_reply.md`

Correction: the exact deliverable count is six, as listed above. Do not emit any seventh file.

Status must be `PARTIAL_TASK_046_AST_SQLITE_READY_FOR_CONTROLLER_AUDIT`, never `READY_FOR_GATE_A`. State clearly that launcher/orchestrator closure is intentionally pending TASK 047 or the next free task number.