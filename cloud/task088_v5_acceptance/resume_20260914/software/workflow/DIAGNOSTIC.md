# PR 114 offline workflow-contract diagnostic

Source checkout: detached `e146c2ea`. Diagnosis only; no source, workflow, policy, governance, branch, credentials, live CRM or Production changes.

## Reproduced results

| Scope | Result |
| --- | --- |
| Unmodified `cloud/ua_ge_price_protection/gate.py` | **348/348 PASS**, exit 0, 0 failures/errors/skips |
| `automation/packages/task107_r2/test_workflow_contracts.py` | **35 tests: 28 passed, 7 failed**, 0 errors/skips |
| Exact current autostart parent checks, mocked `git` output | 18/18 probes match current pinned direct-parent-only behavior |
| `verify_production_credential_workflow_policy(root=ROOT)` | PASS |

Price-gate manifest is `18fc3c2ffb16df204cdd7318f550fbffa0a2169da3be57ff0d2bc88b1855b5c7`, matching historical candidate evidence. It runs 21 canonical activation, 32 renderer, 214 pipeline, 23 installer, 37 preview-boundary and 21 gate tests. Only one direct `automation/test_*.py` exists; the nested workflow-contract tests are separate. The real gate was run without overriding its selection or any implementation.

No full system PASS is implied. The seven errors of expectation in the workflow-contract suite are still active failures and the maintenance workflow discovers that entire suite before price protection. Maintenance therefore cannot complete successfully against this snapshot.

## Seven failures and minimal recommended reconciliation

| Failed test | Exact cause | Recommended narrowly scoped remedy |
| --- | --- | --- |
| `test_global_autostart_is_fresh_exact_marker_only` | Test expects three `set --` direct-or-normal-merge parent checks; current workflow has zero and uses three exact direct-parent equality checks. | Align expectations with the documented, currently pinned direct-parent-only launch contract. Verify all three exact checks and execute their rejection cases. |
| `test_global_autostart_parent_gate_accepts_direct_and_normal_merge_only` | Regex expects three multi-parent-tolerant snippets; finds zero. Current pinned code rejects normal merge commits. | Rename and replace behavioral expectation to direct-parent-only if preserving the restored policy; assert merge, octopus, wrong source and wrong parent rejection. Supporting merge launches is a separate real workflow/policy change, not a test-only fix. |
| `test_production_route_has_backup_transaction_rollback_and_watchdog` | Test forbids any watchdog `workflow_dispatch`; current watchdog has explicitly registered recovery plan/canary/execute routes. | Preserve all original transaction assertions; assert exact permitted event set and schedule-only original jobs, plus recovery route identity, operation, credential and approval constraints from the current contract. |
| `test_all_production_state_writers_bind_runtime_before_repo_python` | Expected watchdog writer set excludes `recovery_canary` and `recovery_execute`. | Extend exact writer set by those two existing jobs and verify their distinct `UAART_RECOVERY_RUNTIME_CLOSURE_VALIDATED` bootstrap occurs before repository Python. Do not omit their verification. |
| `test_git_write_credentials_are_scoped_to_trusted_steps` | New recovery step `Capture complete current Actions queue using GET only` uses `github.token` but neither `production_queue.py` nor Git extraheader. | Assert the exact GET-only gh queue-capture contract and cleanup for the approved recovery jobs, while retaining existing token scope assertions everywhere else. Reject non-GET methods, other endpoints or repository Python in that token step. |
| `test_all_durable_pushes_have_bounded_retry` | It applies legacy six-attempt retry expectation to recovery writers that deliberately do one exact compare-and-swap and remote readback. | Split assertions by approved job identity: legacy writers retain bounded retry; both recovery writers must retain one fixed parent, exact lease, immutable path set, one write, and readback. Adding retry to these recovery routes changes their safety contract. |
| `test_watchdog_push_retry_accepts_an_already_persisted_commit` | Expects six watchdog push blocks; there are eight including two recovery CAS writers. | Assert six legacy retry writers plus two separately validated CAS writers. Maintain accepted-commit drift checks for both forms. |

The current control-plane implementation already treats the recovery routes separately: `_verify_watchdog_pinned_recovery_policy` excludes exactly the two recovery CAS jobs from six-retry-writer checks, and `_verify_recovery_route_workflow_policy` enforces their bootstrap, GET-only queue capture, exact CAS, path sets and owner approval binding. Its current policy check passes.

The autostart difference is confirmed by commit `213adac29d204be47da4cd39bff0c81a7605e6ae` ("TASK088: restore pinned autostart workflow identity"): it deliberately replaced the three merge-tolerant snippets with exact direct-parent checks on 11 September. Tests from the earlier change remained. Diagnostic probes extracted the exact current shell snippets and executed them with synthetic `git rev-list` output; no git operation was executed. A normal merge commit is rejected at all three gates. A future automatic launch must honor the currently accepted launch contract unless a separately reviewed policy change is made.

## Evidence

- `actual_price_gate.json`, `actual_price_gate.log`: real unmodified software gate and raw output.
- `workflow_contracts.json`, `workflow_contracts.log`: complete failing suite, named failures and traces.
- `autostart_parent_behavior.json`: 18 actual shell probes and independent workflow policy result.

All tests ran without live application credentials. Additional probes are diagnostic evidence, not extra software-gate tests. No failing assertion was weakened, skipped, removed, or relabeled PASS. This report proposes the reviewable correction; no correction was performed in this read-only subtask.
