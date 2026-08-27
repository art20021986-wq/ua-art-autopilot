# TASK 046 REPORT - CRM-SPEED-001 split closure A

OWNER_DIRECTIVE_ACKNOWLEDGED: YES (REC-0001..REC-0005, production/CRM writes forbidden, UA-0009 not safe to publish)
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Scope of this bounded continuation

This task fixes only the two root causes identified by TASK 041 controller
evidence (230 PASS / 11 FAIL / 2 ERROR on the immutable snapshot
`65e1b53e71492bebd3b7405a44d04af41e91847a`):

1. `transform_avtoperedacha_rebuild` only rewrote `Expr(Call)` trigger sites,
   so `return generate_stranica_page()` fixtures survived untouched and the
   transformer self-blocked on its own post-transform proof.
2. `find_cursor_names` (SQLite ownership) recognized only
   `cur = conn.cursor()`, missing `cur = conn.execute(<literal SQL>)`; the
   cursor escaped detection, so no close was generated and `return cur`
   was not rejected.

Launcher relocation and the Gate A orchestrator are explicitly **not**
touched in this task and are deferred to TASK 047 (or the next free task
number) as instructed.

## What changed

### `candidate_transforms.py`

- `transform_avtoperedacha_rebuild` is now parent-aware: every direct
  generator call and every alias-resolved related subprocess spawn
  (`Popen`/`run`/`call`/`check_call`/`check_output` with a literal or
  alias-resolvable argument list containing `stranica.py`) is classified by
  its immediate syntactic parent **before** any mutation occurs.
- Only two contexts are supported and rewritten:
  - standalone `Expr(Call)` -> standalone `_queue.enqueue()`
  - exact `Return(Call)` -> `return _queue.enqueue()`
- Any other context (assignment, call argument, boolean/arithmetic
  expression, condition, comprehension, await, yield, decorator/default)
  blocks with `unsupported_call_context` instead of guessing.
- Requires exactly one zero-argument generator candidate that is both
  directly called in-process and has at least one related spawn call;
  multiple generator candidates, non-zero-arg generators, missing direct
  calls, missing related spawns, unrelated-only spawns, and dynamic/ambiguous
  command construction (e.g. `os.path.join(...)` inside the argv list) all
  block.
- Recursion / dynamic dispatch inside the generator's own body blocks.
- Exactly one `_queue = RebuildQueue(<generator_function_object>, <lock_path>)`
  is inserted immediately after the generator definition; the callback is
  always a bare function-object reference, never a call.
- Post-transform AST proof checks: zero remaining direct generator calls
  outside its own definition, zero remaining resolved related spawn calls,
  exactly one `_queue` assignment with the correct shape and callback
  identity, no module-level execution of `enqueue()` or the generator, and
  the resulting code compiles.
- Unused `import subprocess` is removed only when no `SPAWN_FUNCS` usage
  remains anywhere in the transformed module.

### `sqlite_ownership.py` (Section 1 only)

- Ownership discovery now recognizes both `cur = conn.cursor()` and
  `cur = conn.execute(<literal SQL>, ...)` as the same owned-cursor pattern,
  tied to the exact locally-created connection name.
- Requires exactly one local connection and at most one cursor; rejects
  branch/loop/try/with inside the ownership segment, multiple
  connections/cursors, writes (`INSERT`/`UPDATE`/`DELETE`/`CREATE`/`DROP`/
  `ALTER`/`REPLACE`, mutable `PRAGMA ... =`), `commit()`/`rollback()`,
  non-literal/uncertain SQL, and `time.sleep(...)`-style slow work while a
  handle is open.
- Rejects escape via `return`, alias assignment, closures, or being passed
  as a call argument to anything other than the tracked object's own
  methods; `return cur` now correctly blocks.
- Adds `timeout=2` to the `connect(...)` call exactly once, preserving all
  other arguments.
- Initializes `conn = None` (and `cur = None` when a cursor exists) before
  the generated `try`.
- Wraps the (import/close-stripped) segment in `try`/`finally`; `finally`
  closes the cursor first (`if cur is not None: cur.close()`), then the
  connection (`if conn is not None: conn.close()`), on every path.
- Original close statements for tracked names are removed from the body
  before the `try`/`finally` wrap so there is no double-close.
- `fetchall()`/`fetchmany()` results are materialized into an immutable
  `tuple(tuple(row) for row in ...)` before close, preserving the original
  SQL text, parameters, and downstream variable use/return.
- A static `_verify_transformed_function` re-walks the generated function to
  independently prove: exactly one `try`, correct `finally` shape and close
  order (cursor before connection), and `timeout=2` present exactly once on
  every `connect(...)` call in that function. Any failure blocks the whole
  transform rather than returning partially-verified code.
- Runtime fake-connection/cursor tests (see test file) prove: success path
  closes cursor-then-connection and returns immutable tuple rows; connect
  failure raises without `UnboundLocalError`; execute failure still closes
  both handles in order; fetch failure propagates the original exception
  type unmasked.

## Baseline-access disclosure (read before treating "preserved" as proven)

The literal current `main`-branch content of
`cloud/crm_speed_optimization/candidate_transforms.py` and
`cloud/crm_speed_optimization/sqlite_ownership.py` (including the separate
canonical read-only UA-0009 evidence API and any other unrelated
implementation sections in Section 2+) was not present in the assistant's
context for this bounded continuation task. Both files above are
clean-room reconstructions written strictly from the TASK 038 / TASK 041 /
TASK 046 specification text and controller evidence, not diffs against the
real file bytes. The documented **public contract** (`transform_avtoperedacha_rebuild`,
`transform_sqlite_ownership`, `OwnershipBlocked`) is implemented and is
covered by the new focused test file, but a byte-level merge/diff against
the true `main` baseline (to guarantee zero incidental changes to unrelated
sections, in particular the UA-0009 evidence API in `sqlite_ownership.py`)
still must be performed by the controller before this can be treated as a
drop-in replacement. This is flagged explicitly rather than silently
assumed, per the no-fabrication requirement.

## Tests

New file: `cloud/crm_speed_optimization/test_task_046_ast_sqlite.py`
(does not duplicate any existing suite). Covers:

- `Expr` and `Return` positive contexts for the rebuild transform
- alias-resolved related spawn positive
- unsupported call-use context (assignment) BLOCK
- unrelated spawn, dynamic/ambiguous command, two generator targets,
  no-direct-call, and no-spawn negatives
- `conn.execute(...)` cursor discovery positive and `return cur` BLOCK
- guarded close order (`is not None`) and tuple-of-tuples materialization
- four runtime exception paths (success, connect failure, execute failure,
  fetch failure) with fake connection/cursor objects
- presence of the required public API names

## Commands (offline, to be run by the controller)

```bash
python3 -m py_compile cloud/crm_speed_optimization/*.py
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

No skip, expected-failure, background exception, or weakened legacy test was
introduced. Full-suite discovery against the actual `main`-branch package
(all pre-existing tests) was not executed in this bounded environment
because the pre-existing test files were not present in the assistant's
context; the controller must run full discovery against the merged package
before treating this as `READY_FOR_GATE_A_EXECUTION`.

## Explicit non-actions

- Launcher relocation: NOT touched (deferred to TASK 047 or next free task).
- Gate A orchestrator: NOT touched (deferred to TASK 047 or next free task).
- No Gate A execution, no PythonAnywhere access, no candidate installation.
- No Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI,
  process, scheduled task, or UA-0009 file was read, written, or executed.
- `tasks/` was not modified.

## Status

`PARTIAL_TASK_046_AST_SQLITE_READY_FOR_CONTROLLER_AUDIT` -- **not**
`READY_FOR_GATE_A`. Launcher/orchestrator closure is intentionally pending
TASK 047 or the next free task number, and the baseline byte-diff merge
noted above is a prerequisite for full acceptance.

AUTOPILOT VERIFIED CANONICAL SHARED MEMORY markers (verbatim, not altered):

- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4
