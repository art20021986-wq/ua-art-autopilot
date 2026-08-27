# CRM-SPEED-001 TEST MATRIX (round 3 corrected)

Status: package is offline-tested source, not independently executed by
Claude with a controller-grade 10-run log. Final controller execution and
verdict remain with the controller/owner per repository protocol.

## Round 3 regressions closed

| Regression (round 2 execution) | Fix | Covering test(s) |
|---|---|---|
| `test_dynamic_dispatch_blocks`: unsafe getattr-dispatched candidate accepted | Reachable call-graph scanner now flags `getattr/setattr/eval/exec/globals/locals` unconditionally; `transform_cars_ui` returns `candidate=None, status=BLOCKED` whenever any non-`direct_media_call` violation exists in the original graph | `CarsUiTransformTests.test_dynamic_dispatch_blocks`, `test_getattr_computed_name_blocks` |
| `measure_deterministic_repeat() got an unexpected keyword argument 'src'` | Single explicit signature `measure_deterministic_repeat(transform_fn, source, args=(), repeats=10)`, used identically by tests and orchestrator | `DeterministicRepeatTests.*` |
| Overflow test could never overflow because allowlist is shorter than production max | Added `max_files_per_root` parameter (test-only override); production default unchanged at 32; test explicitly sets `max_files_per_root=2` with 3 real matched files | `SiteInventoryTests.test_overflow_blocks`, `test_exact_boundary_n_passes`, `test_boundary_n_plus_one_blocks` |

## New coverage for correction A (dynamic dispatch cases)

- literal getattr dispatch -> BLOCK
- computed-name getattr dispatch -> BLOCK
- bound-method alias (`x = obj.reply_photo; x()`) -> BLOCK
- callback dict containing a media-bound attribute -> BLOCK
- callback list containing a media-bound attribute -> BLOCK
- lambda wrapping a direct media call -> BLOCK
- return-alias (`return obj.reply_photo`) -> BLOCK
- await-alias (`await sender()` where `sender = obj.reply_photo`) -> BLOCK
- nested helper making a direct, non-dynamic media call -> transform succeeds and re-scan is clean
- ambiguous dict/subscript dispatch (`dispatch_table[update.kind](update)`) -> BLOCK
- direct, simple, non-dynamic media call -> transforms to text-only and re-scan is clean

## Deterministic repeat coverage

- one deterministic transform, called positionally and with `source=` keyword, 10 repeats, all hashes/status/reasons/metadata identical
- five deliberately nondeterministic transform variants (random content, wall-clock time, UUID, unordered-set serialization, changing metadata/reason list), each proven non-deterministic across 10 repeats and each shown to force `evaluate_gate_a` to `BLOCKED` when substituted as evidence

## Site inventory coverage

- production default `MAX_FILES_PER_ROOT` remains 32 (asserted directly)
- real overflow with 3 matched files and `max_files_per_root=2`
- exact boundary N (3 matched, max=3 -> OK) and N+1 (3 matched, max=2 -> BLOCKED)
- default cap accepts up to 32 real allowed entries
- missing root -> BLOCKED
- symlink rejected

## Correction D: consolidation identity checks

- `IdentityTests` asserts `CrossProcessLock`, `RebuildQueue`, `SafeWriter`, and `SingletonGuard` resolve to the exact same class object across `canonical_modules`, the thin re-export modules (`cross_process_lock.py`, `rebuild_queue.py`, `safe_writer.py`), and `crm_speed_gate_a`.

## Correction E: end-to-end truth

- `EndToEndGateATests.test_clean_fixture_reaches_pass_awaiting_approval` builds a full synthetic fixture (required inputs, sqlite db, backup archive with matching hash, site root, mock HTTPS 404 publication probe, clean admin routes, clean usercustomize, clean rebuild source, DB-close-before-slow-work source) and calls the single public orchestration function `run_gate_a(fixture)` with no additional wiring, reaching `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` with `unmet_predicates == []` and a written `receipt.json`.
- 11 additional mutation tests each change exactly one evidence input and assert the corresponding predicate is the one that fails and the overall status becomes `BLOCKED`.

## Known scope limitations (disclosed, not hidden)

- The `CrossProcessLock` stress test exercises 25 rounds x 4 independent processes = 100 total simultaneous-contention attempts (not a single 100-round loop with more contenders); this satisfies the aggregate contention volume requested but with a different shape than a single 100-iteration two-process loop.
- `check_db_closed_before_slow_work` uses a bounded statement-order AST heuristic on an explicitly supplied anchored function source, not a full data-flow/points-to analysis across the whole real `avtoperedacha.py`/`samokontrol.py`. Applying it to the real files still requires the exact real source, which is not available inside `cloud/`; production application remains BLOCKED without that source, per the authority boundary.
- `transform_cars_ui` demonstrated against synthetic fixtures only; applying it to the real `cars_ui.py` requires the real source file, which Claude/Cloud does not fetch or execute against production.
- These limitations do not affect the specific three regressions reported by the controller for commit 73ac2b4, all of which are fixed and covered above.

## How to run

```
cd cloud/crm_speed_optimization
python3 -m py_compile *.py
python3 -m unittest test_crm_speed_gate_a -v
```

The controller is expected to run the full suite 10 consecutive times and report pass/fail counts, as in prior rounds. Claude does not fabricate that execution log here.
