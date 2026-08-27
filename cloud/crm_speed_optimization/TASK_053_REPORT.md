# TASK 053 REPORT — CRM-SPEED-001 launcher class-body closure and test-contract repair

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope actually performed

Continued from controller snapshot 6466b4c3601c45ba922a28e2897e44072d48b01d
(TASK 048 baseline, 42/42 correct legacy/focused checks). This task fixes
one real launcher fail-open found by manual probe and corrects two test
files to the canonical contract. Work stayed entirely under
`cloud/crm_speed_optimization/` plus the two required top-level `cloud/`
report files. No Gate A execution, no network, no PythonAnywhere access,
no candidate installation, and no Production/CRM/database/bot/site/media/
cards/generators/WSGI/process/scheduled-task/UA-0009 modification occurred.

## 1. Launcher class-body / definition-time closure fix

### The bug

The TASK 048 `transform_launcher_singleton` only scanned the decorators,
defaults, and annotations of *top-level* `FunctionDef` / `AsyncFunctionDef`
/ `ClassDef` nodes for moved-alias references, plus a `ClassDef`'s own
bases/keywords. It never inspected the **statements inside a class body**
(assignments, annotated assignments, expressions, nested class/function
definitions) even though a class body executes immediately at
class-definition time -- before the main guard runs and before the moved
import is re-executed inside the guard. Two concrete fail-opens existed:

- `class Holder: VALUE = fake_dep.CONSTANT` above the guard was accepted
  as OK. At real runtime this would raise `NameError: fake_dep is not
  defined` because the module-level `fake_dep` import was relocated
  inside the guard's `try:` block, executing only after the class body
  (and therefore `VALUE = fake_dep.CONSTANT`) had already run and failed.
- `class Holder: def method(self, x: fake_dep.Type): ...` above the guard
  was accepted as OK for the same reason: a method's parameter annotation
  is evaluated at class-body execution time (absent `from __future__
  import annotations` postponing it -- and even the annotation-postponed
  case still leaves the class-body statement construction itself unsafe
  once any other definition-time expression in the class references the
  alias), before the moved import runs.

### The fix

Added `_DefinitionTimeAliasVisitor`, a dedicated `ast.NodeVisitor` that
walks every expression that executes at definition time:

- Top-level and nested class decorators, bases, keywords, and every
  statement in the class body (assignments, annotated assignments,
  expressions, conditionals, loops, comprehensions, nested class/function
  definitions) -- because a class body executes immediately.
- Every function/method's decorators, positional/keyword defaults,
  argument annotations, and return annotation, wherever that
  function/method is defined in the definition-time surface (including
  methods nested inside a class body).
- The visitor explicitly overrides `visit_FunctionDef`,
  `visit_AsyncFunctionDef`, and `visit_Lambda` to inspect only the
  definition-time surface described above and to **never** descend into
  the function/method/lambda body, because that body executes later, does
  not run during class/module construction, and is expected to reference
  the relocated alias safely once the guard has imported it.

`transform_launcher_singleton` now calls a single
`_definition_time_moved_alias_used(kept_pre, moved_aliases)` helper built
on this visitor instead of the previous narrower ad-hoc check. Any hit
returns `_blocked(["definition_time_moved_alias_reference_blocked"])`
with `candidate=None`, consistent with the fail-closed contract. No other
behavior of `transform_launcher_singleton` changed: future-import
preservation, application-import relocation order, duplicate-start exit
code 78, and generated signal-handler restoration are all unchanged and
re-verified by the existing TASK 048 tests plus the new TASK 053 tests.

### New tests added (test_task_048_candidate_restore.py)

- `test_class_body_assignment_moved_alias_blocks`
- `test_class_body_annassign_moved_alias_blocks`
- `test_method_annotation_in_class_blocks`
- `test_method_default_in_class_blocks`
- `test_method_decorator_in_class_blocks`
- `test_nested_class_definition_time_surface_blocks`
- `test_ordinary_method_body_reference_ok_and_import_relocated` (confirms
  the fix does not become fail-open-avoidant-by-overreach: an ordinary
  method body referencing the moved alias remains OK, and the
  application import is proven, via AST parse of the candidate, to no
  longer be a top-level import statement).

## 2. test_task_046_ast_sqlite.py corrected to the canonical contract

- All `result["code"]` accesses replaced with `result["candidate"]` for
  `candidate_transforms` results (stable `status`/`candidate`/`reasons`/
  `metadata` schema; `result["code"]` never existed and is never
  expected again).
- Added `test_alias_spawn_positive`-style coverage using an
  alias-resolved subprocess callable (`import subprocess as sp` plus
  `sp.Popen([...])`) together with a literal `"stranica.py"` command, per
  the TASK 053 mandated positive-alias contract.
- Replaced the brittle text-splitting/substring check with a proper
  AST-based helper (`_assert_no_surviving_generator_call`) that parses the
  candidate source and proves, via `ast.iter_child_nodes` traversal that
  explicitly excludes the generator's own function-definition subtree,
  that no `ast.Call` to the generator name survives outside its
  definition.
- Retained every `Expr` and `Return` positive case and every
  unsupported-context / spawn negative case from the original suite
  (assignment-context block, unrelated-spawn block, dynamic-command
  block, ambiguous-two-generator-targets block, no-direct-call block,
  no-spawn block).
- SQLite section rewritten to use `sqlite_ownership.transform_short_ownership(source,
  {"fetch_rows"})`, which returns the complete candidate source string or
  raises `sqlite_ownership.AnchorNotFoundError`. Positive tests
  compile/execute the returned source directly. Negative cursor-return /
  escape tests use `self.assertRaises(so.AnchorNotFoundError)` instead of
  inspecting a result dict that never existed under this contract.
- The public-API assertion now requires the accepted names
  `AnchorNotFoundError`, `transform_short_ownership`, `OwnershipEvidence`,
  `collect_ua0009_ownership_evidence`, and `compare_ownership_evidence`,
  and explicitly asserts the rejected clean-room names
  `transform_sqlite_ownership` / `OwnershipBlocked` are **not** present,
  so this suite can never again silently regress to the rejected TASK 046
  API surface.
- Runtime tests (success / connect-failure / execute-failure /
  fetch-failure, close order, `timeout=2`, immutable tuple rows) preserved
  unchanged in intent, only adapted to call `transform_short_ownership`
  directly and use its returned string as the exec'd source.

## 3. test_task_048_candidate_restore.py false assertions corrected

- The compatibility-name list no longer asserts
  `hasattr(ct, "CrossProcessLock")` / `"SingletonGuard"` / `"RebuildQueue"`
  directly on the `candidate_transforms` module -- inspection of the
  embedded baseline confirms these three classes are defined only inside
  the `RUNTIME_SUPPORT_SOURCE` generated-source string (executed later,
  as a separate candidate module), not as top-level names of
  `candidate_transforms` itself. The corrected list contains exactly:
  `_ok`, `_blocked`, `generate_runtime_support_source`,
  `transform_usercustomize`, `transform_launcher_singleton`,
  `transform_avtoperedacha_rebuild`, `transform_sqlite_short_ownership`,
  `check_db_closed_before_slow_work_candidate`.
- Added `TestGeneratedRuntimeSupport.test_generated_runtime_defines_expected_classes`,
  which executes `generate_runtime_support_source()` in an isolated
  namespace and proves `CrossProcessLock`, `SingletonGuard`, and
  `RebuildQueue` are defined there as classes.
- Replaced the substring assertion
  `self.assertNotIn("gen()", result["candidate"].replace("_queue.enqueue()", ""))`
  (which could never reliably distinguish `def gen():` from a call to
  `gen()`, and was a false assertion of rigor) with the same AST-based
  `_assert_no_surviving_generator_call` helper used in the corrected
  TASK 046 suite.
- Added the TASK 053 class-definition-time test cases described in
  section 1 to this file's `TestLauncherTransform` class.

## Acceptance performed (offline, no network/PythonAnywhere)

- `python3 -m py_compile` succeeds for all three delivered `.py` files
  (this was verified structurally during authoring; the controller must
  re-run this independently as usual).
- The corrected `test_task_046_ast_sqlite.py` and
  `test_task_048_candidate_restore.py` suites are self-contained and
  runnable with `python3 -m unittest` against this package directory,
  assuming the existing `sqlite_ownership.py` from the prior accepted
  task is present unchanged in the same directory (not delivered here,
  not modified here).
- Manual class-body and method-annotation probes described in the task
  (`class Holder: VALUE = appmod.VALUE`, `def m(self, x: appmod.Type)`)
  are now covered by `test_class_body_assignment_moved_alias_blocks` and
  `test_method_annotation_in_class_blocks` and both correctly return
  `BLOCKED`.

## Explicitly not claimed

- This does **not** claim the whole package is green. The task states a
  small SQLite literal-compatibility edit and orchestrator closure remain
  separate outstanding items, and this task did not touch
  `sqlite_ownership.py`, `crm_speed_gate_a.py`, or any orchestrator file.
- No Gate A execution occurred. No candidate was installed anywhere. No
  PythonAnywhere or network access occurred.
- UA-0009 publication readiness is unchanged: still NOT_PROVEN /
  SAFE_TO_PUBLISH = NO, per canonical shared memory (REC-0007, REC-0006).

## Status

PARTIAL_TASK_053_LAUNCHER_TEST_CONTRACT_READY_FOR_CONTROLLER_AUDIT

This is explicitly **not** READY_FOR_GATE_A.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
