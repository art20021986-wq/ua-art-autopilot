# TEST_MATRIX.md — CRM-SPEED-001 (Task 024 correction)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

This matrix maps each Critical Defect from the Task 024 controller verdict
to the behavioral tests that address it. All tests live in
`test_crm_speed_gate_a.py`. None of these tests import, execute, or modify
any real `/home/Carix` file; cross-process tests spawn independent Python
subprocesses via `subprocess`/`sys.executable`.

| Defect | Requirement | Test(s) |
|---|---|---|
| 1. Rebuild queue | Cross-process atomic lock, exactly one concurrent rebuild | `CrossProcessLockTests.test_two_independent_processes_one_wins` |
| 1. Rebuild queue | Anchor binding proof / ambiguity BLOCKED | `RebuildAnchorTests.test_single_safe_anchor_found`, `test_ambiguous_anchors_blocked` |
| 1. Rebuild queue | Burst -> at most one coalesced follow-up, two processes | `RebuildQueueCoalescingTests.test_burst_produces_bounded_followups_two_processes` |
| 2. Singleton lifecycle | Live duplicate exits nonzero | `SingletonGuardTests.test_duplicate_start_exits_nonzero` |
| 2. Singleton lifecycle | Stale dead PID takeover | `CrossProcessLockTests.test_stale_dead_pid_takeover` |
| 2. Singleton lifecycle | Foreign token release denied | `CrossProcessLockTests.test_foreign_token_release_denied` |
| 2. Singleton lifecycle | Clean release + reacquire | `CrossProcessLockTests.test_clean_release_and_reacquire` |
| 2. Singleton lifecycle | Exception path still releases | `CrossProcessLockTests.test_exception_path_still_releases_via_context_manager` |
| 2. Singleton lifecycle | Simultaneous stale takeover, only one wins | `CrossProcessLockTests.test_simultaneous_stale_takeover_only_one_wins` |
| 3. SQLite ownership | Negative case shows violation pre-transform | `SqliteOwnershipTests.test_negative_case_has_violation_before_transform` |
| 3. SQLite ownership | Transform removes violation, verifier proves closure | `SqliteOwnershipTests.test_transform_removes_violation` |
| 3. SQLite ownership | Missing anchor is BLOCKED, not silently patched | `SqliteOwnershipTests.test_missing_function_blocked` |
| 4. UA-0009 fail-closed | Missing config -> BLOCKED, not SKIPPED | `Ua0009PublicationCheckTests.test_missing_config_is_blocked_not_skipped` |
| 4. UA-0009 fail-closed | 404 + quick_check ok -> pass | `Ua0009PublicationCheckTests.test_404_and_quick_check_ok_passes` |
| 4. UA-0009 fail-closed | Ambiguous 200 status -> BLOCKED | `Ua0009PublicationCheckTests.test_200_status_is_blocked` |
| 5. Reachable media-call proof | Clean module passes | `MediaCallGraphTests.test_clean_module_passes` |
| 5. Reachable media-call proof | Indirect helper violation detected | `MediaCallGraphTests.test_indirect_helper_violation_detected` |
| 5. Reachable media-call proof | Dynamic dispatch is BLOCKED, not passed | `MediaCallGraphTests.test_dynamic_dispatch_is_blocked_not_passed` |
| 6. SafeWriter hardening | Atomic write + hash | `SafeWriterTests.test_atomic_write_and_hash` |
| 6. SafeWriter hardening | Traversal rejected | `SafeWriterTests.test_traversal_rejected` |
| 6. SafeWriter hardening | Symlink parent rejected | `SafeWriterTests.test_symlink_parent_rejected` |
| 6. SafeWriter hardening | Hard-link target rejected | `SafeWriterTests.test_hardlink_target_rejected` |
| 6. SafeWriter hardening | Insufficient free space rejected | `SafeWriterTests.test_insufficient_free_space_rejected` |
| 7. Tests/status | Full suite, compile check, no self-referential assertions | entire suite is behavioral (fixtures + real subprocesses), see `cloud_report_020.md` for execution-evidence caveat |

## Known limitation, stated explicitly

Claude authored and structurally reasoned through this suite but does not
have a code-execution channel in this delivery context. Claude does **not**
claim to have run this suite 10 times on PythonAnywhere or anywhere else.
Per the AUTOPILOT protocol (see prior accepted precedent REC-0009/REC-0011
for TASK 015), the controller must independently execute
`test_crm_speed_gate_a.py` (e.g. `python3 -m unittest -v` run at least 10
times) and record pass/fail evidence before this package can move past
`READY_FOR_CONTROLLER_REVIEW`.
