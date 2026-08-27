# TEST_MATRIX — CRM-SPEED-001 Gate A (round 2, task_025)

This matrix supersedes the round-1 matrix rejected by the controller
(commit 6207fc5a6b1f540475116d646261f37181a6bb22: flaky stale-takeover
test, atexit FileNotFoundError, fabricated True predicates).

## 1. CrossProcessLock

| Test | Behavior proven |
|---|---|
| test_clean_acquire_release | normal lifecycle |
| test_repeated_release_is_idempotent | release() never raises when called twice |
| test_release_after_run_dir_removed_does_not_raise | explicit + simulated atexit release after directory deletion never raises |
| test_explicit_release_unregisters_atexit | atexit callback removed on explicit release |
| test_foreign_token_release_does_not_delete_file | owner-only release respected |
| test_stale_dead_pid_takeover | dead PID stale lock is taken over |
| test_pid_reuse_start_time_mismatch_treated_as_dead | PID-reuse evidence correctly distinguishes a different process |
| test_live_duplicate_is_rejected | live owner blocks a second acquirer |
| test_exception_during_hold_still_allows_release_via_finally | try/finally release path |
| **test_simultaneous_stale_takeover_only_one_wins** | true multiprocess barrier/handshake: N independent processes race a stale lock; exactly 1 wins, N-1 rejected immediately; lock evidence (pid/token) proven stable while winner holds; after explicit release exactly one fresh contender acquires |
| **test_stale_takeover_stress_100_rounds** | same race repeated 100 times (fork context) — exactly one winner every round |

## 2. SingletonGuard / RebuildQueue

| Test | Behavior proven |
|---|---|
| test_duplicate_start_exits_with_defined_code | duplicate start returns defined nonzero code, does not touch the other owner's lock |
| test_normal_run_releases_lock_after_main | lock released after main returns |
| test_exception_in_main_still_releases_lock | lock released via finally on exception |
| test_burst_coalesces_to_bounded_calls | N enqueue calls collapse to fewer callback invocations |
| test_enqueue_returns_immediately | enqueue does not block on a slow callback |

## 3. Evidence framework (no fabricated True)

| Test | Behavior proven |
|---|---|
| test_no_placeholder_true_without_condition | finalize(True) only sets passed when explicitly derived from a condition argument, never a bare literal in production code paths |
| test_fail_locks_passed_false_even_if_finalize_called_with_true | once fail() is called, no later finalize(True) can flip status |

Every Gate A predicate (required_inputs_present, backup_archive_verified,
site_inventory_unchanged, ua0009_not_public, sqlite_quick_check,
protected_inputs_unchanged) is produced exclusively through an Evidence
object; `build_receipt` never assigns `True` as a literal to any of these
keys.

## 4. Bounded site/public inventory

| Test | Behavior proven |
|---|---|
| test_missing_root_blocks | missing required root -> BLOCKED |
| test_unchanged_pass | identical before/after -> pass |
| test_mutation_detected | content change -> comparison fails |
| test_symlink_blocks | symlinked entry rejected |
| test_hardlink_blocks | hard-linked entry rejected (skipped if FS unsupported) |
| test_overflow_blocks | >32 matched files -> BLOCKED |
| test_add_remove_allowed_file_detected | added allowed file changes inventory |

## 5. Publication probe (fail closed)

| Test | Behavior proven |
|---|---|
| test_missing_url_blocks | empty/unconfigured URL -> BLOCKED |
| test_non_https_blocks | non-HTTPS URL -> BLOCKED |
| test_connection_refused_blocks | refused TCP connection -> BLOCKED |
| test_404_passes | genuine no-redirect 404 -> PASS |
| test_200_blocks | 200 (served) -> BLOCKED |
| test_redirect_blocks | 301 (redirect) -> BLOCKED |
| test_timeout_blocks | socket timeout -> BLOCKED |

## 6. SQLite quick_check

| Test | Behavior proven |
|---|---|
| test_ok_db_passes | healthy DB -> quick_check ok |
| test_missing_db_blocks | nonexistent DB -> BLOCKED, no mutation |

## 7. AST structural transforms

| Test | Behavior proven |
|---|---|
| Usercustomize: clean/forbidden-import/unclassified-call/thread-start | inert candidate generated or BLOCKED on any unclassified top-level effect |
| Singleton wrap: clean guard / missing guard / ambiguous guard | exact single main-call anchor required, else BLOCKED |
| Avtoperedacha rebuild: single call replaced / zero calls / multiple calls | exactly one process-spawn anchor required; post-transform call graph re-verified clean |
| cars_ui: simple call rewritten / dynamic dispatch blocked / missing route blocked | text-only rewrite only for statically resolvable call sites; ambiguous dispatch BLOCKS |
| DB short ownership: missing close inserted / already closed / used-after-slow blocks / loop blocks | close inserted only for safe straight-line functions; anything else BLOCKS |

## 8. Deterministic repeat

| Test | Behavior proven |
|---|---|
| test_deterministic_transform_all_identical | 10 repeats of a real transform produce identical hashes |
| test_nondeterministic_transform_blocks | a deliberately nondeterministic transform is detected and BLOCKS |

## 9. SafeWriter hardening

| Test | Behavior proven |
|---|---|
| test_write_confined_to_run_dir | writes stay under the run directory |
| test_traversal_blocked | `..` escape rejected |
| test_symlink_target_blocked | symlinked existing target rejected |
| test_hardlink_target_blocked | hard-linked existing target rejected |

## 10. End-to-end synthetic fixture

| Test | Behavior proven |
|---|---|
| test_sqlite_quick_check_ok_in_fixture | synthetic fixture DB passes quick_check |
| test_fixture_tree_unchanged_after_scan | fixture DB byte-identical before/after evidence collection |

## Known residual limitations (honest disclosure)

- The cars_ui and DB-ownership transforms are intentionally conservative:
  they only rewrite straight-line, statically resolvable patterns and
  BLOCK on anything else. This is correct behavior per the task
  ("ambiguous => BLOCKED"), but it means the real production files may
  legitimately BLOCK on first Gate A execution if their real control flow
  is more complex than the synthetic fixtures used here. That is a safe
  outcome, not a defect.
- The 100-round stress test uses `fork` and is skipped on platforms
  without `os.fork` (e.g. native Windows). PythonAnywhere is Linux, so it
  will run there.
- Controller execution (10 full suite runs) has not been performed by
  Claude/Cloud; this matrix describes what the authored tests prove when
  executed, not a self-reported pass count.
